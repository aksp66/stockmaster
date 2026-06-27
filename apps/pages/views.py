from django.shortcuts import render

from django.views.generic import TemplateView

class AccueilView(TemplateView):
    template_name = 'pages/accueil.html'

class ContactView(TemplateView):
    template_name = 'pages/contact.html'

class EntreprisesView(TemplateView):
    template_name = 'pages/entreprises.html'

class FAQView(TemplateView):
    template_name = 'pages/faq.html'

class PolitiqueView(TemplateView):
    template_name = 'pages/politique.html'
