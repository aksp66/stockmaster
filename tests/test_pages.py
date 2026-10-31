"""
Chaque page sans paramètre de chaque espace s'affiche pour son rôle (pas d'erreur serveur,
pas de template invalide). Filet de sécurité contre les régressions de templates.
"""
import re

from django.urls import get_resolver, reverse, NoReverseMatch

from apps.stock.models import BonCommande, InventaireSession, LigneCommande, LigneInventaire

from .base import EntrepriseTestCase, creer_utilisateur

ESPACES = {
    'gestionnaire': 'gestionnaire',
    'magasinier': 'magasinier',
    'auditeur': 'auditeur',
    'comptable': 'comptable',
    'admin_entreprise': 'admin_ent',
    'responsable_achat': 'responsable_achat',
}
# Vues qui modifient des données ou attendent un POST : hors périmètre d'un simple affichage
A_EXCLURE = re.compile(r'supprim|delete|acquitt|valider|annul|deconnexion|logout|lancer|api_|search|marquer|export')


def pages_sans_parametre(namespace):
    resolver = get_resolver().namespace_dict[namespace][1]
    for nom in resolver.reverse_dict:
        if isinstance(nom, str) and not A_EXCLURE.search(nom):
            try:
                yield nom, reverse(f'{namespace}:{nom}')
            except NoReverseMatch:
                continue


class AffichageDesPagesTests(EntrepriseTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        bc = BonCommande.objects.create(entreprise=cls.ent, fournisseur=cls.fournisseur, statut='envoye')
        LigneCommande.objects.create(bon_commande=bc, produit=cls.produit, quantite_commandee=5, prix_unitaire_ht=100)
        session = InventaireSession.objects.create(entrepot=cls.entrepot, utilisateur_demarrage=cls.users['magasinier'])
        LigneInventaire.objects.create(session=session, produit=cls.produit, quantite_theorique=10)
        cls.bc, cls.session = bc, session

    def test_pages_de_chaque_espace(self):
        for namespace, role in ESPACES.items():
            self.connecter(role)
            for nom, url in pages_sans_parametre(namespace):
                with self.subTest(page=f'{namespace}:{nom}'):
                    response = self.client.get(url)
                    self.assertIn(response.status_code, (200, 302), url)

    def test_pages_de_detail(self):
        pages = [
            ('gestionnaire', reverse('gestionnaire:produit_detail', args=[self.produit.pk])),
            ('gestionnaire', reverse('gestionnaire:produit_edit', args=[self.produit.pk])),
            ('gestionnaire', reverse('gestionnaire:inventaire_session_detail', args=[self.session.pk])),
            ('magasinier', reverse('magasinier:inventaire_detail', args=[self.session.pk])),
            ('responsable_achat', reverse('responsable_achat:fournisseur_edit', args=[self.fournisseur.pk])),
        ]
        for role, url in pages:
            with self.subTest(url=url):
                self.connecter(role)
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_espace_superadmin(self):
        self.client.force_login(creer_utilisateur('super_admin'))
        for nom, url in pages_sans_parametre('superadmin'):
            with self.subTest(page=nom):
                self.assertIn(self.client.get(url).status_code, (200, 302))
        url = reverse('superadmin:detail_entreprise', args=[self.ent.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
