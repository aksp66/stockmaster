"""
Audit de sécurité générique, calculé sur toutes les routes de l'application :

1. matrice des accès : seuls les rôles prévus ouvrent chaque espace ;
2. isolation entre entreprises : un utilisateur d'une autre entreprise ne peut ni lire ni modifier un objet de
   l'entreprise A en connaissant son identifiant (GET et POST sur chaque URL à identifiant, avec les identifiants de
   chaque objet de l'entreprise A) ;
3. aucune réponse 500 sur ces requêtes hostiles.
"""
import re
import uuid

from django.apps import apps
from django.db.models import UUIDField
from django.urls import NoReverseMatch, get_resolver, reverse

from apps.core.models import AuditLog
from apps.stock.models import (
    Alerte, BonCommande, Categorie, InventaireSession, LigneCommande, LigneInventaire, Mouvement,
)

from .base import EntrepriseTestCase, creer_entreprise, creer_utilisateur

ESPACES = ['superadmin', 'admin_entreprise', 'gestionnaire', 'responsable_achat', 'magasinier', 'auditeur', 'comptable']
ROLES = ['super_admin', 'admin_ent', 'gestionnaire', 'responsable_achat', 'magasinier', 'auditeur', 'comptable']
# Rôle propre à chaque espace (le rôle « normal » de ses utilisateurs)
ROLE_DE_L_ESPACE = {'superadmin': 'super_admin', 'admin_entreprise': 'admin_ent', 'gestionnaire': 'gestionnaire',
                    'responsable_achat': 'responsable_achat', 'magasinier': 'magasinier', 'auditeur': 'auditeur',
                    'comptable': 'comptable'}
# Rôles autorisés dans chaque espace en plus du rôle propre (l'admin entreprise supervise tous les espaces
# d'entreprise ; le magasinier saisit des mouvements dans l'espace gestionnaire ; le gestionnaire utilise le scan)
AUTORISES = {
    'superadmin': set(),
    'admin_entreprise': set(),
    'gestionnaire': {'admin_ent'},
    'responsable_achat': {'admin_ent'},
    'magasinier': {'admin_ent', 'gestionnaire'},
    'auditeur': {'admin_ent'},
    'comptable': {'admin_ent'},
}
# Pages d'un espace ouvertes volontairement à un autre rôle
EXCEPTIONS = {
    ('gestionnaire', 'magasinier'): {'transfert', 'scan', 'mouvement_create', 'mouvement_form', 'produit_search_ajax'},
    ('magasinier', 'gestionnaire'): {'produit_search_ajax', 'api_scan'},
}
A_EXCLURE = re.compile(r'logout|deconnexion')


def urls_sans_parametre(espace):
    resolver = get_resolver().namespace_dict[espace][1]
    for nom in sorted(n for n in resolver.reverse_dict if isinstance(n, str) and not A_EXCLURE.search(n)):
        try:
            yield nom, reverse(f'{espace}:{nom}')
        except NoReverseMatch:
            continue


def noms_a_parametres(espace):
    """(nom, [paramètres]) des routes de l'espace qui attendent un identifiant."""
    resolver = get_resolver().namespace_dict[espace][1]
    for nom in sorted(n for n in resolver.reverse_dict if isinstance(n, str) and not A_EXCLURE.search(n)):
        for possibilites, _, _, _ in resolver.reverse_dict.getlist(nom):
            for _, params in possibilites:
                if params:
                    yield nom, params


class MatriceDesAccesTests(EntrepriseTestCase):

    def test_seuls_les_roles_prevus_ouvrent_chaque_espace(self):
        users = {r: (self.users.get(r) or creer_utilisateur(r)) for r in ROLES}
        problemes = []
        for espace in ESPACES:
            urls = list(urls_sans_parametre(espace))
            permis = {ROLE_DE_L_ESPACE[espace]} | AUTORISES[espace]
            for role in ROLES:
                self.client.force_login(users[role])
                for nom, url in urls:
                    ouverte = self.client.get(url).status_code == 200
                    if role in permis or not ouverte:
                        continue
                    if nom in EXCEPTIONS.get((espace, role), set()):
                        continue
                    problemes.append(f'{role} ouvre {espace}:{nom}')
        self.assertEqual(problemes, [])

    def test_visiteur_anonyme_ne_voit_aucun_espace(self):
        for espace in ESPACES:
            for nom, url in urls_sans_parametre(espace):
                reponse = self.client.get(url)
                self.assertIn(reponse.status_code, (302, 401, 403, 405), f'{espace}:{nom}')
                if reponse.status_code == 302:
                    self.assertIn('/connexion', reponse['Location'] + '/connexion' if 'connexion' not in reponse['Location'] else reponse['Location'])


class IsolationEntreEntreprisesTests(EntrepriseTestCase):
    """Chaque URL à identifiant, essayée par un utilisateur de l'entreprise B avec les identifiants de l'entreprise A."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cat = Categorie.objects.create(nom='Épicerie', entreprise=cls.ent)
        bc = BonCommande.objects.create(entreprise=cls.ent, fournisseur=cls.fournisseur, statut='envoye',
                                        entrepot_destination=cls.entrepot)
        LigneCommande.objects.create(bon_commande=bc, produit=cls.produit, quantite_commandee=5, prix_unitaire_ht=100)
        session = InventaireSession.objects.create(entrepot=cls.entrepot, utilisateur_demarrage=cls.users['magasinier'])
        LigneInventaire.objects.create(session=session, produit=cls.produit, quantite_theorique=10)
        Alerte.objects.create(produit=cls.produit, entrepot=cls.entrepot, type_alerte='rupture', priorite='critique',
                              message='x')
        Mouvement.objects.create(type_mouvement='entree', produit=cls.produit, quantite=1, entrepot_destination=cls.entrepot)
        AuditLog.objects.create(entreprise=cls.ent, description='journal')
        cls.cat = cat
        # Entreprise B : un utilisateur par rôle
        cls.ent_b = creer_entreprise('Entreprise B')
        cls.users_b = {r: creer_utilisateur(r, cls.ent_b) for r in ROLES if r != 'super_admin'}

    def _identifiants_de_l_entreprise_a(self):
        """Un identifiant par objet de chaque table (hors utilisateurs de B), tous de l'entreprise A."""
        ids = set()
        for modele in apps.get_models():
            if modele._meta.app_label not in ('stock', 'accounts', 'entreprises', 'core') or \
                    not isinstance(modele._meta.pk, UUIDField):
                continue
            for pk in modele.objects.values_list('pk', flat=True)[:6]:
                ids.add(pk)
        ids -= {u.pk for u in self.users_b.values()}
        ids.discard(self.ent_b.pk)
        return ids

    def _instantane(self):
        """Empreinte de toutes les données de l'entreprise A, pour détecter la moindre modification."""
        etat = {}
        for modele in apps.get_models():
            if modele._meta.app_label in ('stock', 'accounts', 'entreprises', 'core'):
                etat[modele.__name__] = sorted(map(str, modele.objects.values_list()))
        return etat

    def test_aucune_fuite_ni_modification_inter_entreprises(self):
        ids_a = self._identifiants_de_l_entreprise_a()
        self.assertGreater(len(ids_a), 15)
        fuites, erreurs, modifications = [], [], []
        etat = self._instantane()
        for espace in ESPACES:
            if espace == 'superadmin':
                continue  # le super admin gère toutes les entreprises par conception
            self.client.force_login(self.users_b[ROLE_DE_L_ESPACE[espace]])
            etat = self._instantane()  # la connexion met à jour last_login : état de référence après elle
            for nom, params in noms_a_parametres(espace):
                for pk in ids_a:
                    kwargs = {p: (pk if i == 0 else 'annule') for i, p in enumerate(params)}
                    try:
                        url = reverse(f'{espace}:{nom}', kwargs=kwargs)
                    except NoReverseMatch:
                        continue  # l'identifiant n'a pas le bon format pour cette route (str attendu, etc.)
                    for methode in ('get', 'post'):
                        reponse = getattr(self.client, methode)(url)
                        if reponse.status_code == 200 and methode == 'get':
                            fuites.append(f'GET {url}')
                        elif reponse.status_code >= 500:
                            erreurs.append(f'{methode.upper()} {url} -> {reponse.status_code}')
                    nouvel_etat = self._instantane()
                    if nouvel_etat != etat:
                        modifications.append(f'POST/GET {url}')
                        etat = nouvel_etat
        self.assertEqual(fuites, [], "pages de l'entreprise A affichées à un utilisateur de B")
        self.assertEqual(erreurs, [], 'erreurs serveur sur requêtes hostiles')
        self.assertEqual(modifications, [], "données de l'entreprise A modifiées par un utilisateur de B")
