from django.contrib import admin
from django.utils import timezone

from .models import Avis


@admin.register(Avis)
class AvisAdmin(admin.ModelAdmin):
    list_display = ('prenom', 'nom', 'entreprise', 'note', 'est_publie', 'date_creation')
    list_filter = ('est_publie', 'note')
    search_fields = ('prenom', 'nom', 'entreprise__nom', 'commentaire')
    actions = ['publier', 'depublier']

    @admin.action(description="Publier les avis sélectionnés")
    def publier(self, request, queryset):
        queryset.filter(est_publie=False).update(est_publie=True, date_publication=timezone.now())

    @admin.action(description="Retirer de la publication")
    def depublier(self, request, queryset):
        queryset.update(est_publie=False)
