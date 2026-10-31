"""
Soumission de chaque formulaire secondaire avec les noms de champs de son template,
et vérification de l'effet en base.
"""
import json
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import InvitationToken, Utilisateur
from apps.entreprises.models import Entreprise, ParametresEntreprise
from apps.stock.models import (
    Alerte, Categorie, Emplacement, Entrepot, InventaireSession, LigneInventaire, Mouvement, Produit,
)

from .base import (
    EntrepriseTestCase, creer_entreprise, creer_entrepot, creer_produit, creer_utilisateur, mettre_en_stock,
    quantite_en_stock,
)


class GestionnaireFormulairesTests(EntrepriseTestCase):

    def setUp(self):
        self.connecter('gestionnaire')

    def test_categories_ajout_modification_suppression(self):
        url = reverse('gestionnaire:categories')
        self.client.post(url, {'action': 'ajouter', 'nom': 'Boissons'})
        parent = Categorie.objects.get(nom='Boissons')
        self.client.post(url, {'action': 'ajouter', 'nom': 'Jus', 'parent': parent.pk})
        jus = Categorie.objects.get(nom='Jus')
        self.assertEqual(jus.parent, parent)
        self.client.post(url, {'action': 'modifier', 'categorie_id': jus.pk, 'nom': 'Jus de fruits', 'parent': ''})
        jus.refresh_from_db()
        self.assertEqual((jus.nom, jus.parent), ('Jus de fruits', None))
        self.client.post(url, {'action': 'supprimer', 'categorie_id': jus.pk})
        self.assertFalse(Categorie.objects.filter(pk=jus.pk).exists())

    def test_categorie_avec_produits_non_supprimee(self):
        cat = Categorie.objects.create(nom='Riz', entreprise=self.ent)
        self.produit.categorie = cat
        self.produit.save()
        self.client.post(reverse('gestionnaire:categories'), {'action': 'supprimer', 'categorie_id': cat.pk})
        self.assertTrue(Categorie.objects.filter(pk=cat.pk).exists())

    def test_emplacements_creation_doublon_suppression(self):
        url = reverse('gestionnaire:emplacements')
        donnees = {'action': 'creer', 'entrepot': self.entrepot.pk, 'code': 'A-01', 'description': 'Allée A'}
        self.client.post(url, donnees)
        self.client.post(url, donnees)  # doublon refusé
        self.assertEqual(Emplacement.objects.filter(code='A-01').count(), 1)
        empl = Emplacement.objects.get()
        self.client.post(url, {'action': 'supprimer', 'emplacement_id': empl.pk})
        self.assertFalse(Emplacement.objects.exists())

    def test_transfert(self):
        annexe = creer_entrepot(self.ent, "Annexe")
        url = reverse('gestionnaire:transfert')
        self.assertEqual(self.client.get(url).status_code, 200)
        base = {'produit': self.produit.pk, 'entrepot_source': self.entrepot.pk,
                'entrepot_destination': annexe.pk, 'note': 'Rééquilibrage'}
        self.client.post(url, {**base, 'quantite': '4'})
        self.assertEqual((quantite_en_stock(self.produit, self.entrepot), quantite_en_stock(self.produit, annexe)), (6, 4))
        # Quantité négative ou nulle, entrepôts identiques : refusés
        self.client.post(url, {**base, 'quantite': '-5'})
        self.client.post(url, {**base, 'quantite': '1', 'entrepot_destination': self.entrepot.pk})
        self.assertEqual(Mouvement.objects.count(), 1)
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 6)

    def test_ajustement_surplus_et_manque(self):
        url = reverse('gestionnaire:mouvement_form')
        base = {'produit': self.produit.pk, 'type_mouvement': 'ajustement', 'entrepot': self.entrepot.pk}
        self.client.post(url, {**base, 'quantite': '3', 'sens_ajustement': 'surplus'})
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 13)
        self.client.post(url, {**base, 'quantite': '5', 'sens_ajustement': 'manque'})
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 8)

    def test_mouvement_sans_entrepot_refuse(self):
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'entree', 'quantite': '2', 'entrepot': '',
        })
        self.assertFalse(Mouvement.objects.exists())

    def test_desactivation_produit(self):
        self.client.post(reverse('gestionnaire:produit_delete', args=[self.produit.pk]))
        self.produit.refresh_from_db()
        self.assertFalse(self.produit.est_actif)

    def _importer(self, contenu, **options):
        fichier = SimpleUploadedFile('produits.csv', contenu.encode('utf-8'), content_type='text/csv')
        return self.client.post(reverse('gestionnaire:produit_import'),
                                {'fichier': fichier, 'separateur': ',', 'doublon': 'ignorer', **options})

    def test_import_csv_point_virgule_et_colonnes_du_modele(self):
        Categorie.objects.create(nom='Épicerie', entreprise=self.ent)
        self._importer("sku;nom;prix_unitaire;seuil_alerte;unite_mesure;categorie;fournisseur_principal\n"
                       "IMP-1;Sucre 1 kg;750;5;kg;épicerie;Fournisseur SA\n"
                       "IMP-2;Sel;200;2;unite;;\n"
                       ";Sans SKU;1;1;unite;;\n"
                       "IMP-3;Huile;900;3;bidon;;\n", separateur=';')
        sucre = Produit.objects.get(sku='IMP-1')
        self.assertEqual((sucre.prix_unitaire, sucre.unite_mesure, sucre.categorie.nom, sucre.fournisseur_principal),
                         (Decimal('750'), 'kg', 'Épicerie', self.fournisseur))
        self.assertTrue(Produit.objects.filter(sku='IMP-2').exists())
        self.assertFalse(Produit.objects.filter(sku__in=['', 'IMP-3']).exists())  # lignes invalides rejetées

    def test_import_csv_doublons(self):
        sku = self.produit.sku
        self._importer(f"sku,nom,prix_unitaire\n{sku},Nouveau nom,1500\n")
        self.produit.refresh_from_db()
        self.assertNotEqual(self.produit.nom, 'Nouveau nom')  # ignoré par défaut
        self._importer(f"sku,nom,prix_unitaire\n{sku},Nouveau nom,1500\n", doublon='mettre_a_jour')
        self.produit.refresh_from_db()
        self.assertEqual((self.produit.nom, self.produit.prix_unitaire), ('Nouveau nom', Decimal('1500')))
        self._importer(f"sku,nom\nNEUF-1,Neuf\n{sku},Encore\n", doublon='erreur')
        self.assertFalse(Produit.objects.filter(sku='NEUF-1').exists())  # tout ou rien

    def test_import_mauvais_separateur_refuse(self):
        self._importer("sku;nom\nX-1;Produit\n", separateur=',')
        self.assertFalse(Produit.objects.filter(sku__in=['', 'X-1']).exists())

    def test_inventaire_creation_saisie_annulation(self):
        cat = Categorie.objects.create(nom='Riz', entreprise=self.ent)
        self.produit.categorie = cat
        self.produit.save()
        mettre_en_stock(creer_produit(self.ent, nom="Hors catégorie"), self.entrepot, 3)
        self.client.post(reverse('gestionnaire:inventaire_creer'), {
            'nom': 'Inventaire riz', 'entrepot': self.entrepot.pk, 'categorie': cat.pk, 'commentaire': 'Rayon A',
        })
        session = InventaireSession.objects.get()
        self.assertEqual(list(session.lignes.values_list('produit', flat=True)), [self.produit.pk])
        self.assertIn('Rayon A', session.note)
        ligne = session.lignes.get()
        self.client.post(reverse('gestionnaire:inventaire_saisie', args=[session.pk]),
                         {f'ligne_{ligne.pk}': '9', f'cmt_{ligne.pk}': 'Sac abîmé'})
        ligne.refresh_from_db()
        self.assertEqual((ligne.quantite_comptee, ligne.note), (9, 'Sac abîmé'))
        self.client.post(reverse('gestionnaire:inventaire_session_annuler', args=[session.pk]))
        session.refresh_from_db()
        self.assertEqual(session.statut, 'annule')

    def test_acquittement_des_alertes(self):
        a1 = Alerte.objects.create(produit=self.produit, type_alerte='seuil_bas', priorite='haute', message='x')
        Alerte.objects.create(produit=self.produit, type_alerte='rupture', priorite='critique', message='y')
        self.client.post(reverse('gestionnaire:alerte_acquitter', args=[a1.pk]))
        a1.refresh_from_db()
        self.assertTrue(a1.lue)
        self.client.post(reverse('gestionnaire:alertes_acquitter_toutes'))
        self.assertFalse(Alerte.objects.filter(lue=False).exists())


class AdminEntrepriseFormulairesTests(EntrepriseTestCase):

    def setUp(self):
        self.admin = self.connecter('admin_ent')

    def test_parametres_enregistres_et_utilises(self):
        url = reverse('admin_entreprise:parametres')
        self.client.post(url, {'section': 'notifications', 'rapport_hebdo': 'on'})
        self.client.post(url, {'section': 'seuils', 'seuil_defaut': '25', 'jours_expiration': '45'})
        p = ParametresEntreprise.pour(self.ent)
        self.assertEqual((p.alertes_email, p.rapport_hebdo, p.ia_email, p.seuil_alerte_defaut, p.jours_alerte_expiration),
                         (False, True, False, Decimal('25'), 45))
        self.assertContains(self.client.get(url), 'name="seuil_defaut" value="25')
        # Valeurs invalides refusées
        self.client.post(url, {'section': 'seuils', 'seuil_defaut': '-1', 'jours_expiration': '0'})
        self.assertEqual(ParametresEntreprise.pour(self.ent).jours_alerte_expiration, 45)
        # Le seuil par défaut est proposé à la création d'un produit
        self.connecter('gestionnaire')
        self.assertContains(self.client.get(reverse('gestionnaire:produit_ajouter')), 'name="seuil_alerte" value="25')

    def test_invitation_puis_activation(self):
        self.client.post(reverse('admin_entreprise:ajouter_utilisateur'), {
            'email': 'nouveau@test.local', 'first_name': 'Kofi', 'last_name': 'Mensah', 'role': 'magasinier',
        })
        invite = Utilisateur.objects.get(email='nouveau@test.local')
        self.assertFalse(invite.is_active)
        self.assertEqual(len(mail.outbox), 1)
        token = InvitationToken.objects.get(user=invite).token
        self.client.logout()
        self.client.post(reverse('accounts:accept_invitation', args=[token]),
                         {'password1': 'Stock-Master-2026!', 'password2': 'Stock-Master-2026!'})
        invite.refresh_from_db()
        self.assertTrue(invite.is_active and invite.check_password('Stock-Master-2026!'))

    def test_role_interdit_refuse(self):
        self.client.post(reverse('admin_entreprise:ajouter_utilisateur'), {
            'email': 'x@test.local', 'first_name': 'X', 'last_name': 'Y', 'role': 'super_admin',
        })
        self.assertFalse(Utilisateur.objects.filter(email='x@test.local').exists())

    def test_modification_role_avec_email(self):
        cible = self.users['magasinier']
        self.client.post(reverse('admin_entreprise:modifier_utilisateur', args=[cible.pk]),
                         {'first_name': 'Ama', 'last_name': 'K', 'role': 'gestionnaire'})
        cible.refresh_from_db()
        self.assertEqual((cible.first_name, cible.role), ('Ama', 'gestionnaire'))
        self.assertEqual(len(mail.outbox), 1)

    def test_admin_ne_peut_ni_changer_son_role_ni_se_supprimer_ni_se_desactiver(self):
        self.client.post(reverse('admin_entreprise:modifier_utilisateur', args=[self.admin.pk]),
                         {'first_name': 'A', 'last_name': 'B', 'role': 'magasinier'})
        self.client.post(reverse('admin_entreprise:supprimer_utilisateur', args=[self.admin.pk]))
        self.client.post(reverse('admin_entreprise:desactiver_utilisateur', args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertEqual((self.admin.role, self.admin.is_active), ('admin_ent', True))

    def test_suppression_et_desactivation_d_un_utilisateur(self):
        cible = self.users['comptable']
        self.client.get(reverse('admin_entreprise:desactiver_utilisateur', args=[cible.pk]))  # GET sans effet
        cible.refresh_from_db()
        self.assertTrue(cible.is_active)
        self.client.post(reverse('admin_entreprise:desactiver_utilisateur', args=[cible.pk]))
        cible.refresh_from_db()
        self.assertFalse(cible.is_active)
        self.client.post(reverse('admin_entreprise:supprimer_utilisateur', args=[cible.pk]))
        self.assertFalse(Utilisateur.objects.filter(pk=cible.pk).exists())

    def test_fiche_entreprise(self):
        url = reverse('admin_entreprise:entreprise_edit')
        self.client.post(url, {'nom': 'Entreprise A2', 'pays': 'Togo', 'ville': 'Kara', 'taille': '10-50', 'nb_entrepots': '3'})
        self.ent.refresh_from_db()
        self.assertEqual((self.ent.nom, self.ent.ville, self.ent.nb_entrepots), ('Entreprise A2', 'Kara', 3))
        response = self.client.post(url, {'nom': 'Entreprise A3', 'nb_entrepots': ''})
        self.assertEqual(response.status_code, 302)  # plus d'erreur 500
        self.client.post(url, {'nom': '', 'nb_entrepots': '2'})
        self.ent.refresh_from_db()
        self.assertEqual(self.ent.nom, 'Entreprise A3')

    def test_entrepots_creation_modification_suppression(self):
        self.client.post(reverse('admin_entreprise:entrepot_ajouter'), {'nom': 'Dépôt Nord', 'ville': 'Kara'})
        nord = Entrepot.objects.get(nom='Dépôt Nord')
        self.assertEqual(nord.entreprise, self.ent)
        self.client.post(reverse('admin_entreprise:entrepot_modifier', args=[nord.pk]), {'nom': 'Dépôt Nord 2'})
        nord.refresh_from_db()
        self.assertEqual(nord.nom, 'Dépôt Nord 2')
        self.client.post(reverse('admin_entreprise:entrepot_supprimer', args=[nord.pk]))
        self.assertFalse(Entrepot.objects.filter(pk=nord.pk).exists())
        # Entrepôt avec du stock : désactivé, pas supprimé (plus d'erreur 500)
        response = self.client.post(reverse('admin_entreprise:entrepot_supprimer', args=[self.entrepot.pk]))
        self.assertEqual(response.status_code, 302)
        self.entrepot.refresh_from_db()
        self.assertFalse(self.entrepot.est_actif)

    def test_categorie_parent_d_une_autre_entreprise_ignore(self):
        etrangere = Categorie.objects.create(nom='Autre', entreprise=creer_entreprise('B'))
        self.client.post(reverse('admin_entreprise:categories'), {'nom': 'Sous-cat', 'parent': etrangere.pk})
        self.assertIsNone(Categorie.objects.get(nom='Sous-cat').parent)


class AchatsEtMagasinierFormulairesTests(EntrepriseTestCase):

    def test_fournisseur_creation_modification_desactivation(self):
        self.connecter('responsable_achat')
        self.client.post(reverse('responsable_achat:fournisseur_create'), {
            'nom': 'Togo Riz', 'contact_nom': 'M. Agbo', 'email': 'agbo@togoriz.tg', 'telephone': '+228 90',
            'adresse': 'Lomé', 'pays': 'Togo', 'delai_livraison': '5', 'description': 'Riz local', 'actif': '1',
        })
        f = __import__('apps.stock.models', fromlist=['Fournisseur']).Fournisseur.objects.get(nom='Togo Riz')
        self.assertEqual((f.contact, f.delai_moyen_jours, f.notes, f.est_actif), ('M. Agbo', 5, 'Riz local', True))
        self.client.post(reverse('responsable_achat:fournisseur_edit', args=[f.pk]),
                         {'nom': 'Togo Riz SA', 'contact_nom': 'M. Agbo', 'delai_livraison': '6', 'actif': '1'})
        f.refresh_from_db()
        self.assertEqual((f.nom, f.delai_moyen_jours), ('Togo Riz SA', 6))
        self.client.post(reverse('responsable_achat:fournisseur_delete', args=[f.pk]))
        f.refresh_from_db()
        self.assertFalse(f.est_actif)

    def test_modification_d_un_brouillon(self):
        from apps.stock.models import BonCommande, LigneCommande
        self.connecter('responsable_achat')
        bc = BonCommande.objects.create(entreprise=self.ent, fournisseur=self.fournisseur)
        LigneCommande.objects.create(bon_commande=bc, produit=self.produit, quantite_commandee=1, prix_unitaire_ht=1)
        self.client.post(reverse('responsable_achat:boncommande_edit', args=[bc.pk]), {
            'fournisseur': self.fournisseur.pk, 'commentaire': 'Modifié',
            'lignes[0][produit]': self.produit.pk, 'lignes[0][quantite]': '7', 'lignes[0][prix_unitaire]': '300',
        })
        bc.refresh_from_db()
        ligne = bc.lignes.get()
        self.assertEqual((bc.note, ligne.quantite_commandee, ligne.prix_unitaire_ht), ('Modifié', 7, 300))

    def test_parametres_achats(self):
        self.connecter('responsable_achat')
        url = reverse('responsable_achat:settings')
        self.client.post(url, {'alerte_rupture': 'on', 'devise_defaut': 'XOF', 'entrepot_defaut': self.entrepot.pk,
                               'seuil_alerte_jours': '10', 'budget_mensuel': '500000'})
        from apps.responsable_achat.models import UserPreferences
        prefs = UserPreferences.objects.get(user=self.users['responsable_achat'])
        self.assertEqual((prefs.seuil_alerte_jours, prefs.budget_mensuel, prefs.notifications['alerte_rupture']),
                         (10, Decimal('500000'), True))
        self.assertEqual(self.client.post(url, {'seuil_alerte_jours': 'abc'}).status_code, 302)  # plus d'erreur 500

    def test_inventaire_magasinier_par_categorie(self):
        self.connecter('magasinier')
        cat = Categorie.objects.create(nom='Riz', entreprise=self.ent)
        mettre_en_stock(creer_produit(self.ent, nom="Autre"), self.entrepot, 2)
        self.produit.categorie = cat
        self.produit.save()
        self.client.post(reverse('magasinier:inventaire_create'),
                         {'entrepot': self.entrepot.pk, 'categorie': cat.pk, 'commentaire': 'Rayon riz'})
        session = InventaireSession.objects.get()
        self.assertEqual((session.lignes.count(), session.note), (1, 'Rayon riz'))

    def test_api_scan(self):
        self.connecter('magasinier')
        self.produit.code_barres = '6111111111111'
        self.produit.save()
        url = reverse('magasinier:api_scan')
        ok = self.client.post(url, json.dumps({'code': '6111111111111', 'action': 'sortie', 'quantite': 2,
                                               'entrepot_id': str(self.entrepot.pk)}), content_type='application/json')
        self.assertTrue(ok.json()['success'])
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 8)
        invalide = self.client.post(url, 'pas du json', content_type='application/json')
        self.assertEqual(invalide.status_code, 400)


class SuperAdminFormulairesTests(EntrepriseTestCase):

    def setUp(self):
        self.sa = creer_utilisateur('super_admin')
        self.client.force_login(self.sa)

    def test_activation_entreprise_en_post_uniquement(self):
        autre = creer_entreprise('B', active=False)
        url = reverse('superadmin:activer_entreprise', args=[autre.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        autre.refresh_from_db()
        self.assertTrue(autre.est_active)
        self.client.post(reverse('superadmin:desactiver_entreprise', args=[autre.pk]))
        autre.refresh_from_db()
        self.assertFalse(autre.est_active)

    def test_changement_de_role(self):
        cible = self.users['comptable']
        response = self.client.post(reverse('superadmin:changer_role', args=[cible.pk]), {'role': 'auditeur'})
        self.assertEqual(response.status_code, 302)  # erreur 500 auparavant
        cible.refresh_from_db()
        self.assertEqual(cible.role, 'auditeur')

    def test_activation_utilisateur_et_protection_de_son_compte(self):
        cible = self.users['comptable']
        self.client.post(reverse('superadmin:desactiver_utilisateur', args=[cible.pk]))
        self.client.post(reverse('superadmin:desactiver_utilisateur', args=[self.sa.pk]))
        cible.refresh_from_db()
        self.sa.refresh_from_db()
        self.assertEqual((cible.is_active, self.sa.is_active), (False, True))
        self.client.post(reverse('superadmin:activer_utilisateur', args=[cible.pk]))
        cible.refresh_from_db()
        self.assertTrue(cible.is_active)

    def test_suppression_douce_entreprise(self):
        self.client.post(reverse('superadmin:supprimer_entreprise', args=[self.ent.pk]), {'action': 'soft_delete'})
        self.ent.refresh_from_db()
        self.assertFalse(self.ent.est_active)


class InscriptionTests(EntrepriseTestCase):

    def test_inscription_en_trois_etapes(self):
        url = reverse('accounts:inscription')
        self.client.post(url, {'type_entreprise': 'commerce_detail'})
        self.client.post(url, {'nom': 'Boutique Ama', 'pays': 'Togo', 'ville': 'Lomé', 'taille': '1-10', 'nb_entrepots': '1'})
        self.client.post(url, {'first_name': 'Ama', 'last_name': 'Doe', 'email': 'ama@boutique.tg',
                               'password1': 'Boutique-Ama-2026!', 'password2': 'Boutique-Ama-2026!'})
        ent = Entreprise.objects.get(nom='Boutique Ama')
        admin = Utilisateur.objects.get(email='ama@boutique.tg')
        self.assertEqual((admin.role, admin.entreprise, ent.est_active, admin.is_active), ('admin_ent', ent, False, False))
        self.assertEqual(len(mail.outbox), 1)  # email de confirmation

    def test_saut_d_etape_impossible(self):
        url = reverse('accounts:inscription')
        self.client.post(url, {'type_entreprise': 'commerce_detail'})
        self.client.get(url, {'step': '3'})  # tentative de sauter l'étape 2
        self.assertEqual(self.client.session['inscription_step'], 2)
        self.assertEqual(self.client.get(url, {'step': 'abc'}).status_code, 302)  # plus d'erreur 500
