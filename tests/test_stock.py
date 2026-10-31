"""Le stock ne doit jamais devenir négatif, quel que soit le point d'entrée."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from apps.gestionnaire.views import _appliquer_mouvement
from apps.stock.models import Mouvement, TypeMouvement

from .base import EntrepriseTestCase, creer_entrepot, quantite_en_stock


class StockJamaisNegatifTests(EntrepriseTestCase):

    def _mouvement(self, type_m, quantite, source=None, destination=None):
        return Mouvement.objects.create(
            type_mouvement=type_m, produit=self.produit, quantite=quantite,
            entrepot_source=source, entrepot_destination=destination,
        )

    def test_sortie_superieure_au_stock_refusee(self):
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                _appliquer_mouvement(self._mouvement(TypeMouvement.SORTIE, 11, source=self.entrepot))
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)

    def test_sortie_de_tout_le_stock_autorisee(self):
        _appliquer_mouvement(self._mouvement(TypeMouvement.SORTIE, 10, source=self.entrepot))
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 0)

    def test_perte_superieure_au_stock_refusee(self):
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                _appliquer_mouvement(self._mouvement(TypeMouvement.PERTE, 15, source=self.entrepot))
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)

    def test_transfert_insuffisant_ne_touche_aucun_entrepot(self):
        dest = creer_entrepot(self.ent, "Annexe")
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                _appliquer_mouvement(self._mouvement(TypeMouvement.TRANSFERT, 12, source=self.entrepot, destination=dest))
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)
        self.assertEqual(quantite_en_stock(self.produit, dest), 0)

    def test_formulaire_gestionnaire_sortie_excessive(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 25, 'entrepot': self.entrepot.pk,
        })
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)
        # Le mouvement refusé ne doit pas rester dans le journal
        self.assertFalse(Mouvement.objects.exists())

    def test_formulaire_gestionnaire_sortie_valide(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 4, 'entrepot': self.entrepot.pk,
        })
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), Decimal(6))
        self.assertEqual(Mouvement.objects.count(), 1)
