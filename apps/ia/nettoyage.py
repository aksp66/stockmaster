"""
Prédictions remplacées : la tâche IA en crée une nouvelle chaque nuit pour chaque produit, seule la plus
récente est utilisée (suggestions d'achat, écrans IA, fiche produit).
"""
from datetime import timedelta

from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.stock.models import PredictionStock


def predictions_remplacees(garder_jours=0):
    """
    Prédictions qui ne sont plus la plus récente de leur produit. Avec garder_jours, celles créées
    pendant ces derniers jours sont conservées (historique pour comparer prévisions et ventes réelles).
    """
    plus_recente = (PredictionStock.objects.filter(produit=OuterRef('produit'))
                    .order_by('-created_at', '-date_cible').values('pk')[:1])
    anciennes = PredictionStock.objects.exclude(pk__in=PredictionStock.objects.filter(pk=Subquery(plus_recente))
                                                .values('pk'))
    if garder_jours:
        anciennes = anciennes.filter(created_at__lt=timezone.now() - timedelta(days=garder_jours))
    return anciennes
