"""Inventaire : comptage par le magasinier, validation (ajustements de stock) par le gestionnaire."""
from django.urls import reverse

from apps.stock.models import InventaireSession, LigneInventaire, Mouvement, TypeMouvement

from .base import EntrepriseTestCase, creer_produit, mettre_en_stock, quantite_en_stock


class InventaireTests(EntrepriseTestCase):

    def setUp(self):
        self.produit2 = creer_produit(self.ent, nom="Huile 5 L")
        mettre_en_stock(self.produit2, self.entrepot, 20)
        self.session = InventaireSession.objects.create(entrepot=self.entrepot)
        self.l1 = LigneInventaire.objects.create(session=self.session, produit=self.produit, quantite_theorique=10)
        self.l2 = LigneInventaire.objects.create(session=self.session, produit=self.produit2, quantite_theorique=20)

    def test_page_de_saisie_magasinier(self):
        self.connecter('magasinier')
        response = self.client.get(reverse('magasinier:inventaire_detail', args=[self.session.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('magasinier:inventaire_sauvegarder', args=[self.session.pk]))

    def test_sauvegarde_du_comptage_sans_toucher_au_stock(self):
        self.connecter('magasinier')
        response = self.client.post(reverse('magasinier:inventaire_sauvegarder', args=[self.session.pk]), {
            f'qte_{self.l1.pk}': '12', f'qte_{self.l2.pk}': '', 'action': 'sauvegarder',
        })
        self.assertRedirects(response, reverse('magasinier:inventaire_detail', args=[self.session.pk]),
                             fetch_redirect_response=False)
        self.l1.refresh_from_db()
        self.l2.refresh_from_db()
        self.assertEqual(self.l1.quantite_comptee, 12)
        self.assertIsNone(self.l2.quantite_comptee)
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)

    def test_quantite_negative_ignoree(self):
        self.connecter('magasinier')
        self.client.post(reverse('magasinier:inventaire_sauvegarder', args=[self.session.pk]), {f'qte_{self.l1.pk}': '-3'})
        self.l1.refresh_from_db()
        self.assertIsNone(self.l1.quantite_comptee)

    def test_validation_applique_surplus_et_manque(self):
        self.l1.quantite_comptee = 13   # surplus de 3
        self.l1.save()
        self.l2.quantite_comptee = 15   # manque de 5
        self.l2.save()
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:inventaire_valider', args=[self.session.pk]))

        self.session.refresh_from_db()
        self.assertEqual(self.session.statut, 'valide')
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 13)
        self.assertEqual(quantite_en_stock(self.produit2, self.entrepot), 15)
        self.assertEqual(Mouvement.objects.filter(type_mouvement=TypeMouvement.AJUSTEMENT).count(), 2)

    def test_lignes_non_comptees_ignorees_a_la_validation(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:inventaire_valider', args=[self.session.pk]))
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)
        self.assertFalse(Mouvement.objects.exists())

    def test_comptage_refuse_apres_validation(self):
        self.session.statut = 'valide'
        self.session.save()
        self.connecter('magasinier')
        self.client.post(reverse('magasinier:inventaire_sauvegarder', args=[self.session.pk]), {f'qte_{self.l1.pk}': '99'})
        self.l1.refresh_from_db()
        self.assertIsNone(self.l1.quantite_comptee)
