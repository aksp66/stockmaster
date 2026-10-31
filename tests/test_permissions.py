"""Contrôle d'accès par rôle (régression du bug où role_required laissait passer tout le monde)."""
from django.urls import reverse

from .base import EntrepriseTestCase, creer_utilisateur

# Espace -> rôles autorisés (hors super_admin, qui passe partout)
ESPACES = {
    'admin_entreprise:dashboard': {'admin_ent'},
    'gestionnaire:dashboard': {'gestionnaire', 'admin_ent'},
    'responsable_achat:dashboard': {'responsable_achat', 'admin_ent'},
    'magasinier:dashboard': {'magasinier', 'admin_ent'},
    'auditeur:dashboard': {'auditeur', 'admin_ent'},
    'comptable:dashboard': {'comptable', 'admin_ent'},
}


class PermissionsParRoleTests(EntrepriseTestCase):

    def test_matrice_des_acces(self):
        for url_name, autorises in ESPACES.items():
            for role in self.users:
                with self.subTest(espace=url_name, role=role):
                    self.connecter(role)
                    response = self.client.get(reverse(url_name))
                    if role in autorises:
                        self.assertEqual(response.status_code, 200)
                    else:
                        self.assertRedirects(response, reverse('pages:accueil'), fetch_redirect_response=False)

    def test_anonyme_redirige_vers_connexion(self):
        for url_name in ESPACES:
            with self.subTest(espace=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 302)
                self.assertNotEqual(response.url, reverse('pages:accueil'))

    def test_espace_superadmin_reserve(self):
        for role in self.users:
            with self.subTest(role=role):
                self.connecter(role)
                response = self.client.get(reverse('superadmin:dashboard'))
                self.assertRedirects(response, reverse('pages:accueil'), fetch_redirect_response=False)
        self.client.force_login(creer_utilisateur('super_admin'))
        self.assertEqual(self.client.get(reverse('superadmin:dashboard')).status_code, 200)

    def test_magasinier_ne_peut_pas_valider_un_inventaire(self):
        from apps.stock.models import InventaireSession
        session = InventaireSession.objects.create(entrepot=self.entrepot)
        self.connecter('magasinier')
        self.client.post(reverse('gestionnaire:inventaire_valider', args=[session.pk]))
        session.refresh_from_db()
        self.assertEqual(session.statut, 'en_cours')

    def test_responsable_achat_ne_peut_pas_saisir_de_mouvement(self):
        from apps.stock.models import Mouvement
        self.connecter('responsable_achat')
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 1, 'entrepot': self.entrepot.pk,
        })
        self.assertFalse(Mouvement.objects.exists())
