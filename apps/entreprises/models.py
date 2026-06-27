from django.db import models
from apps.core.models import TimeStampedModel   

class TypeEntreprise(models.TextChoices):
    COMMERCE_DETAIL   = 'commerce_detail',   'Commerce de détail'
    GROS_DISTRIBUTION = 'gros_distribution', 'Gros / Distribution'
    ECOMMERCE         = 'ecommerce',         'E-commerce / Logistique'
    INDUSTRIE         = 'industrie',         'Industrie / Atelier'
    SANTE             = 'sante',             'Santé / Pharmacie'
    RESTAURATION      = 'restauration',      'Hôtellerie / Restauration'

# Matrice : rôles autorisés par type d'entreprise
ROLES_PAR_TYPE = {
    TypeEntreprise.COMMERCE_DETAIL:   ['admin_ent', 'gestionnaire', 'responsable_achat', 'magasinier'],
    TypeEntreprise.GROS_DISTRIBUTION: ['admin_ent', 'gestionnaire', 'responsable_achat', 'magasinier', 'auditeur', 'comptable'],
    TypeEntreprise.ECOMMERCE:         ['admin_ent', 'gestionnaire', 'responsable_achat', 'magasinier', 'comptable'],
    TypeEntreprise.INDUSTRIE:         ['admin_ent', 'gestionnaire', 'responsable_achat', 'magasinier'],
    TypeEntreprise.SANTE:             ['admin_ent', 'gestionnaire', 'responsable_achat', 'auditeur', 'comptable'],
    TypeEntreprise.RESTAURATION:      ['admin_ent', 'gestionnaire', 'responsable_achat', 'magasinier'],
}

class Entreprise(TimeStampedModel):
    nom              = models.CharField(max_length=200)
    type_entreprise  = models.CharField(max_length=50, choices=TypeEntreprise.choices)
    pays             = models.CharField(max_length=100, default='Togo')
    ville            = models.CharField(max_length=100, blank=True)
    taille           = models.CharField(max_length=50, blank=True)
    nb_entrepots     = models.PositiveIntegerField(default=1)
    est_active       = models.BooleanField(default=False)  # activé après email

    def get_roles_disponibles(self):
        return ROLES_PAR_TYPE.get(self.type_entreprise, [])

    def __str__(self):
        return self.nom