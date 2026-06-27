from django.urls import path
from . import views

app_name = 'magasinier'
urlpatterns = [
    path('', views.dashboard_magasinier, name='dashboard'),
    path('scan/', views.scan_view, name='scan'),
    path('api/scan/', views.api_scan, name='api_scan'),
    path('stocks/', views.consultation_stock, name='stocks'),
    path('mouvement/', views.mouvement_rapide, name='mouvement_rapide'),
    path('inventaire/', views.inventaire_list, name='inventaire_list'),
    path('inventaire/creer/', views.inventaire_create, name='inventaire_create'),
    path('inventaire/<uuid:pk>/', views.inventaire_detail, name='inventaire_detail'),
    path('historique/', views.historique, name='historique'),
    path('alertes/', views.alertes, name='alertes'),
    path('parametres/', views.parametres, name='parametres'),
    path('api/produits/search/', views.produit_search_ajax, name='produit_search_ajax'),
]