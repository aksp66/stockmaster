from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from apps.entreprises.models import Entreprise

from .models import Avis


def statistiques_publiques():
    """Chiffres affichés sur le site public, tous issus de la base : entreprises activées et avis publiés."""
    avis = Avis.objects.filter(est_publie=True).aggregate(
        moyenne=Avg('note'), total=Count('id'), positifs=Count('id', filter=Q(note__gte=4)))
    stats = {'nb_entreprises': Entreprise.objects.filter(est_active=True).count(), 'nb_avis': avis['total']}
    if avis['total']:
        stats.update(
            note_moyenne=round(avis['moyenne'], 1),
            note_etoiles=round(avis['moyenne']),
            pct_recommande=round(avis['positifs'] * 100 / avis['total']),
        )
    return stats


class AccueilView(TemplateView):
    template_name = 'pages/accueil.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(statistiques_publiques())
        ctx['derniers_avis'] = Avis.objects.filter(est_publie=True).select_related('entreprise')[:3]
        return ctx

class ContactView(TemplateView):
    template_name = 'pages/contact.html'

class EntreprisesView(TemplateView):
    template_name = 'pages/entreprises.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request
        publies = Avis.objects.filter(est_publie=True).select_related('entreprise')
        filtre = request.GET.get('filtre')
        if filtre == '5':
            publies = publies.filter(note=5)
        elif filtre == '4':
            publies = publies.filter(note__gte=4)
        elif filtre == 'recent':
            publies = publies.order_by('-date_publication')
        ctx['avis_publies'] = Paginator(publies, 9).get_page(request.GET.get('page'))
        ctx.update(statistiques_publiques())
        user = request.user
        if user.is_authenticated:
            ctx['entreprise_valide'] = bool(user.entreprise and user.entreprise.est_active)
            ctx['avis_deja_existe'] = Avis.objects.filter(utilisateur=user).exists()
            ctx['avis_sousmis'] = ctx['avis_deja_existe'] and request.GET.get('avis') == 'envoye'
        return ctx


@login_required
@require_POST
def soumettre_avis(request):
    """Enregistre l'avis de l'utilisateur connecté (non publié tant qu'il n'est pas modéré)."""
    retour = reverse('pages:entreprises')
    user = request.user
    if not (user.entreprise and user.entreprise.est_active):
        messages.error(request, "Votre compte doit être rattaché à une entreprise cliente active pour laisser un avis.")
        return redirect(f"{retour}#laisser-avis")
    if Avis.objects.filter(utilisateur=user).exists():
        return redirect(f"{retour}#laisser-avis")

    d = request.POST
    try:
        note = int(d.get('note', 0))
    except ValueError:
        note = 0
    commentaire = d.get('commentaire', '').strip()
    champs = {k: d.get(k, '').strip() for k in ('prenom', 'nom', 'poste')}
    erreurs = []
    if not 1 <= note <= 5:
        erreurs.append("Choisissez une note entre 1 et 5 étoiles.")
    if not all(champs.values()):
        erreurs.append("Prénom, nom et poste sont obligatoires.")
    if not 50 <= len(commentaire) <= 500:
        erreurs.append("Votre avis doit contenir entre 50 et 500 caractères.")
    if not d.get('accord_publication'):
        erreurs.append("Vous devez accepter la publication de votre avis.")
    if erreurs:
        for e in erreurs:
            messages.error(request, e)
        return redirect(f"{retour}#laisser-avis")

    Avis.objects.create(utilisateur=user, entreprise=user.entreprise, note=note, commentaire=commentaire, **champs)
    messages.success(request, "Merci ! Votre avis sera publié après vérification.")
    return redirect(f"{retour}?avis=envoye#laisser-avis")


class FAQView(TemplateView):
    template_name = 'pages/faq.html'

    def get_context_data(self, **kwargs):
        from .faq_data import CATEGORIES, faqs
        return super().get_context_data(faq_categories=CATEGORIES, faqs=faqs(), **kwargs)

class PageJuridiqueView(TemplateView):
    """Pages juridiques : l'identité de l'éditeur vient des réglages (LEGAL_* dans .env)."""

    def get_context_data(self, **kwargs):
        from django.conf import settings
        legal = settings.LEGAL
        manquants = [cle for cle, valeur in legal.items() if not valeur]
        return super().get_context_data(legal=legal, manquants=manquants, **kwargs)


class MentionsLegalesView(PageJuridiqueView):
    template_name = 'pages/mentions_legales.html'


class ConditionsView(PageJuridiqueView):
    template_name = 'pages/conditions.html'


class PolitiqueView(TemplateView):
    template_name = 'pages/politique.html'
