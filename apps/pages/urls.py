from django.urls import path
from . import views

app_name = 'pages'
urlpatterns = [
    path('', views.AccueilView.as_view(), name='accueil'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    path('entreprises/', views.EntreprisesView.as_view(), name='entreprises'),
    path('faq/', views.FAQView.as_view(), name='faq'),
    path('politique/', views.PolitiqueView.as_view(), name='politique'),
]