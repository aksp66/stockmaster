"""
Prix de vente enregistré sur chaque vente et chaque retour client.

Les mouvements existants reçoivent le prix de vente actuel de leur produit : c'est la seule information
disponible, et le chiffre d'affaires de l'historique reste ainsi identique à celui calculé jusqu'ici.
"""
from django.db import migrations, models
from django.db.models import OuterRef, Q, Subquery


def renseigner_prix_existants(apps, schema_editor):
    Mouvement = apps.get_model('stock', 'Mouvement')
    Produit = apps.get_model('stock', 'Produit')
    Mouvement.objects.filter(
        Q(type_mouvement='sortie') | Q(type_mouvement='retour', entrepot_destination__isnull=False),
        prix_vente_snapshot__isnull=True,
    ).update(prix_vente_snapshot=Subquery(Produit.objects.filter(pk=OuterRef('produit')).values('prix_vente')[:1]))


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0007_predictions_ancienne_convention'),
    ]

    operations = [
        migrations.AddField(
            model_name='mouvement',
            name='prix_vente_snapshot',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True,
                                      verbose_name='Prix de vente au moment du mouvement'),
        ),
        migrations.RunPython(renseigner_prix_existants, migrations.RunPython.noop),
    ]
