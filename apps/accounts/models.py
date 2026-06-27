import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.entreprises.models import Entreprise   

class RoleUtilisateur(models.TextChoices):
    SUPER_ADMIN = 'super_admin', 'Super Administrateur'
    ADMIN_ENT = 'admin_ent', 'Admin Entreprise'
    GESTIONNAIRE = 'gestionnaire', 'Gestionnaire de stock'
    RESPONSABLE_ACHAT = 'responsable_achat', 'Responsable achat'
    MAGASINIER = 'magasinier', 'Magasinier'
    AUDITEUR = 'auditeur', 'Auditeur'
    COMPTABLE = 'comptable', 'Comptable'

class Utilisateur(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=50, choices=RoleUtilisateur.choices, default=RoleUtilisateur.ADMIN_ENT)
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, null=True, blank=True, related_name='utilisateurs')
    est_actif = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)  # optionnel

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    def get_roles_autorises(self):
        if not self.entreprise:
            return []
        return self.entreprise.get_roles_disponibles()

    def peut_avoir_role(self, role):
        return role in self.get_roles_autorises()

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"
       
    
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='accounts_utilisateur_set',  # ← unique
        blank=True,
        verbose_name='groups',
        help_text='The groups this user belongs to.',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='accounts_utilisateur_set',  # ← unique
        blank=True,
        verbose_name='user permissions',
        help_text='Specific permissions for this user.',
    )

class EmailConfirmationToken(models.Model):
    user = models.OneToOneField(Utilisateur, on_delete=models.CASCADE, related_name='confirmation_token')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        from django.utils import timezone
        return (timezone.now() - self.created_at).total_seconds() < 86400  # 24h

class InvitationToken(models.Model):
    user = models.OneToOneField(Utilisateur, on_delete=models.CASCADE, related_name='invitation_token')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        from django.utils import timezone
        return (timezone.now() - self.created_at).total_seconds() < 86400  # 24h