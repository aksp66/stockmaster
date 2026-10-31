from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Avis(models.Model):
    """
    Avis client déposé depuis la page publique « Entreprises ».
    Un seul avis par utilisateur ; publié uniquement après modération (admin Django).
    """
    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='avis'
    )
    entreprise = models.ForeignKey(
        'entreprises.Entreprise', on_delete=models.CASCADE, related_name='avis'
    )
    note = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100)
    poste = models.CharField(max_length=150)
    commentaire = models.TextField(max_length=500)
    est_publie = models.BooleanField(default=False, verbose_name="Publié")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_publication = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Avis client"
        verbose_name_plural = "Avis clients"
        ordering = ['-date_publication', '-date_creation']

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.entreprise}) — {self.note}/5"

    @property
    def etoiles_range(self):
        return range(self.note)

    @property
    def etoiles_vides_range(self):
        return range(5 - self.note)
