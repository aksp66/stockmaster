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


class BalisesAffichageTests(EntrepriseTestCase):
    """Statuts de stock et couleurs de catégories communs à tous les espaces."""

    def test_statuts_de_stock(self):
        from apps.stock.templatetags.stock_ui import code_statut
        p = self.produit  # seuil 5
        for stock, attendu in [(0, 'rupture'), (5, 'critique'), (9, 'faible'), (10, 'faible'), (11, 'ok')]:
            from apps.stock.models import Stock
            Stock.objects.filter(produit=p).update(quantite=stock)
            self.assertEqual(code_statut(p), attendu, stock)

    def test_couleur_de_categorie_stable(self):
        from apps.stock.templatetags.stock_ui import cat_index
        self.assertEqual(cat_index('Boissons'), cat_index(' boissons '))
        self.assertTrue(all(0 <= cat_index(n) < 8 for n in ('A', 'B', 'Épicerie', '')))

    def test_liste_des_produits_affiche_les_pastilles(self):
        from apps.stock.models import Categorie
        self.produit.categorie = Categorie.objects.create(nom='Épicerie', entreprise=self.ent)
        self.produit.save()
        self.connecter('gestionnaire')
        html = self.client.get(reverse('gestionnaire:produits')).content.decode()
        self.assertIn('class="cat cat-', html)
        self.assertIn('st st-faible', html)  # 10 en stock pour un seuil de 5


class PagesPubliquesTests(EntrepriseTestCase):

    def test_banniere_de_cookies_sur_les_pages_publiques(self):
        for nom in ('pages:accueil', 'pages:faq', 'pages:politique', 'pages:contact', 'pages:entreprises'):
            html = self.client.get(reverse(nom)).content.decode()
            self.assertIn('id="ck-banner"', html, nom)
            self.assertIn('js/cookies.js', html, nom)
            self.assertIn('data-cookies-open', html, nom)  # lien « Gérer mes cookies » du pied de page

    def test_politique_decrit_le_cookie_de_consentement(self):
        html = self.client.get(reverse('pages:politique')).content.decode()
        self.assertIn('sm_consent', html)
        self.assertIn('id="s8"', html)

    def test_faq_alimentee_par_les_donnees_et_sans_promesse_inventee(self):
        from apps.pages.faq_data import QUESTIONS
        response = self.client.get(reverse('pages:faq'))
        html = response.content.decode()
        self.assertEqual(html.count('class="faq-item"'), len(QUESTIONS))
        self.assertEqual(len(response.context['faq_categories']), 5)
        for faux in ('30, 60 et 90', '2h ouvrées', 'illimité'):
            self.assertNotIn(faux, html)

    def test_theme_orange_pour_les_visiteurs(self):
        self.assertNotIn('data-theme="ocean"', self.client.get(reverse('pages:accueil')).content.decode())


class PagesJuridiquesEtAlerteTests(EntrepriseTestCase):

    def test_pages_juridiques_sans_information_inventee(self):
        for nom in ('pages:mentions_legales', 'pages:conditions'):
            html = self.client.get(reverse(nom)).content.decode()
            self.assertIn('[À compléter]', html, nom)  # rien n'est renseigné : la page le dit au lieu d'inventer
            self.assertIn('Gérer mes cookies', html)

    def test_identite_renseignee_dans_les_reglages(self):
        from django.test import override_settings
        from django.conf import settings
        with override_settings(LEGAL={**settings.LEGAL, 'editeur': 'Exemple SARL', 'juridiction': 'Lomé'}):
            html = self.client.get(reverse('pages:mentions_legales')).content.decode()
        self.assertIn('<strong>Exemple SARL</strong>', html)
        self.assertIn('<strong>Lomé</strong>', html)

    def test_avertissement_reserve_au_super_admin(self):
        self.assertNotIn('Réservé au super admin', self.client.get(reverse('pages:conditions')).content.decode())
        from .base import creer_utilisateur
        self.client.force_login(creer_utilisateur('super_admin'))
        self.assertIn('Réservé au super admin', self.client.get(reverse('pages:conditions')).content.decode())

    def test_email_aux_super_admins_a_la_confirmation_d_inscription(self):
        from django.core import mail
        from apps.accounts.models import EmailConfirmationToken, Utilisateur
        from .base import creer_entreprise, creer_utilisateur
        sa = creer_utilisateur('super_admin')
        ent = creer_entreprise('Nouvelle SARL', active=False)
        admin = Utilisateur.objects.create_user(username='n@exemple.com', email='n@exemple.com', password='x',
                                                role='admin_ent', entreprise=ent, is_active=False, est_actif=False)
        jeton = EmailConfirmationToken.objects.create(user=admin, token='j' * 40)
        self.client.get(reverse('accounts:confirmation_email', args=[jeton.token]))
        envoyes = [m for m in mail.outbox if 'attend son activation' in m.subject]
        self.assertEqual(len(envoyes), 1)
        self.assertEqual(envoyes[0].to, [sa.email])
        self.assertIn('Nouvelle SARL', envoyes[0].subject)
        self.assertIn(str(ent.pk), envoyes[0].body)


class TogoEtSessionsTests(EntrepriseTestCase):

    def test_plus_de_reference_a_la_france_ni_au_rgpd(self):
        for nom in ('pages:accueil', 'pages:contact', 'pages:politique', 'pages:mentions_legales', 'pages:conditions',
                    'pages:faq'):
            html = self.client.get(reverse(nom)).content.decode()
            for interdit in ('France', 'RGPD', 'CNIL', 'Paris', '+33'):
                self.assertNotIn(interdit, html, f'{interdit} dans {nom}')
        self.assertIn('2019-014', self.client.get(reverse('pages:politique')).content.decode())

    def test_politique_sans_style_affiche_en_clair(self):
        self.assertNotIn('border-radius:16px;padding:28px;', self.client.get(reverse('pages:politique')).content.decode()
                         .split('Sommaire')[-1].split('id="s1"')[0])

    def test_un_seul_lien_mentions_legales_dans_le_pied_de_page(self):
        html = self.client.get(reverse('pages:accueil')).content.decode()
        self.assertEqual(html.count('>Mentions légales</a>'), 1)

    def test_sessions_a_duree_limitee(self):
        from django.conf import settings
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertLessEqual(settings.SESSION_COOKIE_AGE, 8 * 3600)
        self.assertLessEqual(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].days, 7)

    def test_interrupteurs_des_parametres_sans_double_bascule(self):
        self.connecter('admin_ent')
        html = self.client.get(reverse('admin_entreprise:parametres')).content.decode()
        self.assertIn('class="ck-switch"', html)
        self.assertNotIn("previousElementSibling.checked=!", html)  # l'ancien script inversait la case une 2e fois

    def test_enregistrement_des_notifications_dans_les_deux_sens(self):
        from apps.entreprises.models import ParametresEntreprise
        self.connecter('admin_ent')
        url = reverse('admin_entreprise:parametres')
        self.client.post(url, {'section': 'notifications', 'rapport_hebdo': 'on'})
        p = ParametresEntreprise.pour(self.ent)
        self.assertEqual((p.alertes_email, p.rapport_hebdo, p.ia_email), (False, True, False))
        self.client.post(url, {'section': 'notifications', 'alertes_email': 'on', 'ia_email': 'on'})
        p.refresh_from_db()
        self.assertEqual((p.alertes_email, p.rapport_hebdo, p.ia_email), (True, False, True))


class AccueilAnimeeTests(EntrepriseTestCase):

    def test_page_complete_et_ressources(self):
        html = self.client.get(reverse('pages:accueil')).content.decode()
        for attendu in ('css/accueil.css', 'js/accueil.js', 'ac-hero', 'ac-rotator', 'role="tablist"', 'ac-steps', 'Aperçu illustratif'):
            self.assertIn(attendu, html)
        self.assertEqual(html.count('role="tabpanel"'), 6)  # un panneau par rôle
        self.assertEqual(html.count('role="tab"'), 6)

    def test_aucune_promesse_inexacte(self):
        html = self.client.get(reverse('pages:accueil')).content.decode()
        for faux in ('30/60/90', '7j/7', 'moins de 15 minutes', 'Zéro rupture', 'générés automatiquement', 'Après 7 jours'):
            self.assertNotIn(faux, html)
        self.assertIn('14 jours', html)  # seuil réel de la tâche IA

    def test_chiffres_publics_uniquement_s_ils_existent(self):
        from apps.entreprises.models import Entreprise
        Entreprise.objects.update(est_active=False)
        self.assertNotIn('ac-stats', self.client.get(reverse('pages:accueil')).content.decode())
        Entreprise.objects.update(est_active=True)
        self.assertIn('ac-stats', self.client.get(reverse('pages:accueil')).content.decode())


class PagesDErreurTests(EntrepriseTestCase):

    def test_404_au_gabarit_commun(self):
        reponse = self.client.get('/cette-page-n-existe-pas/')
        self.assertEqual(reponse.status_code, 404)
        self.assertContains(reponse, 'Page introuvable', status_code=404)
        self.assertContains(reponse, 'css/stockmaster.css', status_code=404)

    def test_403_et_500_se_rendent_sans_contexte(self):
        from django.template.loader import render_to_string
        for nom, texte in (('403.html', 'Accès refusé'), ('500.html', 'Une erreur est survenue')):
            html = render_to_string(nom)  # aucune requête : exactement comme la page 500 de Django
            self.assertIn(texte, html)
            self.assertIn('Retour à l\'accueil', html)
