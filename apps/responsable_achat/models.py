from django.db import models
from django.conf import settings

class UserPreferences(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='achat_prefs')
    notifications = models.JSONField(default=dict)  # ex: {'relance_commande': True, 'alerte_rupture': True}
    devise_defaut = models.CharField(max_length=3, default='EUR')
    entrepot_defaut = models.ForeignKey('stock.Entrepot', null=True, blank=True, on_delete=models.SET_NULL)
    seuil_alerte_jours = models.PositiveSmallIntegerField(default=7)
    budget_mensuel = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"Préférences de {self.user.email}"
