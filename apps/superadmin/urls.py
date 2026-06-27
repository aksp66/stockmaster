from django.urls import path
from . import views


app_name = 'superadmin'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('entreprises/', views.liste_entreprises, name='entreprises'),
    path('entreprises/activer/<uuid:entreprise_id>/', views.activer_entreprise, name='activer_entreprise'),
    path('entreprises/desactiver/<uuid:entreprise_id>/', views.desactiver_entreprise, name='desactiver_entreprise'),
    path('entreprises/<uuid:entreprise_id>/', views.detail_entreprise, name='detail_entreprise'),
    path('utilisateurs/', views.liste_utilisateurs, name='utilisateurs'),
    path('utilisateurs/activer/<uuid:user_id>/', views.activer_utilisateur, name='activer_utilisateur'),
    path('utilisateurs/desactiver/<uuid:user_id>/', views.desactiver_utilisateur, name='desactiver_utilisateur'),
    path('utilisateurs/<uuid:pk>/changer-role/', views.changer_role_view, name='changer_role'),
    path('entreprises/<uuid:pk>/supprimer/', views.supprimer_entreprise_view, name='supprimer_entreprise'),
    path('logs/', views.logs_audit_view, name='logs'),
]