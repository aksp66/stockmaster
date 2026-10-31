"""Séparation des données entre entreprises (multi-tenant)."""
from django.urls import reverse

from apps.stock.models import BonCommande, Mouvement

from .base import (
    EntrepriseTestCase, creer_entreprise, creer_entrepot, creer_fournisseur, creer_produit,
    mettre_en_stock, quantite_en_stock,
)


class SeparationEntreprisesTests(EntrepriseTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.autre = creer_entreprise("Entreprise B")
        cls.autre_entrepot = creer_entrepot(cls.autre, "Dépôt B")
        cls.autre_produit = creer_produit(cls.autre, nom="Produit secret B")
        cls.autre_fournisseur = creer_fournisseur(cls.autre, "Fournisseur B")
        mettre_en_stock(cls.autre_produit, cls.autre_entrepot, 50)
        cls.autre_bc = BonCommande.objects.create(entreprise=cls.autre, fournisseur=cls.autre_fournisseur)

    def test_fiche_produit_d_une_autre_entreprise_introuvable(self):
        self.connecter('gestionnaire')
        response = self.client.get(reverse('gestionnaire:produit_detail', args=[self.autre_produit.pk]))
        self.assertEqual(response.status_code, 404)

    def test_liste_produits_limitee_a_l_entreprise(self):
        self.connecter('gestionnaire')
        response = self.client.get(reverse('gestionnaire:produits'))
        self.assertContains(response, self.produit.nom)
        self.assertNotContains(response, "Produit secret B")

    def test_mouvement_sur_produit_d_une_autre_entreprise_refuse(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.autre_produit.pk, 'type_mouvement': 'sortie',
            'quantite': 5, 'entrepot': self.autre_entrepot.pk,
        })
        self.assertFalse(Mouvement.objects.exists())
        self.assertEqual(quantite_en_stock(self.autre_produit, self.autre_entrepot), 50)

    def test_bon_de_commande_d_une_autre_entreprise_inaccessible(self):
        self.connecter('responsable_achat')
        for name in ('boncommande_detail', 'boncommande_pdf', 'boncommande_reception'):
            with self.subTest(vue=name):
                response = self.client.get(reverse(f'responsable_achat:{name}', args=[self.autre_bc.pk]))
                self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse('responsable_achat:boncommande_annuler', args=[self.autre_bc.pk]))
        self.assertEqual(response.status_code, 404)
        self.autre_bc.refresh_from_db()
        self.assertEqual(self.autre_bc.statut, 'brouillon')

    def test_fournisseur_d_une_autre_entreprise_inaccessible(self):
        self.connecter('responsable_achat')
        response = self.client.get(reverse('responsable_achat:fournisseur_detail', args=[self.autre_fournisseur.pk]))
        self.assertEqual(response.status_code, 404)

    def test_numero_de_bc_unique_entre_entreprises(self):
        # Les deux entreprises démarrent leur numérotation : pas de collision sur `numero` (unique global)
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur)
        self.assertNotEqual(bc.numero, self.autre_bc.numero)
