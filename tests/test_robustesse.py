"""
Robot de parcours, intégré à la CI :

1. gabarits : chaque page de chaque espace est rendue ; toute variable de gabarit qui échoue alors que l'objet existe
   (attribut inexistant sur un modèle, variable absente du contexte) est signalée. C'est la classe de défauts la plus
   fréquente trouvée en revue (gabarit écrit pour un champ qui n'existe pas). Traverser un None
   (``{{ produit.categorie.nom }}`` sans catégorie) est légitime et ignoré ;
2. formulaires : un POST vide sur chaque route, pour chaque rôle autorisé, ne doit jamais provoquer d'erreur serveur ;
3. lecture seule : l'auditeur ne modifie aucune donnée, quelle que soit la route qu'il appelle.
"""
import re
from collections import defaultdict

from django.apps import apps
from django.db import transaction
from django.template.base import Variable, VariableDoesNotExist
from django.template.context import BaseContext
from django.urls import NoReverseMatch, get_resolver, reverse

from apps.stock.models import (
    Alerte, BonCommande, InventaireSession, LigneCommande, LigneInventaire, Mouvement,
)

from .base import EntrepriseTestCase
from .test_securite_generique import ESPACES, ROLE_DE_L_ESPACE

A_EXCLURE = re.compile(r'logout|deconnexion')
# Variables fournies par Django ou par les bibliothèques, absentes du contexte hors requête réelle
IGNORES = ('csrf_token', 'perms', 'DEFAULT_MESSAGE_LEVELS', 'forloop',
           # facultatives : présentes en modification, absentes en création (ou l'inverse)
           'bc', 'entrepot', 'utilisateur', 'scan_settings')


def routes_sans_parametre(espace):
    resolver = get_resolver().namespace_dict[espace][1]
    for nom in sorted(n for n in resolver.reverse_dict if isinstance(n, str) and not A_EXCLURE.search(n)):
        try:
            yield nom, reverse(f'{espace}:{nom}')
        except NoReverseMatch:
            continue


class DonneesDeParcours(EntrepriseTestCase):

    def setUp(self):
        super().setUp()
        self.client.raise_request_exception = False  # une erreur serveur est renvoyée (500) au lieu d'être levée

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        bc = BonCommande.objects.create(entreprise=cls.ent, fournisseur=cls.fournisseur, statut='envoye',
                                        entrepot_destination=cls.entrepot)
        LigneCommande.objects.create(bon_commande=bc, produit=cls.produit, quantite_commandee=5, prix_unitaire_ht=100)
        session = InventaireSession.objects.create(entrepot=cls.entrepot, utilisateur_demarrage=cls.users['magasinier'])
        LigneInventaire.objects.create(session=session, produit=cls.produit, quantite_theorique=10)
        Alerte.objects.create(produit=cls.produit, entrepot=cls.entrepot, type_alerte='rupture', priorite='critique',
                              message='x')
        Mouvement.objects.create(type_mouvement='entree', produit=cls.produit, quantite=1, entrepot_destination=cls.entrepot)
        cls.bc, cls.session = bc, session

    def requete(self, methode, url):
        """Requête isolée : annulée ensuite (point de sauvegarde), pour qu'une erreur SQL n'abîme pas la suite."""
        sauvegarde = transaction.savepoint()
        try:
            return getattr(self.client, methode)(url)
        finally:
            transaction.savepoint_rollback(sauvegarde)

    def pages_de_detail(self):
        """(rôle, url) des pages qui demandent un identifiant."""
        return [
            ('gestionnaire', reverse('gestionnaire:produit_detail', args=[self.produit.pk])),
            ('gestionnaire', reverse('gestionnaire:produit_edit', args=[self.produit.pk])),
            ('gestionnaire', reverse('gestionnaire:inventaire_session_detail', args=[self.session.pk])),
            ('magasinier', reverse('magasinier:inventaire_detail', args=[self.session.pk])),
            ('responsable_achat', reverse('responsable_achat:boncommande_detail', args=[self.bc.pk])),
            ('responsable_achat', reverse('responsable_achat:boncommande_edit', args=[self.bc.pk])),
            ('responsable_achat', reverse('responsable_achat:boncommande_reception', args=[self.bc.pk])),
            ('responsable_achat', reverse('responsable_achat:fournisseur_edit', args=[self.fournisseur.pk])),
            ('admin_ent', reverse('admin_entreprise:modifier_utilisateur', args=[self.users['comptable'].pk])),
        ]


class RobotDesGabaritsTests(DonneesDeParcours):

    def test_aucune_variable_de_gabarit_en_echec(self):
        echecs = defaultdict(set)
        original = Variable._resolve_lookup

        def espion(variable, context):
            try:
                return original(variable, context)
            except VariableDoesNotExist:
                courant = context
                for bit in variable.lookups:
                    try:
                        courant = courant[bit]
                        continue
                    except (TypeError, AttributeError, KeyError, ValueError, IndexError):
                        pass
                    try:
                        courant = getattr(courant, bit)
                    except (TypeError, AttributeError, ValueError):
                        if courant is not None and variable.lookups[0] not in IGNORES and not hasattr(courant, 'getlist'):
                            quoi = bit if isinstance(courant, BaseContext) else f'{type(courant).__name__}.{bit}'
                            echecs[quoi].add(variable.var)
                        break
                    if callable(courant):
                        try:
                            courant = courant()
                        except Exception:
                            break
                raise

        Variable._resolve_lookup = espion
        try:
            for espace in ESPACES:
                self.client.force_login(self.users.get(ROLE_DE_L_ESPACE[espace]) or self._super_admin())
                for _, url in routes_sans_parametre(espace):
                    self.client.get(url)
            for role, url in self.pages_de_detail():
                self.connecter(role)
                self.client.get(url)
        finally:
            Variable._resolve_lookup = original
        self.maxDiff = None
        self.assertEqual({k: sorted(v)[:3] for k, v in sorted(echecs.items())}, {})

    def _super_admin(self):
        from .base import creer_utilisateur
        return creer_utilisateur('super_admin')


class PostVidesTests(DonneesDeParcours):

    def test_post_vide_sur_chaque_route_sans_erreur_serveur(self):
        erreurs = []
        for espace in ESPACES:
            if espace == 'superadmin':
                utilisateur = self._super_admin()
            else:
                utilisateur = self.users[ROLE_DE_L_ESPACE[espace]]
            self.client.force_login(utilisateur)
            for nom, url in routes_sans_parametre(espace):
                reponse = self.requete('post', url)
                if reponse.status_code >= 500:
                    erreurs.append(f'POST {espace}:{nom} -> {reponse.status_code}')
        self.assertEqual(erreurs, [])

    def test_post_vide_sur_chaque_page_de_detail(self):
        erreurs = []
        for role, url in self.pages_de_detail():
            self.connecter(role)
            reponse = self.requete('post', url)
            if reponse.status_code >= 500:
                erreurs.append(f'POST {url} -> {reponse.status_code}')
        self.assertEqual(erreurs, [])

    def _super_admin(self):
        from .base import creer_utilisateur
        return creer_utilisateur('super_admin')


class LectureSeuleTests(DonneesDeParcours):
    """Un auditeur consulte tout et ne modifie rien, même s'il appelle directement les routes d'écriture."""

    def _etat(self):
        return {m.__name__: sorted(map(str, m.objects.values_list()))
                for m in apps.get_models() if m._meta.app_label in ('stock', 'accounts', 'entreprises')}

    def test_l_auditeur_ne_modifie_aucune_donnee(self):
        self.connecter('auditeur')
        avant = self._etat()
        erreurs = []
        for espace in ESPACES:
            for nom, url in routes_sans_parametre(espace):
                for methode in ('post', 'put', 'delete'):
                    reponse = self.requete(methode, url)
                    erreurs.append(f'{methode} {espace}:{nom}') if reponse.status_code >= 500 else None
        for _, url in self.pages_de_detail():
            self.client.post(url)
            self.client.delete(url)
        self.assertEqual(erreurs, [])
        self.assertEqual(self._etat(), avant)
