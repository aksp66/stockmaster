"""Retours, calcul de réapprovisionnement et vérification des seuils après chaque variation de stock."""
import json
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.stock.models import (
    Alerte, BonCommande, InventaireSession, LigneCommande, LigneInventaire, Mouvement, PredictionStock, TypeMouvement,
)
from apps.stock.reappro import calculer_reappro

from .base import EntrepriseTestCase, creer_produit, mettre_en_stock, quantite_en_stock


class RetourTests(EntrepriseTestCase):

    def setUp(self):
        self.connecter('gestionnaire')

    def _retour(self, sens, quantite):
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'retour', 'quantite': quantite,
            'entrepot': self.entrepot.pk, 'sens_retour': sens,
        })

    def test_retour_client_entre_en_stock(self):
        self._retour('client', 3)
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 13)
        self.assertEqual(Mouvement.objects.get().signe, '+')

    def test_retour_fournisseur_sort_du_stock(self):
        self._retour('fournisseur', 4)
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 6)
        self.assertEqual(Mouvement.objects.get().signe, '−')

    def test_retour_fournisseur_superieur_au_stock_refuse(self):
        self._retour('fournisseur', 50)
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)
        self.assertFalse(Mouvement.objects.exists())

    def test_type_de_mouvement_inconnu_refuse(self):
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'vente', 'quantite': 1, 'entrepot': self.entrepot.pk,
        })
        self.assertFalse(Mouvement.objects.exists())

    def test_signe_affiche_dans_l_historique(self):
        self._retour('client', 3)
        self.assertContains(self.client.get(reverse('gestionnaire:mouvements')), '+3')


class CalculReapproTests(EntrepriseTestCase):
    """Produit : 10 en stock, seuil 5, délai de réappro 7 jours (valeurs par défaut des fabriques)."""

    def _predictions(self, par_jour):
        """Comme apps/ia/tasks.py : une ligne portant la consommation totale prévue sur 30 jours."""
        PredictionStock.objects.create(produit=self.produit, date_cible=timezone.localdate() + timedelta(days=30),
                                       quantite_prevue=Decimal(str(par_jour)) * 30, confiance=85,
                                       modele_utilise='prophet')

    def test_quantite_basee_sur_la_consommation_prevue(self):
        self._predictions(2)
        r = calculer_reappro(self.produit)
        # 60 prévus sur 30 jours = 2/jour ; 2 × (7 + 30) + 5 − 10 = 69
        self.assertEqual((r['source'], r['conso_jour'], r['jours_rupture'], r['quantite_suggeree'], r['confiance']),
                         ('ia', Decimal(2), 5, Decimal(69), 85))
        self.assertTrue(r['urgent'])  # rupture dans 5 jours, avant une livraison (7 jours)

    def test_commandes_en_cours_deduites(self):
        self._predictions(2)
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur, statut='envoye')
        LigneCommande.objects.create(bon_commande=bc, produit=self.produit, quantite_commandee=50,
                                     quantite_recue=10, prix_unitaire_ht=1)
        self.assertEqual(calculer_reappro(self.produit)['quantite_suggeree'], Decimal(29))  # 69 − 40 en attente

    def test_quantite_minimale_de_commande(self):
        self._predictions(Decimal('0.2'))
        self.produit.qte_min_commande = 50
        self.produit.save()
        # besoin = 0,2 × 37 + 5 − 10 = 2,4 → arrondi 3 → relevé au minimum de 50
        self.assertEqual(calculer_reappro(self.produit)['quantite_suggeree'], Decimal(50))

    def test_gros_consommateur_avec_seuil_bas_suggere(self):
        # L'ancienne formule (seuil × 2 − stock) ne suggérait rien ici
        self._predictions(5)
        self.assertGreater(calculer_reappro(self.produit)['quantite_suggeree'], 0)

    def test_confiance_exprimee_en_fraction(self):
        PredictionStock.objects.create(produit=self.produit, date_cible=timezone.localdate() + timedelta(days=30),
                                       quantite_prevue=30, confiance=0.82, modele_utilise='prophet')
        self.assertEqual(calculer_reappro(self.produit)['confiance'], 82)

    def test_stock_suffisant_rien_a_commander(self):
        self._predictions(Decimal('0.1'))
        mettre_en_stock(creer_produit(self.ent), self.entrepot, 0)
        self.assertEqual(calculer_reappro(self.produit)['quantite_suggeree'], 0)

    def test_moyenne_des_sorties_sans_prediction(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 7, 'entrepot': self.entrepot.pk,
        })
        r = calculer_reappro(self.produit)
        self.assertEqual(r['source'], 'historique')
        self.assertEqual(r['conso_jour'], Decimal(7) / 28)
        self.assertGreater(r['quantite_suggeree'], 0)

    def test_page_suggestions_et_lien_commander(self):
        self._predictions(2)
        self.connecter('responsable_achat')
        response = self.client.get(reverse('responsable_achat:suggestions_list'))
        self.assertEqual([s['produit'] for s in response.context['suggestions_urgentes']], [self.produit])
        # Le lien « Commander » pré-remplit le bon de commande
        html = self.client.get(reverse('responsable_achat:boncommande_create'),
                               {'produit': self.produit.pk, 'qte': '69'}).content.decode()
        self.assertIn('value="69"', html)
        self.assertRegex(html, rf'value="{self.produit.pk}"[^>]*\s+selected')


class SeuilsApresVariationTests(EntrepriseTestCase):

    def test_reception_de_commande_clot_l_alerte_de_rupture(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 10, 'entrepot': self.entrepot.pk,
        })
        self.assertTrue(Alerte.objects.filter(type_alerte='rupture', lue=False).exists())
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur, statut='envoye',
                                        entrepot_destination=self.entrepot)
        ligne = LigneCommande.objects.create(bon_commande=bc, produit=self.produit, quantite_commandee=20,
                                             prix_unitaire_ht=100)
        self.connecter('responsable_achat')
        self.client.post(reverse('responsable_achat:boncommande_reception', args=[bc.pk]),
                         {f'recu_{ligne.pk}': '20', 'entrepot': self.entrepot.pk})
        self.assertFalse(Alerte.objects.filter(lue=False).exists())

    def test_reception_partielle_remplace_rupture_par_seuil_bas(self):
        Alerte.objects.create(produit=self.produit, entrepot=self.entrepot, type_alerte='rupture',
                              priorite='critique', message='x')
        Mouvement.objects.all().delete()
        stock = self.produit.stocks.get()
        stock.quantite = 0
        stock.save()
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur, statut='envoye',
                                        entrepot_destination=self.entrepot)
        ligne = LigneCommande.objects.create(bon_commande=bc, produit=self.produit, quantite_commandee=20,
                                             prix_unitaire_ht=100)
        self.connecter('responsable_achat')
        self.client.post(reverse('responsable_achat:boncommande_reception', args=[bc.pk]),
                         {f'recu_{ligne.pk}': '3', 'entrepot': self.entrepot.pk})
        ouvertes = list(Alerte.objects.filter(lue=False).values_list('type_alerte', flat=True))
        self.assertEqual(ouvertes, ['seuil_bas'])

    def test_validation_d_inventaire_cree_l_alerte(self):
        session = InventaireSession.objects.create(entrepot=self.entrepot)
        LigneInventaire.objects.create(session=session, produit=self.produit, quantite_theorique=10, quantite_comptee=2)
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:inventaire_valider', args=[session.pk]))
        self.assertTrue(Alerte.objects.filter(produit=self.produit, type_alerte='seuil_bas', lue=False).exists())

    def test_api_mobile_cree_l_alerte(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        token = RefreshToken.for_user(self.users['magasinier']).access_token
        response = self.client.post('/api/v1/mouvements/rapide/', json.dumps({
            'produit_id': str(self.produit.pk), 'type_mouvement': 'sortie', 'quantite': 8,
            'entrepot_id': str(self.entrepot.pk),
        }), content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Alerte.objects.filter(produit=self.produit, lue=False).exists())

    def test_creation_produit_avec_stock_initial_sous_le_seuil(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:produit_ajouter'), {
            'nom': 'Lait', 'sku': 'LAIT-1', 'unite': 'unite', 'seuil_alerte': '10', 'prix_unitaire': '500',
            'stock_initial': '4', 'entrepot_initial': self.entrepot.pk,
        })
        lait = self.produit.__class__.objects.get(sku='LAIT-1')
        self.assertEqual(lait.quantite_totale(), 4)
        self.assertTrue(Alerte.objects.filter(produit=lait, type_alerte='seuil_bas').exists())
        self.assertEqual(Mouvement.objects.get(produit=lait).type_mouvement, TypeMouvement.ENTREE)


class EcranIaAdminTests(EntrepriseTestCase):

    def test_une_prediction_par_produit_unites_explicites(self):
        ancienne = PredictionStock.objects.create(produit=self.produit, date_cible=timezone.localdate() + timedelta(days=29),
                                                  quantite_prevue=999, confiance=50, modele_utilise='prophet')
        PredictionStock.objects.filter(pk=ancienne.pk).update(created_at=timezone.now() - timedelta(days=1))
        PredictionStock.objects.create(produit=self.produit, date_cible=timezone.localdate() + timedelta(days=30),
                                       quantite_prevue=60, borne_inferieure=45, borne_superieure=75,
                                       confiance=0.85, modele_utilise='prophet')
        self.connecter('admin_ent')
        response = self.client.get(reverse('admin_entreprise:ia_dashboard'))
        self.assertEqual(response.context['nb_predictions'], 1)  # l'ancienne prédiction n'est pas recomptée
        p = response.context['predictions'][0]
        self.assertEqual((p.quantite_prevue, p.horizon, p.conso_jour, p.confiance_pct), (60, 30, 2, 85))
        self.assertEqual(p.a_commander, calculer_reappro(self.produit)['quantite_suggeree'])
        self.assertContains(response, '/ jour')
        csv = self.client.get(reverse('admin_entreprise:exports'), {'type': 'ia'}).content.decode()
        self.assertIn('Consommation / jour', csv)

