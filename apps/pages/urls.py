from django.urls import path
from . import views

app_name = 'pages'
urlpatterns = [
    path('', views.AccueilView.as_view(), name='accueil'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    path('entreprises/', views.EntreprisesView.as_view(), name='entreprises'),
    path('entreprises/avis/', views.soumettre_avis, name='soumettre_avis'),
    path('faq/', views.FAQView.as_view(), name='faq'),
    path('politique/', views.PolitiqueView.as_view(), name='politique'),
    path('mentions-legales/', views.MentionsLegalesView.as_view(), name='mentions_legales'),
    path('conditions/', views.ConditionsView.as_view(), name='conditions'),
]