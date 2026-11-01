from django.core.cache import cache
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
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


# Thèmes d'apparence (code, nom, couleur de la barre latérale, couleur principale, teinte claire).
# Les couleurs réelles sont définies dans static/css/stockmaster.css (:root[data-theme="…"]) ;
# celles-ci ne servent qu'à l'aperçu dans la page Paramètres.
THEMES = [
    ('orange', 'Orange', '#1a1208', '#f97316', '#fff7ed'),
    ('ocean', 'Océan', '#0b1a26', '#0ea5e9', '#f0f9ff'),
    ('foret', 'Forêt', '#0d1a12', '#16a34a', '#f0fdf4'),
    ('violet', 'Violet', '#150f26', '#7c3aed', '#f5f3ff'),
    ('rubis', 'Rubis', '#1f0a10', '#e11d48', '#fff1f2'),
    ('ardoise', 'Ardoise', '#0f172a', '#475569', '#f1f5f9'),
]
THEME_PAR_DEFAUT = 'orange'


class ParametresEntreprise(models.Model):
    """
    Réglages d'une entreprise, modifiables par son admin (page Paramètres).
    Créés à la volée avec les valeurs par défaut : utiliser ParametresEntreprise.pour(entreprise).
    """
    entreprise = models.OneToOneField(Entreprise, on_delete=models.CASCADE, related_name='parametres')
    # Notifications par email
    alertes_email = models.BooleanField(
        default=True, verbose_name="Alertes de stock par email",
        help_text="Email aux admins et gestionnaires à chaque nouvelle rupture, seuil bas ou produit proche de l'expiration.")
    rapport_hebdo = models.BooleanField(
        default=False, verbose_name="Rapport hebdomadaire",
        help_text="Synthèse envoyée chaque lundi matin aux admins de l'entreprise.")
    ia_email = models.BooleanField(
        default=True, verbose_name="Suggestions d'achat IA par email",
        help_text="Liste quotidienne des produits à commander, envoyée aux responsables achat.")
    # Seuils
    seuil_alerte_defaut = models.DecimalField(
        max_digits=14, decimal_places=2, default=10, verbose_name="Seuil d'alerte par défaut",
        help_text="Proposé à la création d'un produit.")
    jours_alerte_expiration = models.PositiveSmallIntegerField(
        default=30, verbose_name="Jours avant expiration (alerte)",
        help_text="Une alerte est créée pour les lots en stock qui expirent dans ce délai.")
    # Apparence : appliquée à toute l'application, pour tous les rôles de l'entreprise
    theme = models.CharField(
        max_length=20, choices=[(code, nom) for code, nom, *_ in THEMES], default=THEME_PAR_DEFAUT,
        verbose_name="Thème de couleurs")
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Paramètres d'entreprise"
        verbose_name_plural = "Paramètres d'entreprise"

    def __str__(self):
        return f"Paramètres — {self.entreprise}"

    @classmethod
    def pour(cls, entreprise):
        """Paramètres de l'entreprise, créés avec les valeurs par défaut s'ils n'existent pas encore."""
        return cls.objects.get_or_create(entreprise=entreprise)[0]


def cle_theme(entreprise_id):
    return f"stockmaster:theme:{entreprise_id}"


@receiver(post_save, sender=ParametresEntreprise)
def invalider_cache_theme(sender, instance, **kwargs):
    cache.delete(cle_theme(instance.entreprise_id))


def cle_entreprise_active(entreprise_id):
    return f"stockmaster:entreprise-active:{entreprise_id}"


def entreprise_est_active(entreprise_id):
    """État actif d'une entreprise (mis en cache une minute ; invalidé dès qu'elle est enregistrée)."""
    cle = cle_entreprise_active(entreprise_id)
    actif = cache.get(cle)
    if actif is None:
        actif = bool(Entreprise.objects.filter(pk=entreprise_id, est_active=True).exists())
        cache.set(cle, actif, 60)
    return actif


@receiver(post_save, sender=Entreprise)
def invalider_cache_entreprise_active(sender, instance, **kwargs):
    cache.delete(cle_entreprise_active(instance.pk))
