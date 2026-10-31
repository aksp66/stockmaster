"""Workflow des bons de commande : création, envoi, réception (mise à jour du stock), clôture, PDF."""
from decimal import Decimal

from django.urls import reverse

from apps.stock.models import BonCommande, LigneCommande, Mouvement, TypeMouvement

from .base import EntrepriseTestCase, quantite_en_stock


class BonCommandeTests(EntrepriseTestCase):

    def setUp(self):
        self.connecter('responsable_achat')

    def _bc(self, statut='brouillon', quantite=10, prix='500'):
        bc = BonCommande.objects.create(
            entreprise=self.ent, fournisseur=self.fournisseur, statut=statut,
            entrepot_destination=self.entrepot,
        )
        LigneCommande.objects.create(bon_commande=bc, produit=self.produit,
                                     quantite_commandee=quantite, prix_unitaire_ht=Decimal(prix))
        return bc

    def test_creation_depuis_le_formulaire(self):
        response = self.client.post(reverse('responsable_achat:boncommande_create'), {
            'fournisseur': self.fournisseur.pk, 'entrepot_destination': self.entrepot.pk,
            'commentaire': 'Urgent',
            'lignes[0][produit]': self.produit.pk, 'lignes[0][quantite]': '8',
            'lignes[0][prix_unitaire]': '1000', 'lignes[0][remise]': '10',
            'action': 'brouillon',
        })
        bc = BonCommande.objects.get()
        self.assertRedirects(response, reverse('responsable_achat:boncommande_detail', args=[bc.pk]),
                             fetch_redirect_response=False)
        ligne = bc.lignes.get()
        self.assertEqual(ligne.quantite_commandee, 8)
        self.assertEqual(ligne.prix_unitaire_ht, Decimal('900.00'))  # remise de 10 % appliquée
        self.assertEqual(bc.note, 'Urgent')
        self.assertEqual(bc.statut, 'brouillon')

    def test_creation_et_envoi_direct(self):
        self.client.post(reverse('responsable_achat:boncommande_create'), {
            'fournisseur': self.fournisseur.pk,
            'lignes[0][produit]': self.produit.pk, 'lignes[0][quantite]': '2', 'lignes[0][prix_unitaire]': '50',
            'action': 'envoyer',
        })
        self.assertEqual(BonCommande.objects.get().statut, 'envoye')

    def test_envoi_d_un_brouillon(self):
        bc = self._bc()
        self.client.post(reverse('responsable_achat:boncommande_envoyer', args=[bc.pk]))
        bc.refresh_from_db()
        self.assertEqual(bc.statut, 'envoye')

    def test_envoi_refuse_sans_ligne(self):
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur)
        self.client.post(reverse('responsable_achat:boncommande_envoyer', args=[bc.pk]))
        bc.refresh_from_db()
        self.assertEqual(bc.statut, 'brouillon')

    def test_actions_de_statut_refusees_en_get(self):
        bc = self._bc()
        response = self.client.get(reverse('responsable_achat:boncommande_envoyer', args=[bc.pk]))
        self.assertEqual(response.status_code, 405)

    def test_reception_partielle_puis_complete(self):
        bc = self._bc(statut='envoye', quantite=10)
        ligne = bc.lignes.get()
        url = reverse('responsable_achat:boncommande_reception', args=[bc.pk])

        self.client.post(url, {f'recu_{ligne.pk}': '4', 'entrepot': self.entrepot.pk, 'reference_bl': 'BL-1'})
        bc.refresh_from_db()
        self.assertEqual(bc.statut, 'recu_partiel')
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 14)
        mouv = Mouvement.objects.get()
        self.assertEqual((mouv.type_mouvement, mouv.reference), (TypeMouvement.ENTREE, f"BC-{bc.numero}"))
        self.assertEqual(mouv.prix_unitaire_snapshot, Decimal('500'))

        # Réception au-delà du restant : plafonnée à 6
        self.client.post(url, {f'recu_{ligne.pk}': '50', 'entrepot': self.entrepot.pk})
        bc.refresh_from_db()
        self.assertEqual(bc.statut, 'recu_complet')
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 20)
        self.assertIsNotNone(bc.date_livraison_effective)

    def test_reception_impossible_sur_brouillon(self):
        bc = self._bc()
        response = self.client.get(reverse('responsable_achat:boncommande_reception', args=[bc.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cloture_et_annulation(self):
        bc = self._bc(statut='recu_complet')
        self.client.post(reverse('responsable_achat:boncommande_cloturer', args=[bc.pk]))
        bc.refresh_from_db()
        self.assertEqual(bc.statut, 'cloture')
        # Un BC clôturé ne peut plus être annulé
        self.client.post(reverse('responsable_achat:boncommande_annuler', args=[bc.pk]))
        bc.refresh_from_db()
        self.assertEqual(bc.statut, 'cloture')

    def test_annulation_d_un_bc_envoye(self):
        bc = self._bc(statut='envoye')
        self.client.post(reverse('responsable_achat:boncommande_annuler', args=[bc.pk]))
        bc.refresh_from_db()
        self.assertEqual(bc.statut, 'annule')

    def test_pdf(self):
        bc = self._bc()
        response = self.client.get(reverse('responsable_achat:boncommande_pdf', args=[bc.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_pages_achats_affichent_les_donnees(self):
        bc = self._bc(statut='envoye')
        pages = [
            reverse('responsable_achat:dashboard'),
            reverse('responsable_achat:boncommande_list'),
            reverse('responsable_achat:boncommande_detail', args=[bc.pk]),
            reverse('responsable_achat:boncommande_reception', args=[bc.pk]),
            reverse('responsable_achat:fournisseur_detail', args=[self.fournisseur.pk]),
            reverse('responsable_achat:fournisseur_list'),
        ]
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
        self.assertContains(self.client.get(reverse('responsable_achat:boncommande_list')), bc.numero)
