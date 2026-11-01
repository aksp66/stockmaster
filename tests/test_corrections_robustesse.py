"""Non-régression des défauts trouvés par le robot de parcours (étape 7)."""
import json
from decimal import Decimal

from django.urls import reverse

from apps.stock.models import (
    Alerte, BonCommande, Fournisseur, InventaireSession, LigneCommande, LigneInventaire, Mouvement, Produit, Stock,
)

from .base import EntrepriseTestCase, quantite_en_stock


class FormulaireProduitTests(EntrepriseTestCase):

    def setUp(self):
        self.connecter('gestionnaire')

    def _creer(self, **champs):
        donnees = {'nom': 'Lait', 'sku': 'LAIT-1', 'unite': 'unite', 'seuil_alerte': '5', 'prix_unitaire': '500'}
        donnees.update(champs)
        return self.client.post(reverse('gestionnaire:produit_ajouter'), donnees)

    def test_formulaire_vide_refuse_sans_erreur_serveur(self):
        reponse = self.client.post(reverse('gestionnaire:produit_ajouter'), {})
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(Produit.objects.count(), 1)
        reponse = self.client.post(reverse('gestionnaire:produit_edit', args=[self.produit.pk]), {})
        self.assertEqual(reponse.status_code, 302)
        self.produit.refresh_from_db()
        self.assertTrue(self.produit.nom)  # le nom n'a pas été effacé

    def test_nombres_invalides_refuses(self):
        for champ, valeur in [('prix_unitaire', 'abc'), ('seuil_alerte', '-3'), ('prix_vente', 'NaN'),
                              ('delai_reappro', 'x'), ('qte_min_commande', '0'), ('prix_unitaire', '1e30')]:
            self.assertEqual(self._creer(**{champ: valeur}).status_code, 302, champ)
        self.assertFalse(Produit.objects.filter(sku='LAIT-1').exists())

    def test_virgule_decimale_acceptee(self):
        self._creer(prix_unitaire='1 250,50', seuil_alerte='2,5')
        produit = Produit.objects.get(sku='LAIT-1')
        self.assertEqual((produit.prix_unitaire, produit.seuil_alerte), (Decimal('1250.50'), Decimal('2.5')))

    def test_code_barres_deja_pris_refuse(self):
        self.produit.code_barres = '6111'
        self.produit.save()
        self._creer(code_barres='6111')
        self.assertFalse(Produit.objects.filter(sku='LAIT-1').exists())

    def test_modification_valide(self):
        self.client.post(reverse('gestionnaire:produit_edit', args=[self.produit.pk]), {
            'nom': 'Riz premium', 'unite': 'kg', 'seuil_alerte': '8', 'prix_unitaire': '900', 'est_actif': 'on'})
        self.produit.refresh_from_db()
        self.assertEqual((self.produit.nom, self.produit.unite_mesure, self.produit.seuil_alerte),
                         ('Riz premium', 'kg', 8))


class ScanGestionnaireTests(EntrepriseTestCase):

    def test_corps_invalide_et_roles(self):
        url = reverse('gestionnaire:api_scan')
        self.connecter('gestionnaire')
        self.assertEqual(self.client.post(url, 'pas du json', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(url, '[1, 2]', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(url, json.dumps({'code': self.produit.sku}),
                                          content_type='application/json').json()['found'], True)
        self.connecter('comptable')  # n'avait aucun contrôle de rôle
        self.assertNotEqual(self.client.post(url, json.dumps({'code': self.produit.sku}),
                                             content_type='application/json').status_code, 200)


class AlertesEtMouvementsTests(EntrepriseTestCase):

    def test_page_des_mouvements_avec_un_mouvement_sans_auteur(self):
        Mouvement.objects.create(type_mouvement='entree', produit=self.produit, quantite=1, entrepot_destination=self.entrepot)
        self.connecter('gestionnaire')
        self.assertEqual(self.client.get(reverse('gestionnaire:mouvements')).status_code, 200)  # 500 auparavant

    def test_alertes_de_la_fiche_produit(self):
        Alerte.objects.create(produit=self.produit, entrepot=self.entrepot, type_alerte='rupture', priorite='critique',
                              message='x')
        self.connecter('gestionnaire')
        html = self.client.get(reverse('gestionnaire:produit_detail', args=[self.produit.pk])).content.decode()
        self.assertIn('Acquitter', html)


class AchatsTests(EntrepriseTestCase):

    def setUp(self):
        self.connecter('responsable_achat')

    def test_champs_fournisseur_enregistres(self):
        self.client.post(reverse('responsable_achat:fournisseur_create'), {
            'nom': 'Agro SARL', 'code': 'AGR-1', 'site_web': 'https://agro.example', 'code_postal': '00228', 'ville': 'Lomé',
            'delai_paiement': '45', 'remise': '7,5', 'devise': 'EUR', 'delai_livraison': '4'})
        f = Fournisseur.objects.get(nom='Agro SARL')
        self.assertEqual((f.code, f.ville, f.delai_paiement, f.remise, f.devise, f.delai_moyen_jours),
                         ('AGR-1', 'Lomé', 45, Decimal('7.5'), 'EUR', 4))
        html = self.client.get(reverse('responsable_achat:fournisseur_edit', args=[f.pk])).content.decode()
        self.assertIn('value="Lomé"', html)

    def test_valeurs_invalides_du_fournisseur_ramenees_a_des_valeurs_sures(self):
        self.client.post(reverse('responsable_achat:fournisseur_create'), {
            'nom': 'X', 'delai_paiement': 'abc', 'remise': '500', 'devise': 'BTC'})
        f = Fournisseur.objects.get(nom='X')
        self.assertEqual((f.delai_paiement, f.remise, f.devise), (30, Decimal(100), 'XOF'))

    def test_nom_de_fournisseur_obligatoire(self):
        avant = Fournisseur.objects.count()
        self.assertEqual(self.client.post(reverse('responsable_achat:fournisseur_create'), {}).status_code, 200)
        self.assertEqual(Fournisseur.objects.count(), avant)
        self.assertEqual(self.client.post(reverse('responsable_achat:fournisseur_edit', args=[self.fournisseur.pk]), {}).status_code, 302)
        self.fournisseur.refresh_from_db()
        self.assertTrue(self.fournisseur.nom)

    def test_remise_de_ligne_conservee_et_date_d_envoi(self):
        self.client.post(reverse('responsable_achat:boncommande_create'), {
            'fournisseur': self.fournisseur.pk, 'action': 'envoyer',
            'lignes[0][produit]': self.produit.pk, 'lignes[0][quantite]': '10',
            'lignes[0][prix_unitaire]': '1000', 'lignes[0][remise]': '10'})
        bc = BonCommande.objects.get()
        ligne = LigneCommande.objects.get(bon_commande=bc)
        self.assertEqual((ligne.prix_unitaire_ht, ligne.remise), (Decimal('900.00'), Decimal('10.00')))
        self.assertEqual(bc.statut, 'envoye')
        self.assertIsNotNone(bc.date_envoi)


class OptionsDInventaireTests(EntrepriseTestCase):

    def test_options_enregistrees_a_la_creation(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:inventaire_creer'), {'entrepot': self.entrepot.pk, 'masquer_stock': 'on'})
        session = InventaireSession.objects.get()
        self.assertEqual((session.masquer_stock, session.ajustement_auto), (True, False))  # case « ajustement » décochée

    def test_sans_ajustement_automatique_le_stock_ne_change_pas(self):
        session = InventaireSession.objects.create(entrepot=self.entrepot, ajustement_auto=False)
        LigneInventaire.objects.create(session=session, produit=self.produit, quantite_theorique=10, quantite_comptee=3)
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:inventaire_valider', args=[session.pk]))
        session.refresh_from_db()
        self.assertEqual(session.statut, 'valide')
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)
        self.assertFalse(Mouvement.objects.filter(reference=f'INVENTAIRE-{session.pk}').exists())

    def test_avec_ajustement_automatique_le_stock_est_aligne(self):
        session = InventaireSession.objects.create(entrepot=self.entrepot)
        LigneInventaire.objects.create(session=session, produit=self.produit, quantite_theorique=10, quantite_comptee=3)
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:inventaire_valider', args=[session.pk]))
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 3)

    def test_comptage_a_l_aveugle_cache_la_quantite_attendue(self):
        session = InventaireSession.objects.create(entrepot=self.entrepot, masquer_stock=True)
        LigneInventaire.objects.create(session=session, produit=self.produit, quantite_theorique=10)
        self.connecter('magasinier')
        html = self.client.get(reverse('magasinier:inventaire_detail', args=[session.pk])).content.decode()
        self.assertNotIn('Attendu', html)


class UtilisateursTests(EntrepriseTestCase):

    def test_modification_sans_nom_refusee(self):
        self.connecter('admin_ent')
        cible = self.users['comptable']
        reponse = self.client.post(reverse('admin_entreprise:modifier_utilisateur', args=[cible.pk]), {})
        self.assertEqual(reponse.status_code, 302)
        cible.refresh_from_db()
        self.assertEqual(cible.role, 'comptable')


class AnalyseIaTests(EntrepriseTestCase):
    """Le lancement de l'analyse IA ne doit jamais produire d'erreur 500, que le broker réponde ou non."""

    def test_broker_injoignable(self):
        from unittest import mock
        from apps.core.models import AuditLog
        self.connecter('admin_ent')
        with mock.patch('apps.admin_entreprise.views.current_app.control.ping', side_effect=ConnectionRefusedError):
            reponse = self.client.post(reverse('admin_entreprise:ia_lancer'), follow=True)
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "pas disponible")
        self.assertFalse(AuditLog.objects.filter(type_action='ia_analyse').exists())  # rien n'a été lancé

    def test_broker_disponible(self):
        from unittest import mock
        from apps.core.models import AuditLog
        self.connecter('admin_ent')
        with mock.patch('apps.admin_entreprise.views.current_app.control.ping', return_value=[{}]), \
                mock.patch('apps.admin_entreprise.views.analyser_entreprise_immediate.delay') as lancer:
            reponse = self.client.post(reverse('admin_entreprise:ia_lancer'), follow=True)
        lancer.assert_called_once_with(str(self.ent.pk))
        self.assertContains(reponse, "Analyse IA déclenchée")
        self.assertTrue(AuditLog.objects.filter(type_action='ia_analyse').exists())
