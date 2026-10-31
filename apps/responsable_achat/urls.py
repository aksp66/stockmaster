from django.urls import path
from . import views

app_name = 'responsable_achat'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # Fournisseurs
    path('fournisseurs/', views.fournisseur_list, name='fournisseur_list'),
    path('fournisseurs/ajouter/', views.fournisseur_create, name='fournisseur_create'),
    path('fournisseurs/<uuid:pk>/', views.fournisseur_detail, name='fournisseur_detail'),
    path('fournisseurs/<uuid:pk>/modifier/', views.fournisseur_edit, name='fournisseur_edit'),
    path('fournisseurs/<uuid:pk>/supprimer/', views.fournisseur_delete, name='fournisseur_delete'),
    # Bons de commande
    path('commandes/', views.boncommande_list, name='boncommande_list'),
    path('commandes/creer/', views.boncommande_create, name='boncommande_create'),
    path('commandes/<uuid:pk>/', views.boncommande_detail, name='boncommande_detail'),
    path('commandes/<uuid:pk>/modifier/', views.boncommande_edit, name='boncommande_edit'),
    path('commandes/<uuid:pk>/statut/<str:statut>/', views.boncommande_changer_statut, name='boncommande_statut'),
    path('commandes/<uuid:pk>/reception/', views.boncommande_reception, name='boncommande_reception'),
    path('commandes/<uuid:pk>/envoyer/', views.boncommande_envoyer, name='boncommande_envoyer'),
    path('commandes/<uuid:pk>/cloturer/', views.boncommande_cloturer, name='boncommande_cloturer'),
    path('commandes/<uuid:pk>/annuler/', views.boncommande_annuler, name='boncommande_annuler'),
    path('commandes/<uuid:pk>/pdf/', views.boncommande_pdf, name='boncommande_pdf'),
    # IA et autres
    path('suggestions/', views.suggestions_list, name='suggestions_list'),
    path('predictions/', views.predictions_list, name='predictions_list'),
    path('exports/', views.exports_view, name='exports'),
    path('parametres/', views.settings_view, name='settings'),
]