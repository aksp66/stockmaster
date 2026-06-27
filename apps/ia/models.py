from django.db import models
from apps.stock.models import Produit

class SuggestionAchat(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='suggestions_achat')
    quantite_recommandee = models.PositiveIntegerField()
    raison = models.TextField(blank=True)
    date_suggestion = models.DateField(auto_now_add=True)
    priorite = models.CharField(max_length=20, choices=[('haute', 'Haute'), ('normale', 'Normale'), ('basse', 'Basse')], default='normale')
    validee = models.BooleanField(default=False)