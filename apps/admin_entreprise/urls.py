from django.urls import path
from . import views


app_name = 'admin_entreprise'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('utilisateurs/', views.gestion_utilisateurs, name='utilisateurs'),
    path('utilisateurs/ajouter/', views.ajouter_utilisateur, name='ajouter_utilisateur'),
    path('utilisateurs/modifier/<uuid:user_id>/', views.modifier_utilisateur, name='modifier_utilisateur'),
    path('utilisateurs/desactiver/<uuid:user_id>/', views.desactiver_utilisateur, name='desactiver_utilisateur'),
    path('utilisateurs/supprimer/<uuid:user_id>/', views.supprimer_utilisateur, name='supprimer_utilisateur'),
    path('entreprise/', views.modifier_entreprise, name='entreprise_edit'),
    path('parametres/', views.parametres, name='parametres'),
    path('entrepots/', views.entrepot_list, name='entrepot_list'),
    path('entrepots/ajouter/', views.entrepot_create, name='entrepot_ajouter'),
    path('entrepots/modifier/<uuid:pk>/', views.entrepot_edit, name='entrepot_modifier'),
    path('entrepots/supprimer/<uuid:pk>/', views.entrepot_delete, name='entrepot_supprimer'),
    path('ia/', views.ia_dashboard, name='ia_dashboard'),
    path('ia/lancer/', views.ia_lancer, name='ia_lancer'),
    path('exports/', views.exports_view, name='exports'),
    path('categories/', views.categories_view, name='categories'),
]