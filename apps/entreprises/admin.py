from django.contrib import admin

from .models import ParametresEntreprise


@admin.register(ParametresEntreprise)
class ParametresEntrepriseAdmin(admin.ModelAdmin):
    list_display = ('entreprise', 'alertes_email', 'rapport_hebdo', 'ia_email',
                    'seuil_alerte_defaut', 'jours_alerte_expiration', 'modifie_le')
