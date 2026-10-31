"""
Supprime les prédictions remplacées : la tâche IA en crée une nouvelle chaque nuit pour chaque produit,
seule la plus récente est utilisée (suggestions d'achat, écrans IA, fiche produit).

    python manage.py nettoyer_predictions --apercu     # compte sans rien supprimer
    python manage.py nettoyer_predictions              # supprime
"""
from django.core.management.base import BaseCommand
from django.db.models import OuterRef, Subquery

from apps.stock.models import PredictionStock


class Command(BaseCommand):
    help = "Ne garde que la prédiction la plus récente de chaque produit."

    def add_arguments(self, parser):
        parser.add_argument('--apercu', action='store_true', help="Affiche ce qui serait supprimé, sans supprimer.")

    def handle(self, *args, **options):
        plus_recente = (PredictionStock.objects.filter(produit=OuterRef('produit'))
                        .order_by('-created_at', '-date_cible').values('pk')[:1])
        anciennes = PredictionStock.objects.exclude(pk__in=PredictionStock.objects.filter(pk=Subquery(plus_recente))
                                                    .values('pk'))
        nb, gardees = anciennes.count(), PredictionStock.objects.count() - anciennes.count()
        if options['apercu']:
            self.stdout.write(f"{nb} prédiction(s) remplacée(s) seraient supprimées ; {gardees} conservée(s).")
            return
        anciennes.delete()
        self.stdout.write(self.style.SUCCESS(f"{nb} prédiction(s) remplacée(s) supprimée(s) ; {gardees} conservée(s)."))
