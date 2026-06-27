from django.urls import path
from . import views

app_name = 'gestionnaire'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('tableau-de-bord/', views.dashboard, name='tableau_bord'),

    # Produits
    path('produits/', views.produits_liste, name='produits'),
    path('produits/liste/', views.produits_liste, name='produit_list'),      # alias utilisé dans les templates
    path('produits/ajouter/', views.produit_form, name='produit_ajouter'),
    path('produits/creer/', views.produit_form, name='produit_create'),      # alias utilisé
    path('produits/<uuid:pk>/modifier/', views.produit_form, name='produit_modifier'),
    path('produits/<uuid:pk>/editer/', views.produit_form, name='produit_edit'),  # alias utilisé
    path('produits/<uuid:pk>/', views.produit_detail, name='produit_detail'),
    path('produits/<uuid:pk>/supprimer/', views.produit_delete, name='produit_delete'),
    path('produits/importer/', views.produit_import, name='produit_import'),
    path('api/produits/recherche/', views.produit_search_ajax, name='produit_search_ajax'),

    # Mouvements
    path('mouvements/', views.mouvements_liste, name='mouvements'),
    path('mouvements/liste/', views.mouvements_liste, name='mouvement_list'),  # alias utilisé
    path('mouvements/enregistrer/', views.mouvement_form, name='mouvement_form'),
    path('mouvements/creer/', views.mouvement_form, name='mouvement_create'),  # alias utilisé

    # Scan
    path('scan/', views.scan_view, name='scan'),
    path('api/scan/', views.api_scan, name='api_scan'),

    # Inventaires
    path('inventaires/', views.inventaires_liste, name='inventaires'),
    path('inventaires/', views.inventaires_liste, name='inventaire_session_list'),
    path('inventaires/liste/', views.inventaires_liste, name='inventaire_list'),  # alias utilisé
    path('inventaires/creer/', views.inventaire_creer, name='inventaire_creer'),
    path('inventaires/creer/', views.inventaire_creer, name='inventaire_session_create'),  # alias utilisé
    path('inventaires/<uuid:pk>/saisie/', views.inventaire_saisie, name='inventaire_session_detail'),
    path('inventaires/<uuid:pk>/annuler/', views.inventaire_session_annuler, name='inventaire_session_annuler'),
    path('inventaires/<uuid:pk>/valider/', views.inventaire_valider, name='inventaire_valider'),
    path('inventaires/<uuid:pk>/saisie/', views.inventaire_saisie, name='inventaire_saisie'),

    # Alertes
    path('alertes/', views.alertes_liste, name='alertes'),
    path('alertes/<uuid:pk>/acquitter/', views.alerte_acquitter, name='alerte_acquitter'),
    path('alertes/acquitter-toutes/', views.alertes_acquitter_toutes, name='alertes_acquitter_toutes'),

    # Transfert
    path('transfert/', views.transfert_view, name='transfert'),

    # Rapports
    path('rapports/', views.rapports_view, name='rapports'),

    # Emplacements
    path('emplacements/', views.emplacements_view, name='emplacements'),

    # Catégories 
    path('categories/', views.categories_list, name='categories'),
]