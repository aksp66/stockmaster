"""Dépôt d'avis client depuis la page publique « Entreprises »."""
from django.urls import reverse

from apps.pages.models import Avis

from .base import EntrepriseTestCase

AVIS_VALIDE = {
    'note': '5', 'prenom': 'Ama', 'nom': 'Kodjo', 'poste': 'Responsable logistique',
    'commentaire': "StockMaster nous a permis de réduire nos ruptures de stock de moitié en trois mois.",
    'accord_publication': 'on',
}


class AvisTests(EntrepriseTestCase):

    def test_page_publique(self):
        self.assertEqual(self.client.get(reverse('pages:entreprises')).status_code, 200)

    def test_avis_enregistre_non_publie(self):
        user = self.connecter('gestionnaire')
        self.client.post(reverse('pages:soumettre_avis'), AVIS_VALIDE)
        avis = Avis.objects.get()
        self.assertEqual((avis.utilisateur, avis.entreprise, avis.note), (user, self.ent, 5))
        self.assertFalse(avis.est_publie)
        # Non modéré : pas visible sur la page publique
        self.assertNotContains(self.client.get(reverse('pages:entreprises')), "réduire nos ruptures")

    def test_un_seul_avis_par_utilisateur(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('pages:soumettre_avis'), AVIS_VALIDE)
        self.client.post(reverse('pages:soumettre_avis'), {**AVIS_VALIDE, 'note': '1'})
        self.assertEqual(Avis.objects.get().note, 5)

    def test_avis_trop_court_refuse(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('pages:soumettre_avis'), {**AVIS_VALIDE, 'commentaire': 'Bien.'})
        self.assertFalse(Avis.objects.exists())

    def test_anonyme_refuse(self):
        self.client.post(reverse('pages:soumettre_avis'), AVIS_VALIDE)
        self.assertFalse(Avis.objects.exists())


class ChiffresPublicsTests(EntrepriseTestCase):
    """Les pages publiques n'affichent que des chiffres issus de la base."""

    def _avis(self, role, note, publie=True):
        from django.utils import timezone
        return Avis.objects.create(
            utilisateur=self.users[role], entreprise=self.ent, note=note, prenom='A', nom='B', poste='C',
            commentaire='x' * 60, est_publie=publie, date_publication=timezone.now() if publie else None,
        )

    def test_aucun_chiffre_invente(self):
        from .base import creer_entreprise
        creer_entreprise("Pas encore activée", active=False)
        for url in (reverse('pages:accueil'), reverse('pages:entreprises')):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                for faux in ('+200', '>4.8<', '>84<', '97%', '98%', '72%', 'Des centaines', 'Laurent M.', 'TechLog'):
                    self.assertNotIn(faux, html)
        response = self.client.get(reverse('pages:entreprises'))
        self.assertEqual(response.context['nb_entreprises'], 1)  # seule l'entreprise active compte
        self.assertContains(response, "1 entreprise cliente")
        self.assertContains(response, "Aucun avis publié pour l'instant")

    def test_statistiques_calculees_sur_les_avis_publies(self):
        self._avis('gestionnaire', 5)
        self._avis('magasinier', 3)
        self._avis('comptable', 1, publie=False)  # non modéré : ignoré
        ctx = self.client.get(reverse('pages:entreprises')).context
        self.assertEqual((ctx['nb_avis'], ctx['note_moyenne'], ctx['pct_recommande'], ctx['note_etoiles']), (2, 4.0, 50, 4))
        accueil = self.client.get(reverse('pages:accueil'))
        self.assertEqual(len(accueil.context['derniers_avis']), 2)
        self.assertContains(accueil, "4,0/5")  # format français
