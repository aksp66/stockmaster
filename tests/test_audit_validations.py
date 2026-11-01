"""Journal d'audit des actions sensibles, garde-fous et confirmations (super admin et autres rôles)."""
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.core.models import AuditLog, TypeAction
from apps.stock.models import BonCommande, LigneCommande

from .base import EntrepriseTestCase, creer_entreprise, creer_utilisateur


class SuperAdminTests(EntrepriseTestCase):

    def setUp(self):
        self.sa = creer_utilisateur('super_admin')
        self.autre_sa = creer_utilisateur('super_admin')
        self.client.force_login(self.sa)

    def test_actions_journalisees_avec_etat_avant_apres(self):
        ent = creer_entreprise('B', active=False)
        self.client.post(reverse('superadmin:activer_entreprise', args=[ent.pk]))
        self.client.post(reverse('superadmin:desactiver_utilisateur', args=[self.users['comptable'].pk]))
        self.client.post(reverse('superadmin:changer_role', args=[self.users['auditeur'].pk]), {'role': 'comptable'})
        self.client.post(reverse('superadmin:supprimer_entreprise', args=[ent.pk]))
        types = list(AuditLog.objects.order_by('created_at').values_list('type_action', flat=True))
        self.assertEqual(types, [TypeAction.ACTIVATION_ENT, TypeAction.DESACTIVATION_USER, TypeAction.CHANGEMENT_ROLE,
                                 TypeAction.SUPPRESSION_ENT])
        activation = AuditLog.objects.get(type_action=TypeAction.ACTIVATION_ENT)
        self.assertEqual((activation.donnees_avant, activation.donnees_apres, activation.utilisateur),
                         ({'est_active': False}, {'est_active': True}, self.sa))
        self.assertTrue(activation.ip_address)

    def test_page_des_logs_affiche_et_filtre(self):
        ent = creer_entreprise('Filtrée', active=False)
        self.client.post(reverse('superadmin:activer_entreprise', args=[ent.pk]))
        self.client.post(reverse('superadmin:desactiver_utilisateur', args=[self.users['auditeur'].pk]))
        page = self.client.get(reverse('superadmin:logs'))
        self.assertContains(page, 'Filtrée')
        self.assertEqual(len(page.context['logs']), 2)
        filtre = self.client.get(reverse('superadmin:logs'), {'type_action': 'desactivation'})
        self.assertEqual([log.type_action for log in filtre.context['logs']], [TypeAction.DESACTIVATION_USER])
        recherche = self.client.get(reverse('superadmin:logs'), {'q': 'Filtrée'})
        self.assertEqual(len(recherche.context['logs']), 1)
        export = self.client.get(reverse('superadmin:logs'), {'export': 'csv'})
        self.assertIn('Filtrée', export.content.decode('utf-8-sig'))

    def test_dernier_super_admin_protege(self):
        self.autre_sa.is_active = False
        self.autre_sa.save()
        # Le seul super admin actif ne peut être ni désactivé ni rétrogradé
        self.client.post(reverse('superadmin:desactiver_utilisateur', args=[self.sa.pk]))
        self.client.post(reverse('superadmin:changer_role', args=[self.sa.pk]), {'role': 'admin_ent'})
        self.sa.refresh_from_db()
        self.assertEqual((self.sa.is_active, self.sa.role), (True, 'super_admin'))

    def test_desactivation_d_un_autre_super_admin_permise_et_journalisee(self):
        self.client.post(reverse('superadmin:desactiver_utilisateur', args=[self.autre_sa.pk]))
        self.autre_sa.refresh_from_db()
        self.assertFalse(self.autre_sa.is_active)
        self.assertEqual(AuditLog.objects.get().type_action, TypeAction.DESACTIVATION_USER)

    def test_changement_de_role_garde_fous(self):
        self.client.post(reverse('superadmin:changer_role', args=[self.sa.pk]), {'role': 'comptable'})  # son propre rôle
        sans_ent = creer_utilisateur('super_admin')
        self.client.post(reverse('superadmin:changer_role', args=[sans_ent.pk]), {'role': 'comptable'})  # sans entreprise
        self.client.post(reverse('superadmin:changer_role', args=[self.users['comptable'].pk]), {'role': 'pirate'})
        self.assertEqual(AuditLog.objects.count(), 0)
        self.assertEqual(Utilisateur.objects.get(pk=sans_ent.pk).role, 'super_admin')

    def test_actions_en_post_uniquement(self):
        ent = creer_entreprise('C')
        for nom, args in [('supprimer_entreprise', [ent.pk]), ('changer_role', [self.users['comptable'].pk])]:
            self.assertEqual(self.client.get(reverse(f'superadmin:{nom}', args=args)).status_code, 405, nom)

    def test_confirmation_sur_les_boutons_destructeurs(self):
        ent = creer_entreprise('D')
        html = self.client.get(reverse('superadmin:detail_entreprise', args=[ent.pk])).content.decode()
        self.assertIn('data-confirm=', html)
        self.assertIn('js/stockmaster.js', html)


class JournalDesAutresRolesTests(EntrepriseTestCase):

    def test_admin_entreprise_utilisateurs(self):
        self.connecter('admin_ent')
        cible = self.users['magasinier']
        self.client.post(reverse('admin_entreprise:desactiver_utilisateur', args=[cible.pk]))
        self.client.post(reverse('admin_entreprise:modifier_utilisateur', args=[cible.pk]),
                         {'first_name': 'Mike', 'last_name': 'Mag', 'role': 'gestionnaire'})
        self.client.post(reverse('admin_entreprise:supprimer_utilisateur', args=[cible.pk]))
        types = list(AuditLog.objects.order_by('created_at').values_list('type_action', flat=True))
        self.assertEqual(types, [TypeAction.DESACTIVATION_USER, TypeAction.CHANGEMENT_ROLE, TypeAction.SUPPRESSION_USER])
        self.assertEqual(AuditLog.objects.filter(entreprise=self.ent).count(), 3)

    def test_dernier_admin_de_l_entreprise_protege(self):
        admin = self.users['admin_ent']
        autre_admin = creer_utilisateur('admin_ent', self.ent)
        self.client.force_login(admin)
        self.client.post(reverse('admin_entreprise:desactiver_utilisateur', args=[autre_admin.pk]))  # il en reste un
        self.assertFalse(Utilisateur.objects.get(pk=autre_admin.pk).is_active)
        # Un super admin tente de retirer le seul admin restant
        self.client.force_login(creer_utilisateur('super_admin', self.ent))
        self.client.post(reverse('admin_entreprise:supprimer_utilisateur', args=[admin.pk]))
        self.client.post(reverse('admin_entreprise:desactiver_utilisateur', args=[admin.pk]))
        self.assertTrue(Utilisateur.objects.filter(pk=admin.pk, is_active=True).exists())

    def test_theme_et_parametres_journalises(self):
        self.connecter('admin_ent')
        self.client.post(reverse('admin_entreprise:parametres'), {'section': 'apparence', 'theme': 'rubis'})
        log = AuditLog.objects.get(type_action=TypeAction.PARAMETRES)
        self.assertEqual((log.donnees_avant, log.donnees_apres), ({'theme': 'orange'}, {'theme': 'rubis'}))

    def test_archivage_produit_et_bon_de_commande_journalises(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:produit_delete', args=[self.produit.pk]))
        self.assertTrue(AuditLog.objects.filter(type_action=TypeAction.SUPPRESSION_PRODUIT).exists())
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur)
        LigneCommande.objects.create(bon_commande=bc, produit=self.produit, quantite_commandee=5, prix_unitaire_ht=100)
        self.connecter('responsable_achat')
        self.client.post(reverse('responsable_achat:boncommande_envoyer', args=[bc.pk]))
        self.client.post(reverse('responsable_achat:boncommande_annuler', args=[bc.pk]))
        types = list(AuditLog.objects.filter(type_action__in=[TypeAction.VALIDATION_BC, TypeAction.ANNULATION_BC])
                     .order_by('created_at').values_list('type_action', flat=True))
        self.assertEqual(types, [TypeAction.VALIDATION_BC, TypeAction.ANNULATION_BC])

    def test_changement_de_statut_en_get_refuse(self):
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur)
        self.connecter('responsable_achat')
        reponse = self.client.get(reverse('responsable_achat:boncommande_statut', args=[bc.pk, 'annule']))
        self.assertEqual(reponse.status_code, 405)

    def test_confirmations_presentes_dans_les_espaces(self):
        self.connecter('admin_ent')
        html = self.client.get(reverse('admin_entreprise:utilisateurs')).content.decode()
        self.assertIn('data-confirm=', html)
        self.assertNotIn('onsubmit="return confirm(', html)
        self.connecter('responsable_achat')
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur)
        LigneCommande.objects.create(bon_commande=bc, produit=self.produit, quantite_commandee=5, prix_unitaire_ht=100)
        html = self.client.get(reverse('responsable_achat:boncommande_detail', args=[bc.pk])).content.decode()
        self.assertIn('data-confirm=', html)
