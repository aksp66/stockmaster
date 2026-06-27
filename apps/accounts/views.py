from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.urls import reverse
from django.views.generic import TemplateView
from .forms import Step1TypeEntrepriseForm, Step2EntrepriseForm, Step3AdminForm
from apps.entreprises.models import Entreprise, TypeEntreprise
from .models import EmailConfirmationToken
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.contrib.auth.views import LoginView
from .models import InvitationToken
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse_lazy
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView, PasswordResetDoneView, PasswordResetCompleteView 



User = get_user_model()


def inscription_wizard(request):
    TYPE_DESCRIPTIONS = {
        'commerce_detail': "Boutique, épicerie, pharmacie, pièces auto",
        'gros_distribution': "Grossiste, matériel BTP, multi-entrepôts",
        'ecommerce': "Préparateur, dropshipping, retours",
        'industrie': "Fabrication, assemblage, matières premières",
        'sante': "Lots, dates exp., audit réglementaire",
        'restauration': "Denrées périssables, inventaire hebdo",
    }

    # Gestion du paramètre GET step
    if request.GET.get('step'):
        step = int(request.GET.get('step'))
        request.session['inscription_step'] = step
        return redirect('accounts:inscription')

    step = request.session.get('inscription_step', 1)

    if step > 1 and 'inscription_data' not in request.session:
        request.session['inscription_step'] = 1
        step = 1

    # Traitement POST
    if request.method == 'POST':
        if step == 1:
            form = Step1TypeEntrepriseForm(request.POST)
            if form.is_valid():
                request.session['inscription_data'] = {
                    'type_entreprise': form.cleaned_data['type_entreprise']
                }
                request.session['inscription_step'] = 2
                return redirect('accounts:inscription')
            # Si invalide, on conserve le formulaire avec erreurs
        elif step == 2:
            form = Step2EntrepriseForm(request.POST)
            if form.is_valid():
                data = request.session.get('inscription_data', {})
                data.update({
                    'nom': form.cleaned_data['nom'],
                    'pays': form.cleaned_data['pays'],
                    'ville': form.cleaned_data.get('ville', ''),
                    'taille': form.cleaned_data.get('taille', ''),
                    'nb_entrepots': form.cleaned_data['nb_entrepots'],
                })
                request.session['inscription_data'] = data
                request.session['inscription_step'] = 3
                return redirect('accounts:inscription')
            # Si invalide, on conserve le formulaire avec erreurs
        elif step == 3:
            form = Step3AdminForm(request.POST)
            if form.is_valid():
                data = request.session.get('inscription_data', {})
                entreprise = Entreprise.objects.create(
                    nom=data['nom'],
                    type_entreprise=data['type_entreprise'],
                    pays=data['pays'],
                    ville=data.get('ville', ''),
                    taille=data.get('taille', ''),
                    nb_entrepots=data.get('nb_entrepots', 1),
                    est_active=False,
                )
                user = User.objects.create_user(
                    username=form.cleaned_data['email'],
                    email=form.cleaned_data['email'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    password=form.cleaned_data['password1'],
                    role='admin_ent',
                    entreprise=entreprise,
                    est_actif=False,
                    is_active=False,
                )
                _envoyer_email_confirmation(request, user)
                request.session.pop('inscription_step', None)
                request.session.pop('inscription_data', None)
                return redirect('accounts:inscription_confirmation')
            else:
                # Renvoi immédiat du formulaire avec erreurs
                return render(request, 'accounts/inscription_step3.html', {'form': form, 'step': 3})
        # Pour les étapes 1 et 2, si le formulaire est invalide, on sort du if pour afficher le formulaire avec erreurs
        # (mais il faut récupérer le formulaire POST)
        if step == 1:
            form = Step1TypeEntrepriseForm(request.POST)
        elif step == 2:
            form = Step2EntrepriseForm(request.POST)
        else:
            # step == 3 déjà traité
            form = None
        if form and not form.is_valid():
            context = {'form': form, 'step': step}
            if step == 1:
                type_choices = [
                    (value, label, TYPE_DESCRIPTIONS.get(value, ""))
                    for value, label in TypeEntreprise.choices
                ]
                context['type_choices'] = type_choices
            return render(request, f'accounts/inscription_step{step}.html', context)
    else:
        # GET : formulaires vierges
        if step == 1:
            form = Step1TypeEntrepriseForm()
        elif step == 2:
            form = Step2EntrepriseForm()
        elif step == 3:
            form = Step3AdminForm()
        else:
            form = Step1TypeEntrepriseForm()

    context = {'form': form, 'step': step}
    if step == 1:
        type_choices = [
            (value, label, TYPE_DESCRIPTIONS.get(value, ""))
            for value, label in TypeEntreprise.choices
        ]
        context['type_choices'] = type_choices

    return render(request, f'accounts/inscription_step{step}.html', context)


def _envoyer_email_confirmation(request, user):
    token_str = get_random_string(64)
    EmailConfirmationToken.objects.update_or_create(user=user, defaults={'token': token_str})
    lien = request.build_absolute_uri(reverse('accounts:confirmation_email', args=[token_str]))
    sujet = "Confirmez votre compte – StockMaster"
    html_message = render_to_string('emails/confirmation_email.html', {
        'first_name': user.first_name,
        'lien': lien,
    })
    plain_message = strip_tags(html_message)
    send_mail(
        subject=sujet,
        message=plain_message,
        from_email='StockMaster <ahlipedro66@gmail.com>',
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def confirmer_email(request, token):
    """Active le compte de l'utilisateur après clic sur le lien."""
    from django.contrib.auth import login
    token_obj = get_object_or_404(EmailConfirmationToken, token=token)

    if token_obj.is_valid():
        user = token_obj.user
        user.est_actif = True
        user.is_active = True
        user.save()
        # Active aussi l'entreprise si besoin
        entreprise = user.entreprise
        if entreprise:
            entreprise.est_active = True
            entreprise.save()
        token_obj.delete()
        messages.success(request, "Votre compte a été activé ! Vous pouvez maintenant vous connecter.")
        # Option : connecter automatiquement l'utilisateur
        # login(request, user)
        return redirect('accounts:connexion')
    else:
        messages.error(request, "Le lien de confirmation a expiré. Veuillez demander un nouvel email.")
        return redirect('accounts:inscription')


def confirmation_inscription(request):
    """Page affichée après la création du compte (avant confirmation email)."""
    return render(request, 'accounts/confirmation.html')


class ConnexionView(LoginView):
    template_name = 'accounts/connexion.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        if user.role == 'super_admin':
            return reverse('superadmin:dashboard')
        elif user.role == 'admin_ent':
            return reverse('admin_entreprise:dashboard')   
        elif user.role == 'gestionnaire':
            return reverse('gestionnaire:dashboard')
        elif user.role == 'responsable_achat':
            return reverse('responsable_achat:dashboard')
        elif user.role == 'magasinier':
            return reverse('magasinier:dashboard')
        elif user.role == 'auditeur':
            return reverse('auditeur:dashboard')
        elif user.role == 'comptable':
            return reverse('comptable:dashboard')
        else:
            return reverse('pages:accueil')              # fallback

class RestaurationView(PasswordResetView):
    template_name = 'accounts/restauration.html'
    email_template_name = 'emails/password_reset_email.txt'           # version texte
    html_email_template_name = 'emails/password_reset_email.html'    # version HTML
    subject_template_name = 'emails/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')



def accept_invitation(request, token):
    token_obj = get_object_or_404(InvitationToken, token=token)
    if not token_obj.is_valid():
        messages.error(request, "Ce lien a expiré. Veuillez contacter l'administrateur.")
        return redirect('pages:accueil')
    user = token_obj.user
    if request.method == 'POST':
        password = request.POST.get('password1')
        password2 = request.POST.get('password2')
        if password and password == password2:
            user.set_password(password)
            user.is_active = True
            user.est_actif = True
            user.save()
            token_obj.delete()
            messages.success(request, "Votre compte est activé. Vous pouvez vous connecter.")
            return redirect('accounts:connexion')
        else:
            messages.error(request, "Les mots de passe ne correspondent pas.")
    return render(request, 'accounts/accept_invitation.html', {'user': user})