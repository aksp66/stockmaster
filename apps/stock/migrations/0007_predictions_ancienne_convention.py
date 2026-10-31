"""
Mise à la convention actuelle des prédictions enregistrées avant le 31/10/2026.

- Bornes journalières (ancienne tâche IA) : reconnaissables car la borne haute est inférieure à la
  consommation prévue sur la période, impossible avec des totaux. Un total ne peut pas être reconstitué
  à partir de min / max journaliers : les bornes passent à « inconnues » (NULL) et la quantité
  recommandée, calculée par l'ancienne formule, est effacée. La consommation prévue, déjà un total,
  est conservée.
- Confiance exprimée entre 0 et 1 (ancien script de démonstration) : ramenée sur 100.
"""
from django.db import migrations
from django.db.models import F


def vers_convention_actuelle(apps, schema_editor):
    PredictionStock = apps.get_model('stock', 'PredictionStock')
    PredictionStock.objects.filter(borne_superieure__lt=F('quantite_prevue')).update(
        borne_inferieure=None, borne_superieure=None, quantite_recommandee_commande=None,
    )
    PredictionStock.objects.filter(confiance__lte=1).update(confiance=F('confiance') * 100)


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0006_prediction_unites_documentees'),
    ]

    operations = [
        migrations.RunPython(vers_convention_actuelle, migrations.RunPython.noop),
    ]
