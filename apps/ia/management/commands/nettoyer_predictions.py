"""
Supprime les prédictions remplacées : la tâche IA en crée une nouvelle chaque nuit pour chaque produit,
seule la plus récente est utilisée (suggestions d'achat, écrans IA, fiche produit).
Planifiée chaque semaine par Celery Beat (apps.ia.tasks.nettoyer_predictions), avec un historique conservé.

    python manage.py nettoyer_predictions --apercu            # compte sans rien supprimer
    python manage.py nettoyer_predictions                     # supprime
    python manage.py nettoyer_predictions --garder-jours 90   # conserve celles des 90 derniers jours
"""
from django.core.management.base import BaseCommand

from apps.ia.nettoyage import predictions_remplacees
from apps.stock.models import PredictionStock


class Command(BaseCommand):
    help = "Ne garde que la prédiction la plus récente de chaque produit."

    def add_arguments(self, parser):
        parser.add_argument('--apercu', action='store_true', help="Affiche ce qui serait supprimé, sans supprimer.")
        parser.add_argument('--garder-jours', type=int, default=0,
                            help="Conserve aussi les prédictions créées pendant ces derniers jours.")

    def handle(self, *args, **options):
        anciennes = predictions_remplacees(options['garder_jours'])
        nb = anciennes.count()
        gardees = PredictionStock.objects.count() - nb
        if options['apercu']:
            self.stdout.write(f"{nb} prédiction(s) remplacée(s) seraient supprimées ; {gardees} conservée(s).")
            return
        anciennes.delete()
        self.stdout.write(self.style.SUCCESS(f"{nb} prédiction(s) remplacée(s) supprimée(s) ; {gardees} conservée(s)."))
