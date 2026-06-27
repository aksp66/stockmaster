from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Utilisateur, EmailConfirmationToken
from apps.entreprises.models import Entreprise

class UtilisateurAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'entreprise', 'est_actif', 'is_active')
    list_filter = ('role', 'est_actif', 'is_active', 'entreprise')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informations personnelles', {'fields': ('first_name', 'last_name', 'username')}),
        ('Permissions', {'fields': ('role', 'entreprise', 'est_actif', 'is_active', 'groups', 'user_permissions')}),
        ('Dates importantes', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2', 'role', 'entreprise'),
        }),
    )

admin.site.register(Utilisateur, UtilisateurAdmin)
admin.site.register(Entreprise)
admin.site.register(EmailConfirmationToken)