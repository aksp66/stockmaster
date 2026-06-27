from django.db import models
from apps.accounts.models import Utilisateur
from apps.entreprises.models import Entreprise

class AuditLog(models.Model):
    ACTION_TYPES = [
        ('activation', 'Activation'),
        ('desactivation', 'Désactivation'),
        ('role', 'Changement de rôle'),
        ('suppression', 'Suppression'),
        ('connexion', 'Connexion'),
    ]
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, related_name='logs')
    entreprise = models.ForeignKey(Entreprise, on_delete=models.SET_NULL, null=True, blank=True)
    type_action = models.CharField(max_length=50, choices=ACTION_TYPES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']