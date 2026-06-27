import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TypeAction(models.TextChoices):
    CONNEXION            = 'connexion',            _('Connexion')
    DECONNEXION          = 'deconnexion',          _('Déconnexion')
    CREATION_USER        = 'creation_user',        _('Création utilisateur')
    MODIFICATION_USER    = 'modification_user',    _('Modification utilisateur')
    SUPPRESSION_USER     = 'suppression_user',     _('Suppression utilisateur')
    ACTIVATION_USER      = 'activation_user',      _('Activation utilisateur')
    DESACTIVATION_USER   = 'desactivation_user',   _('Désactivation utilisateur')
    CHANGEMENT_ROLE      = 'changement_role',      _('Changement de rôle')
    CREATION_ENT         = 'creation_entreprise',  _('Création entreprise')
    ACTIVATION_ENT       = 'activation_entreprise',_('Activation entreprise')
    DESACTIVATION_ENT    = 'desactivation_entreprise', _('Désactivation entreprise')
    SUPPRESSION_ENT      = 'suppression_entreprise',  _('Suppression entreprise')
    CREATION_PRODUIT     = 'creation_produit',     _('Création produit')
    MODIFICATION_PRODUIT = 'modification_produit', _('Modification produit')
    MOUVEMENT_STOCK      = 'mouvement_stock',      _('Mouvement de stock')
    VALIDATION_INVENTAIRE= 'validation_inventaire',_('Validation inventaire')
    CREATION_BC          = 'creation_bc',          _('Création bon de commande')
    VALIDATION_BC        = 'validation_bc',        _('Validation bon de commande')
    RECEPTION_BC         = 'reception_bc',         _('Réception bon de commande')
    EXPORT               = 'export',               _('Export de données')
    IA_ANALYSE           = 'ia_analyse',           _('Analyse IA déclenchée')
    AUTRE                = 'autre',                _('Autre')


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='logs_audit',
        verbose_name=_("Utilisateur")
    )
    entreprise = models.ForeignKey(
        'entreprises.Entreprise',  # ← chaîne, pas d'import direct
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='logs_audit',
        verbose_name=_("Entreprise")
    )
    type_action = models.CharField(
        max_length=40,
        choices=TypeAction.choices,
        default=TypeAction.AUTRE,
        verbose_name=_("Type d'action")
    )
    description = models.TextField(verbose_name=_("Description"))
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name=_("Adresse IP")
    )
    user_agent = models.CharField(
        max_length=300, blank=True,
        verbose_name=_("User-Agent")
    )
    objet_type = models.CharField(
        max_length=100, blank=True,
        verbose_name=_("Type d'objet concerné"),
        help_text=_("Ex: Produit, Entreprise, Utilisateur")
    )
    objet_id = models.CharField(
        max_length=100, blank=True,
        verbose_name=_("ID de l'objet concerné")
    )
    donnees_avant = models.JSONField(
        null=True, blank=True,
        verbose_name=_("Données avant modification")
    )
    donnees_apres = models.JSONField(
        null=True, blank=True,
        verbose_name=_("Données après modification")
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date")
    )

    class Meta:
        verbose_name = _("Log d'audit")
        verbose_name_plural = _("Logs d'audit")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['entreprise', '-created_at']),
            models.Index(fields=['utilisateur', '-created_at']),
            models.Index(fields=['type_action']),
        ]

    def __str__(self):
        user = self.utilisateur.email if self.utilisateur else "Système"
        return f"[{self.get_type_action_display()}] {user} — {self.created_at:%d/%m/%Y %H:%M}"

    @classmethod
    def log(cls, request, type_action, description,
            objet=None, donnees_avant=None, donnees_apres=None):
        ip = cls._get_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')[:300]
        entreprise = getattr(getattr(request, 'user', None), 'entreprise', None)
        obj_type = ''
        obj_id   = ''
        if objet is not None:
            obj_type = type(objet).__name__
            obj_id   = str(getattr(objet, 'pk', ''))
        return cls.objects.create(
            utilisateur=request.user if request.user.is_authenticated else None,
            entreprise=entreprise,
            type_action=type_action,
            description=description,
            ip_address=ip,
            user_agent=ua,
            objet_type=obj_type,
            objet_id=obj_id,
            donnees_avant=donnees_avant,
            donnees_apres=donnees_apres,
        )

    @staticmethod
    def _get_ip(request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class Notification(models.Model):
    class TypeNotif(models.TextChoices):
        ALERTE_STOCK  = 'alerte_stock',  _('Alerte stock')
        COMMANDE      = 'commande',      _('Commande')
        INVENTAIRE    = 'inventaire',    _('Inventaire')
        IA            = 'ia',            _('Prédiction IA')
        SYSTEME       = 'systeme',       _('Système')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    type_notif = models.CharField(max_length=20, choices=TypeNotif.choices)
    titre = models.CharField(max_length=150)
    message = models.TextField()
    lue = models.BooleanField(default=False)
    lien = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.titre} → {self.destinataire.email}"


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ExportLog(models.Model):
    EXPORT_TYPES = [
        ('bc_csv', 'Bons de commande CSV'),
        ('bc_pdf', 'Bons de commande PDF'),
        ('fournisseurs_csv', 'Fournisseurs CSV'),
        ('predictions_csv', 'Prédictions CSV'),
        ('suggestions_csv', 'Suggestions CSV'),
        ('valorisation_cump_csv', 'Valorisation CUMP CSV'),
        ('marges_csv', 'Marges CSV'),
        ('rapport_comptable_pdf', 'Rapport comptable PDF'),
        ('depreciation_csv', 'Dépréciation CSV'),
        ('rapport_categories_pdf', 'Rapport par catégories PDF'),
    ]
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exports'
    )
    entreprise = models.ForeignKey(
        'entreprises.Entreprise',  # ← chaîne
        on_delete=models.CASCADE,
        related_name='exports'
    )
    type_export = models.CharField(max_length=50, choices=EXPORT_TYPES)
    nom_fichier = models.CharField(max_length=255)
    periode = models.CharField(max_length=100, blank=True)
    url = models.URLField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.get_type_export_display()} - {self.date_creation}"