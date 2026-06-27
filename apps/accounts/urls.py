from django.urls import path, reverse_lazy
from django.contrib.auth.views import LogoutView
from django.contrib.auth.views import PasswordResetConfirmView, PasswordResetDoneView, PasswordResetCompleteView
from . import views


app_name = 'accounts'

urlpatterns = [
    # Authentification
    path('connexion/', views.ConnexionView.as_view(), name='connexion'),
    path('restauration/', views.RestaurationView.as_view(), name='restauration'),
    
    
# Réinitialisation du mot de passe – étapes
    path('restauration/confirmation/',
         PasswordResetDoneView.as_view(template_name='accounts/reset_done.html'),
         name='password_reset_done'),

    path('restauration/confirmer/<uidb64>/<token>/',
         PasswordResetConfirmView.as_view(
             template_name='accounts/reset_confirm.html',
             success_url=reverse_lazy('accounts:password_reset_complete')
         ),
         name='password_reset_confirm'),

    path('restauration/complete/',
         PasswordResetCompleteView.as_view(template_name='accounts/reset_complete.html'),
         name='password_reset_complete'),


    # Inscription – wizard
    path('inscription/', views.inscription_wizard, name='inscription'),
    path('inscription/confirmation/', views.confirmation_inscription, name='inscription_confirmation'),
    
    # Activation email
    path('confirmer/<str:token>/', views.confirmer_email, name='confirmation_email'),
    
    path('deconnexion/', LogoutView.as_view(next_page='pages:accueil'), name='logout'),
    
    path('invitation/<str:token>/', views.accept_invitation, name='accept_invitation'),
]