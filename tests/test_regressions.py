"""Régressions corrigées lors de la vérification des espaces (octobre 2026)."""
import json
from decimal import Decimal

from django.urls import reverse

from apps.stock.models import Mouvement

from .base import EntrepriseTestCase, creer_produit, quantite_en_stock


class GestionnaireRegressionsTests(EntrepriseTestCase):

    def setUp(self):
        self.connecter('gestionnaire')

    def _modifier_produit(self, **extra):
        donnees = {
            'nom': self.produit.nom, 'unite': 'kg', 'seuil_alerte': '5', 'prix_unitaire': '1000',
            'fournisseur': self.fournisseur.pk, 'delai_reappro': '7', 'qte_min_commande': '1',
            **extra,
        }
        self.client.post(reverse('gestionnaire:produit_edit', args=[self.produit.pk]), donnees)
        self.produit.refresh_from_db()

    def test_modifier_un_produit_ne_le_desactive_pas(self):
        self._modifier_produit(est_actif='on')
        self.assertTrue(self.produit.est_actif)
        self.assertEqual(self.produit.unite_mesure, 'kg')
        self.assertEqual(self.produit.fournisseur_principal, self.fournisseur)

    def test_formulaire_de_modification_preselectionne_unite_et_fournisseur(self):
        self.produit.unite_mesure = 'kg'
        self.produit.fournisseur_principal = self.fournisseur
        self.produit.save()
        html = self.client.get(reverse('gestionnaire:produit_edit', args=[self.produit.pk])).content.decode()
        self.assertRegex(html, r'value="kg"\s+selected')
        self.assertRegex(html, rf'value="{self.fournisseur.pk}"\s+selected')
        self.assertRegex(html, r'name="est_actif"\s+checked')

    def test_prix_d_achat_saisi_conserve_pour_la_valorisation(self):
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'entree', 'quantite': 3,
            'entrepot': self.entrepot.pk, 'prix_unitaire_achat': '750', 'motif': 'Réassort',
            'reference_document': 'BL-42', 'date_mouvement': '2026-10-01T09:30',
        })
        mouv = Mouvement.objects.get()
        self.assertEqual(mouv.prix_unitaire_snapshot, Decimal('750'))
        self.assertEqual((mouv.note, mouv.reference), ('Réassort', 'BL-42'))
        self.assertEqual(mouv.date_mouvement.date().isoformat(), '2026-10-01')
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 13)

    def test_fiche_produit_graphique_et_stock_apres_mouvement(self):
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 4, 'entrepot': self.entrepot.pk,
        })
        response = self.client.get(reverse('gestionnaire:produit_detail', args=[self.produit.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.context['data_stock'])[-1], 6.0)
        self.assertEqual(response.context['mouvements'][0].stock_apres, 6)
        self.assertNotIn('const labels  = ;', response.content.decode())

    def test_liste_produits_compteurs_et_filtre_rupture(self):
        vide = creer_produit(self.ent, nom="Sucre (rupture)")
        response = self.client.get(reverse('gestionnaire:produits'), {'stock': 'rupture'})
        self.assertEqual(response.context['nb_rupture'], 1)
        self.assertEqual(list(response.context['produits']), [vide])

    def test_mouvements_presentent_l_entrepot(self):
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 1, 'entrepot': self.entrepot.pk,
        })
        self.assertContains(self.client.get(reverse('gestionnaire:mouvements')), self.entrepot.nom)


class MagasinierRegressionsTests(EntrepriseTestCase):

    def setUp(self):
        self.connecter('magasinier')

    def test_page_alertes_liste_les_produits_sous_le_seuil(self):
        creer_produit(self.ent, nom="Lait (rupture)")
        response = self.client.get(reverse('magasinier:alertes'))
        self.assertEqual(response.context['nb_rupture'], 1)
        self.assertContains(response, "Lait (rupture)")

    def test_motif_du_mouvement_rapide_enregistre(self):
        self.client.post(reverse('magasinier:mouvement_rapide'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 2,
            'entrepot': self.entrepot.pk, 'motif': 'Casse',
        })
        self.assertEqual(Mouvement.objects.get().note, 'Casse')

    def test_preferences_entrepot_et_type_par_defaut(self):
        self.client.post(reverse('magasinier:parametres'), {'entrepot_defaut': self.entrepot.pk, 'type_defaut': 'sortie'})
        response = self.client.get(reverse('magasinier:mouvement_rapide'))
        self.assertEqual(response.context['entrepot_defaut_id'], self.entrepot.pk)
        self.assertEqual(response.context['type_initial'], 'sortie')


class AchatsEtAuditRegressionsTests(EntrepriseTestCase):

    def test_suggestions_d_achat_sans_erreur(self):
        self.connecter('responsable_achat')
        self.assertEqual(self.client.get(reverse('responsable_achat:suggestions_list')).status_code, 200)

    def test_journal_d_audit_affiche_le_type_d_action(self):
        from apps.core.models import AuditLog, TypeAction
        AuditLog.objects.create(utilisateur=self.users['admin_ent'], entreprise=self.ent,
                                type_action=TypeAction.CREATION_PRODUIT, description="Produit Riz créé")
        self.connecter('auditeur')
        response = self.client.get(reverse('auditeur:logs'))
        self.assertContains(response, "Création produit")
        self.assertContains(response, "Produit Riz créé")
