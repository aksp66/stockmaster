"""Notifications pilotées par les paramètres de l'entreprise (emails et tâches planifiées)."""
from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.admin_entreprise.tasks import envoyer_rapports_hebdo, envoyer_suggestions_ia, verifier_expirations
from apps.entreprises.models import ParametresEntreprise
from apps.stock.models import Alerte, Mouvement, PredictionStock, TypeMouvement

from .base import EntrepriseTestCase


class NotificationsTests(EntrepriseTestCase):

    def _parametres(self, **valeurs):
        p = ParametresEntreprise.pour(self.ent)
        for champ, valeur in valeurs.items():
            setattr(p, champ, valeur)
        p.save()

    def _sortie(self, quantite):
        self.connecter('gestionnaire')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('gestionnaire:mouvement_form'), {
                'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': quantite, 'entrepot': self.entrepot.pk,
            })

    def test_email_a_la_creation_d_une_alerte(self):
        self._sortie(6)  # 4 restants, seuil 5
        self.assertTrue(Alerte.objects.filter(type_alerte='seuil_bas').exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.produit.nom, mail.outbox[0].subject)
        self.assertCountEqual(mail.outbox[0].to, [self.users['admin_ent'].email, self.users['gestionnaire'].email])

    def test_pas_d_email_si_desactive(self):
        self._parametres(alertes_email=False)
        self._sortie(6)
        self.assertTrue(Alerte.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_alerte_d_expiration(self):
        self._parametres(jours_alerte_expiration=10)
        Mouvement.objects.create(type_mouvement=TypeMouvement.ENTREE, produit=self.produit, quantite=1,
                                 entrepot_destination=self.entrepot, lot_numero='L42',
                                 date_expiration=timezone.localdate() + timedelta(days=5))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(verifier_expirations(), 1)
            self.assertEqual(verifier_expirations(), 0)  # pas de doublon
        alerte = Alerte.objects.get(type_alerte='expiration')
        self.assertIn('L42', alerte.message)
        self.assertEqual(len(mail.outbox), 1)

    def test_lot_hors_delai_ignore(self):
        self._parametres(jours_alerte_expiration=10)
        Mouvement.objects.create(type_mouvement=TypeMouvement.ENTREE, produit=self.produit, quantite=1,
                                 entrepot_destination=self.entrepot,
                                 date_expiration=timezone.localdate() + timedelta(days=60))
        self.assertEqual(verifier_expirations(), 0)

    def test_rapport_hebdomadaire_selon_parametre(self):
        self.assertEqual(envoyer_rapports_hebdo(), 0)  # désactivé par défaut
        self._parametres(rapport_hebdo=True)
        self.assertEqual(envoyer_rapports_hebdo(), 1)
        self.assertIn('Valeur du stock', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, [self.users['admin_ent'].email])

    def test_suggestions_ia_par_email(self):
        self.produit.seuil_alerte = 20  # 10 en stock, 60 consommés sur 30 jours : à commander
        self.produit.save()
        for i in range(30):
            PredictionStock.objects.create(produit=self.produit, date_cible=timezone.localdate() + timedelta(days=i),
                                           quantite_prevue=2, confiance=80, modele_utilise='prophet')
        self.assertEqual(envoyer_suggestions_ia(), 1)
        self.assertIn(self.produit.nom, mail.outbox[0].body)
        self._parametres(ia_email=False)
        mail.outbox.clear()
        self.assertEqual(envoyer_suggestions_ia(), 0)
