"""Correctifs de l'audit de sécurité : entreprise désactivée, limitation de connexion, XSS, injection CSV, validation."""
import io
import json
from decimal import Decimal

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import EmailConfirmationToken, Utilisateur
from apps.core.csv_safe import proteger
from apps.entreprises.models import Entreprise
from apps.stock.models import Categorie, Produit

from .base import EntrepriseTestCase, creer_entreprise, creer_utilisateur


class EntrepriseDesactiveeTests(EntrepriseTestCase):

    def _desactiver(self):
        self.ent.est_active = False
        self.ent.save()  # invalide le cache de l'état actif

    def test_utilisateur_deconnecte_et_bloque_sur_le_web(self):
        self.connecter('gestionnaire')
        self.assertEqual(self.client.get(reverse('gestionnaire:dashboard')).status_code, 200)
        self._desactiver()
        reponse = self.client.get(reverse('gestionnaire:dashboard'))
        self.assertEqual(reponse.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)  # session fermée
        reponse = self.client.get(reverse('gestionnaire:dashboard'), follow=True)
        self.assertNotEqual(reponse.status_code, 500)

    def test_reactivation_rend_l_acces(self):
        self.connecter('gestionnaire')
        self._desactiver()
        self.client.get(reverse('gestionnaire:dashboard'))
        self.ent.est_active = True
        self.ent.save()
        self.connecter('gestionnaire')
        self.assertEqual(self.client.get(reverse('gestionnaire:dashboard')).status_code, 200)

    def test_api_refusee_a_une_entreprise_desactivee(self):
        token = RefreshToken.for_user(self.users['magasinier']).access_token
        auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        self.assertEqual(self.client.get('/api/v1/produits/', **auth).status_code, 200)
        self._desactiver()
        self.assertEqual(self.client.get('/api/v1/produits/', **auth).status_code, 403)

    def test_connexion_api_refusee(self):
        self.users['magasinier'].set_password('Mot2Passe!Solide')
        self.users['magasinier'].save()
        self._desactiver()
        reponse = self.client.post('/api/v1/auth/login/', json.dumps({
            'username': self.users['magasinier'].get_username(), 'password': 'Mot2Passe!Solide'}),
            content_type='application/json')
        self.assertEqual(reponse.status_code, 403)

    def test_super_admin_non_concerne(self):
        sa = creer_utilisateur('super_admin')
        self._desactiver()
        self.client.force_login(sa)
        self.assertEqual(self.client.get(reverse('superadmin:dashboard')).status_code, 200)

    def test_super_admin_sans_entreprise_renvoye_vers_son_espace(self):
        self.client.force_login(creer_utilisateur('super_admin'))
        for nom in ('admin_entreprise:parametres', 'gestionnaire:dashboard', 'comptable:dashboard'):
            reponse = self.client.get(reverse(nom))  # provoquait une erreur 500 (entreprise absente)
            self.assertRedirects(reponse, reverse('superadmin:dashboard'), fetch_redirect_response=False)


class LimitationDesConnexionsTests(EntrepriseTestCase):

    def setUp(self):
        cache.clear()
        self.user = self.users['gestionnaire']
        self.user.set_password('Mot2Passe!Solide')
        self.user.save()
        self.url = reverse('accounts:connexion')

    def tearDown(self):
        cache.clear()

    def _essai(self, mot_de_passe, identifiant=None):
        return self.client.post(self.url, {'username': identifiant or self.user.get_username(), 'password': mot_de_passe})

    def test_blocage_apres_cinq_echecs_meme_avec_le_bon_mot_de_passe(self):
        for _ in range(5):
            self.assertEqual(self._essai('mauvais').status_code, 200)
        self.assertEqual(self._essai('mauvais').status_code, 429)
        self.assertEqual(self._essai('Mot2Passe!Solide').status_code, 429)  # même correct, tant que le blocage dure
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_connexion_reussie_remet_le_compteur_a_zero(self):
        for _ in range(3):
            self._essai('mauvais')
        self.assertEqual(self._essai('Mot2Passe!Solide').status_code, 302)
        self.client.logout()
        for _ in range(4):
            self._essai('mauvais')
        self.assertEqual(self._essai('Mot2Passe!Solide').status_code, 302)

    def test_autre_identifiant_non_bloque(self):
        for _ in range(6):
            self._essai('mauvais')
        autre = self.users['comptable']
        autre.set_password('Mot2Passe!Solide')
        autre.save()
        self.assertEqual(self._essai('Mot2Passe!Solide', autre.get_username()).status_code, 302)

    def test_api_aussi_limitee(self):
        for _ in range(5):
            self.client.post('/api/v1/auth/login/', json.dumps({'username': self.user.get_username(), 'password': 'x'}),
                             content_type='application/json')
        reponse = self.client.post('/api/v1/auth/login/', json.dumps({'username': self.user.get_username(), 'password': 'x'}),
                                   content_type='application/json')
        self.assertEqual(reponse.status_code, 429)


class XssDansLesGraphiquesTests(EntrepriseTestCase):

    CHARGE = '</script><script>alert(1)</script>'

    def test_nom_de_categorie_ne_sort_pas_du_script(self):
        cat = Categorie.objects.create(nom=self.CHARGE, entreprise=self.ent)
        self.produit.categorie = cat
        self.produit.save()
        for role, url in [('auditeur', 'auditeur:valorisation'), ('auditeur', 'auditeur:dashboard'),
                          ('comptable', 'comptable:dashboard'), ('gestionnaire', 'gestionnaire:dashboard')]:
            self.connecter(role)
            html = self.client.get(reverse(url)).content.decode()
            self.assertNotIn('<script>alert(1)', html, url)
            self.assertNotIn(self.CHARGE, html, url)

    def test_filtre_json_js(self):
        from apps.core.templatetags.core_ui import json_js
        self.assertEqual(json_js(['a</script>', 'é&']), '["a\\u003C/script\\u003E", "é\\u0026"]')
        self.assertEqual(json_js('[1, 2]'), '[1, 2]')  # JSON déjà sérialisé : normalisé, pas doublement encodé


class InjectionCsvTests(EntrepriseTestCase):

    def test_proteger(self):
        for dangereux in ('=HYPERLINK("http://x")', '+cmd|calc', '-2+3+cmd', '@SUM(A1)', '\t=1+1'):
            self.assertTrue(proteger(dangereux).startswith("'"), dangereux)
        for sur in ('Riz', '12', '-12', '-1 250,50', '+33 1', '12 %', 5, Decimal('-3'), None):
            self.assertEqual(proteger(sur), sur)

    def test_export_de_produits_protege(self):
        Produit.objects.filter(pk=self.produit.pk).update(nom='=HYPERLINK("http://pirate.example")')
        self.connecter('gestionnaire')
        reponse = self.client.get(reverse('gestionnaire:rapports'), {'export': 'stock'})
        contenu = reponse.content.decode('utf-8-sig')
        self.assertIn("'=HYPERLINK", contenu)
        self.assertNotIn(',=HYPERLINK', contenu)
        self.assertNotIn('\n=HYPERLINK', contenu)

    def test_import_de_produits_limite_en_taille(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.connecter('gestionnaire')
        gros = SimpleUploadedFile('p.csv', b'sku,nom\n' + b'a,b\n' * 1_800_000)
        self.client.post(reverse('gestionnaire:produit_import'), {'fichier': gros})
        self.assertEqual(Produit.objects.count(), 1)


class ValidationDeLEntrepriseTests(EntrepriseTestCase):
    """Après confirmation de l'email, l'entreprise reste en attente jusqu'à l'activation par le super admin."""

    def _inscription_en_attente(self):
        ent = creer_entreprise('Nouvelle', active=False)
        admin = Utilisateur.objects.create_user(username='nouveau@exemple.com', email='nouveau@exemple.com',
                                                password='x', role='admin_ent', entreprise=ent, is_active=False,
                                                est_actif=False)
        jeton = EmailConfirmationToken.objects.create(user=admin, token='jeton-de-test-' + 'x' * 30)
        return ent, admin, jeton

    def test_entreprise_reste_en_attente_par_defaut(self):
        ent, admin, jeton = self._inscription_en_attente()
        reponse = self.client.get(reverse('accounts:confirmation_email', args=[jeton.token]), follow=True)
        ent.refresh_from_db()
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)
        self.assertFalse(ent.est_active)
        self.assertContains(reponse, 'validée par l')

    def test_utilisateur_en_attente_ne_peut_pas_travailler(self):
        ent, admin, jeton = self._inscription_en_attente()
        self.client.get(reverse('accounts:confirmation_email', args=[jeton.token]))
        self.client.force_login(admin)
        reponse = self.client.get(reverse('admin_entreprise:dashboard'))
        self.assertEqual(reponse.status_code, 302)

    @override_settings(ENTREPRISE_VALIDATION_MANUELLE=False)
    def test_activation_automatique_possible_par_reglage(self):
        ent, admin, jeton = self._inscription_en_attente()
        self.client.get(reverse('accounts:confirmation_email', args=[jeton.token]))
        ent.refresh_from_db()
        self.assertTrue(ent.est_active)

    def test_activation_par_le_super_admin_ouvre_l_acces(self):
        ent, admin, jeton = self._inscription_en_attente()
        self.client.get(reverse('accounts:confirmation_email', args=[jeton.token]))
        self.client.force_login(creer_utilisateur('super_admin'))
        self.client.post(reverse('superadmin:activer_entreprise', args=[ent.pk]))
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse('admin_entreprise:dashboard')).status_code, 200)


class ControlesDiversTests(EntrepriseTestCase):

    def test_recherche_de_produits_du_magasinier_reservee(self):
        url = reverse('magasinier:produit_search_ajax')
        for role in ('comptable', 'auditeur', 'responsable_achat'):
            self.connecter(role)
            self.assertNotEqual(self.client.get(url, {'q': 'Riz'}).status_code, 200, role)
        self.connecter('magasinier')
        self.assertEqual(self.client.get(url, {'q': 'Riz'}).status_code, 200)

    def test_en_tetes_de_securite(self):
        reponse = self.client.get(reverse('pages:accueil'))
        self.assertEqual(reponse['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(reponse['X-Frame-Options'], 'DENY')
        self.assertEqual(reponse['Referrer-Policy'], 'strict-origin-when-cross-origin')
        self.assertEqual(reponse['Cross-Origin-Opener-Policy'], 'same-origin')

    def test_adresse_ip_du_journal_non_falsifiable(self):
        from apps.accounts.throttle import adresse_ip
        from django.test import RequestFactory
        requete = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='1.2.3.4, 9.9.9.9', REMOTE_ADDR='10.0.0.1')
        with override_settings(SECURE_PROXY_SSL_HEADER=None):
            self.assertEqual(adresse_ip(requete), '10.0.0.1')  # hors proxy : l'en-tête du client est ignoré
        with override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https')):
            self.assertEqual(adresse_ip(requete), '9.9.9.9')   # derrière notre proxy : dernière entrée ajoutée par lui


class SessionsParEntrepriseTests(EntrepriseTestCase):

    def _enregistrer(self, minutes, fermeture=True):
        self.connecter('admin_ent')
        donnees = {'section': 'sessions', 'inactivite_minutes': str(minutes)}
        if fermeture:
            donnees['fermeture_navigateur'] = 'on'
        return self.client.post(reverse('admin_entreprise:parametres'), donnees)

    def test_reglage_enregistre_et_journalise(self):
        from apps.core.models import AuditLog
        from apps.entreprises.models import ParametresEntreprise
        self._enregistrer(45, fermeture=False)
        p = ParametresEntreprise.pour(self.ent)
        self.assertEqual((p.session_inactivite_minutes, p.session_fermeture_navigateur), (45, False))
        self.assertTrue(AuditLog.objects.filter(type_action='parametres', description__startswith='Sessions').exists())
        html = self.client.get(reverse('admin_entreprise:parametres')).content.decode()
        self.assertIn('value="45"', html)

    def test_valeurs_hors_limites_refusees(self):
        from apps.entreprises.models import ParametresEntreprise
        for valeur in ('5', '5000', 'abc', ''):
            self._enregistrer(valeur)
        self.assertEqual(ParametresEntreprise.pour(self.ent).session_inactivite_minutes, 120)

    def test_deconnexion_apres_inactivite_selon_l_entreprise(self):
        import time
        self._enregistrer(30)
        self.connecter('gestionnaire')
        self.assertEqual(self.client.get(reverse('gestionnaire:dashboard')).status_code, 200)
        session = self.client.session
        session['_derniere_activite'] = time.time() - 29 * 60
        session.save()
        self.assertEqual(self.client.get(reverse('gestionnaire:dashboard')).status_code, 200)  # 29 min : encore valide
        session = self.client.session
        session['_derniere_activite'] = time.time() - 31 * 60
        session.save()
        reponse = self.client.get(reverse('gestionnaire:dashboard'))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('connexion', reponse['Location'])
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_autre_entreprise_non_affectee(self):
        import time
        self._enregistrer(15)
        autre = creer_entreprise('B')
        self.client.force_login(creer_utilisateur('gestionnaire', autre))
        session = self.client.session
        session['_derniere_activite'] = time.time() - 60 * 60  # 1 h : dépasse 15 min mais l'entreprise B garde 2 h
        session.save()
        self.assertEqual(self.client.get(reverse('gestionnaire:dashboard')).status_code, 200)

    def test_option_fermeture_du_navigateur(self):
        self._enregistrer(60, fermeture=False)
        self.connecter('gestionnaire')
        self.client.get(reverse('gestionnaire:dashboard'))
        self.assertGreater(self.client.session.get_expiry_age(), 3600)  # cookie persistant
        self._enregistrer(60, fermeture=True)
        self.connecter('gestionnaire')
        self.client.get(reverse('gestionnaire:dashboard'))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_seul_l_admin_modifie_les_sessions(self):
        from apps.entreprises.models import ParametresEntreprise
        self.connecter('gestionnaire')
        self.client.post(reverse('admin_entreprise:parametres'), {'section': 'sessions', 'inactivite_minutes': '30'})
        self.assertEqual(ParametresEntreprise.pour(self.ent).session_inactivite_minutes, 120)
