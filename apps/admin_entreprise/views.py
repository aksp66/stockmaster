from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from apps.accounts.models import Utilisateur, RoleUtilisateur
from apps.entreprises.models import Entreprise
from apps.accounts.decorators import role_required
from .forms import EntrepotForm
from django.db import models
from django.core.paginator import Paginator
from django.http import HttpResponse
import csv
from apps.stock.models import Entrepot, Categorie, PredictionStock, Alerte, Produit
from apps.accounts.models import RoleUtilisateur
from django.utils.crypto import get_random_string
from apps.accounts.models import InvitationToken
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from celery import current_app
from celery.exceptions import CeleryError



@login_required
@role_required('admin_ent', 'super_admin')
def dashboard(request):
    entreprise = request.user.entreprise
    utilisateurs = entreprise.utilisateurs.all()
    total_users = utilisateurs.count()
    users_actifs = utilisateurs.filter(is_active=True).count()
    
    # Entrepôts
    entrepots_qs = Entrepot.objects.filter(entreprise=entreprise)
    total_entrepots = entrepots_qs.count()
    
    # Produits
    total_produits = Produit.objects.filter(entreprise=entreprise).count()
    
    # Rôles distincts
    total_roles = utilisateurs.values('role').distinct().count()
    
    # Derniers utilisateurs
    derniers_utilisateurs = utilisateurs.order_by('-date_joined')[:5]
    
    # Entrepôts pour l'affichage dans le dashboard
    entrepots = entrepots_qs[:10]  # ou tous, selon le besoin
    
    # Alertes (optionnel, pour le bloc de droite)
    alertes_recentes = Alerte.objects.filter(produit__entreprise=entreprise, lue=False).order_by('-created_at')[:5]
    alertes_count = alertes_recentes.count()
    
    # Prédictions IA pour l'affichage (optionnel)
    predictions_ia = PredictionStock.objects.filter(produit__entreprise=entreprise).order_by('-date_cible')[:3]
    
    context = {
        'total_users': total_users,
        'users_actifs': users_actifs,
        'total_entrepots': total_entrepots,
        'entrepots': entrepots,
        'total_produits': total_produits,
        'total_roles': total_roles,
        'derniers_utilisateurs': derniers_utilisateurs,
        'alertes_recentes': alertes_recentes,
        'alertes_count': alertes_count,
        'predictions_ia': predictions_ia,
    }
    return render(request, 'admin_entreprise/dashboard.html', context)

@login_required
@role_required('super_admin', 'admin_ent')
def gestion_utilisateurs(request):
    utilisateurs = request.user.entreprise.utilisateurs.all()
    roles_disponibles = request.user.entreprise.get_roles_disponibles()
    return render(request, 'admin_entreprise/utilisateurs.html', {
        'utilisateurs': utilisateurs,
        'roles_disponibles': roles_disponibles,
    })

@role_required('admin_ent', 'super_admin')
def ajouter_utilisateur(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        role = request.POST.get('role')
        
        # Vérification si l'email existe déjà
        if Utilisateur.objects.filter(email=email).exists():
            messages.error(request, f"Un utilisateur avec l'email {email} existe déjà.")
            return redirect('admin_entreprise:utilisateurs')
        
        # Vérification du rôle autorisé
        if role not in request.user.entreprise.get_roles_disponibles():
            messages.error(request, "Rôle non autorisé pour cette entreprise.")
            return redirect('admin_entreprise:utilisateurs')
        
        # Création de l'utilisateur (désactivé)
        password = get_random_string(12)
        user = Utilisateur.objects.create_user(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
            role=role,
            entreprise=request.user.entreprise,
            est_actif=False,
            is_active=False,
        )
        
        # Création d'un token d'invitation
        token_str = get_random_string(64)
        InvitationToken.objects.create(user=user, token=token_str)
        lien = request.build_absolute_uri(reverse('accounts:accept_invitation', args=[token_str]))
        
        sujet = "Invitation à rejoindre StockMaster"
        html_message = render_to_string('emails/invitation_email.html', {
            'first_name': first_name,
            'inviter_nom': request.user.get_full_name(),
            'lien': lien,
        })
        plain_message = strip_tags(html_message)
        send_mail(
            subject=sujet,
            message=plain_message,
            from_email='StockMaster <noreply@stockmaster.tg>',
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        
        messages.success(request, f"Invitation envoyée à {email}.")
        return redirect('admin_entreprise:utilisateurs')
    
    # GET : afficher le formulaire
    roles_codes = request.user.entreprise.get_roles_disponibles()
    roles_disponibles = [(code, dict(RoleUtilisateur.choices).get(code, code)) for code in roles_codes]
    return render(request, 'admin_entreprise/utilisateur_form.html', {'roles_disponibles': roles_disponibles})


@login_required
@role_required('super_admin', 'admin_ent')
def modifier_utilisateur(request, user_id):
    utilisateur = get_object_or_404(Utilisateur, id=user_id, entreprise=request.user.entreprise)
    if request.method == 'POST':
        ancien_role = utilisateur.role
        utilisateur.first_name = request.POST.get('first_name')
        utilisateur.last_name = request.POST.get('last_name')
        nouveau_role = request.POST.get('role')
        if nouveau_role in request.user.entreprise.get_roles_disponibles():
            utilisateur.role = nouveau_role
        utilisateur.save()
        messages.success(request, f"Utilisateur {utilisateur.email} modifié.")
        
        # Si l'utilisateur modifié est celui qui est connecté, on l'informe que son rôle a changé
        if request.user == utilisateur:
            messages.info(request, f"Votre rôle a été modifié : {dict(RoleUtilisateur.choices).get(ancien_role)} → {dict(RoleUtilisateur.choices).get(nouveau_role)}. Déconnectez-vous et reconnectez-vous pour voir les changements complets.")
        else:
            if request.user != utilisateur:
                html_message = render_to_string('emails/role_changed.html', {
                    'first_name': utilisateur.first_name,
                    'nouveau_role': dict(RoleUtilisateur.choices).get(nouveau_role),
                    'entreprise': utilisateur.entreprise.nom,
                })
                plain_message = strip_tags(html_message)
                send_mail(
                    subject="Changement de rôle sur StockMaster",
                    message=plain_message,
                    from_email='StockMaster <ahlipedro66@gmail.com>',
                    recipient_list=[utilisateur.email],
                    html_message=html_message,
                    fail_silently=True,
                )
        
        return redirect('admin_entreprise:utilisateurs')
    else:
        roles_codes = request.user.entreprise.get_roles_disponibles()
        roles_disponibles = [(code, dict(RoleUtilisateur.choices).get(code, code)) for code in roles_codes]
        return render(request, 'admin_entreprise/utilisateur_form.html', {
            'utilisateur': utilisateur,
            'roles_disponibles': roles_disponibles,
        })

@login_required
@role_required('admin_ent', 'super_admin')
def supprimer_utilisateur(request, user_id):
    user = get_object_or_404(Utilisateur, id=user_id, entreprise=request.user.entreprise)
    if request.method == 'POST':
        user.delete()
        messages.success(request, f"L'utilisateur {user.email} a été supprimé.")
        return redirect('admin_entreprise:utilisateurs')
    # Optionnel : afficher une page de confirmation
    return render(request, 'admin_entreprise/confirmer_suppression.html', {'utilisateur': user})

@login_required
@role_required('super_admin', 'admin_ent')
def desactiver_utilisateur(request, user_id):
    utilisateur = get_object_or_404(Utilisateur, id=user_id, entreprise=request.user.entreprise)
    utilisateur.is_active = not utilisateur.is_active
    utilisateur.est_actif = utilisateur.is_active
    utilisateur.save()
    messages.success(request, f"Utilisateur {'activé' if utilisateur.is_active else 'désactivé'}.")
    return redirect('admin_entreprise:utilisateurs')

@login_required
@role_required('super_admin', 'admin_ent')
def modifier_entreprise(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        entreprise.nom = request.POST.get('nom')
        entreprise.pays = request.POST.get('pays')
        entreprise.ville = request.POST.get('ville')
        entreprise.taille = request.POST.get('taille')
        entreprise.nb_entrepots = request.POST.get('nb_entrepots')
        entreprise.save()
        messages.success(request, "Informations mises à jour.")
        return redirect('admin_entreprise:entreprise_edit')
    return render(request, 'admin_entreprise/entreprise_edit.html', {'entreprise': entreprise})

@login_required
@role_required('super_admin', 'admin_ent')
def parametres(request):
    return render(request, 'admin_entreprise/parametres.html')

@role_required('admin_ent', 'super_admin')
def entrepot_list(request):
    entrepots = Entrepot.objects.filter(entreprise=request.user.entreprise)
    return render(request, 'admin_entreprise/entrepot_list.html', {'entrepots': entrepots})

@role_required('admin_ent', 'super_admin')
def entrepot_create(request):
    if request.method == 'POST':
        form = EntrepotForm(request.POST, initial={'entreprise': request.user.entreprise})
        if form.is_valid():
            e = form.save(commit=False)
            e.entreprise = request.user.entreprise
            e.save()
            messages.success(request, "Entrepôt créé avec succès.")
            return redirect('admin_entreprise:entrepot_list')
    else:
        form = EntrepotForm(initial={'entreprise': request.user.entreprise})
    return render(request, 'admin_entreprise/entrepot_form.html', {'form': form})

@role_required('admin_ent', 'super_admin')
def entrepot_edit(request, pk):
    entrepot = get_object_or_404(Entrepot, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        form = EntrepotForm(request.POST, instance=entrepot, initial={'entreprise': request.user.entreprise})
        if form.is_valid():
            form.save()
            messages.success(request, "Entrepôt modifié.")
            return redirect('admin_entreprise:entrepot_list')
    else:
        form = EntrepotForm(instance=entrepot, initial={'entreprise': request.user.entreprise})
    return render(request, 'admin_entreprise/entrepot_form.html', {'form': form, 'entrepot': entrepot})

@role_required('admin_ent', 'super_admin')
def entrepot_delete(request, pk):
    entrepot = get_object_or_404(Entrepot, pk=pk, entreprise=request.user.entreprise)
    if request.method == 'POST':
        entrepot.delete()
        messages.success(request, "Entrepôt supprimé.")
        return redirect('admin_entreprise:entrepot_list')
    return render(request, 'admin_entreprise/entrepot_confirm_delete.html', {'entrepot': entrepot})

@role_required('admin_ent', 'super_admin')
def ia_dashboard(request):
    entreprise = request.user.entreprise
    # Queryset complet (non slicé)
    qs = PredictionStock.objects.filter(produit__entreprise=entreprise)
    
    # Statistiques globales
    nb_predictions = qs.count()
    nb_recommandations = qs.filter(quantite_recommandee_commande__isnull=False).count()
    
    # Agrégation de la confiance moyenne
    agg = qs.aggregate(avg_confiance=models.Avg('confiance'))
    precision_moyenne = agg.get('avg_confiance')
    if precision_moyenne is not None:
        precision_moyenne = round(precision_moyenne)
    
    # Dernière analyse (date de la prédiction la plus récente)
    derniere = qs.order_by('-created_at').first()
    derniere_analyse = derniere.created_at if derniere else None
    
    # Prédictions pour l'affichage (slice uniquement à la fin)
    predictions = qs.order_by('-date_cible')[:20]
    
    context = {
        'predictions': predictions,
        'nb_predictions': nb_predictions,
        'nb_recommandations': nb_recommandations,
        'precision_moyenne': precision_moyenne,
        'derniere_analyse': derniere_analyse,
        'modele_actif': 'Prophet / RandomForest',
        'steps_ia': [
            {'icon': 'database', 'titre': 'Collecte', 'desc': 'Analyse historique des mouvements'},
            {'icon': 'cogs', 'titre': 'Modélisation', 'desc': 'Prophet & RandomForest'},
            {'icon': 'lightbulb', 'titre': 'Recommandations', 'desc': 'Commandes suggérées avec confiance'},
        ],
    }
    return render(request, 'admin_entreprise/ia_dashboard.html', context)

from apps.ia.tasks import analyser_entreprise_immediate

@role_required('admin_ent', 'super_admin')
def ia_lancer(request):
    entreprise = request.user.entreprise
    try:
        # Vérifier que Celery peut se connecter au broker
        current_app.control.ping(timeout=1.0)
    except CeleryError:
        messages.error(request, "Le service d'analyse IA n'est pas disponible. Contactez l'administrateur.")
        return redirect('admin_entreprise:ia_dashboard')
    
    analyser_entreprise_immediate.delay(str(entreprise.id))
    messages.success(request, "Analyse IA déclenchée. Les résultats seront disponibles sous peu.")
    return redirect('admin_entreprise:ia_dashboard')

@role_required('admin_ent', 'super_admin')
def exports_view(request):
    """Export des données (CSV, Excel, PDF)"""
    type_export = request.GET.get('type', '')
    if type_export == 'utilisateurs':
        return export_utilisateurs_csv(request)
    elif type_export == 'entrepots':
        return export_entrepots_csv(request)
    elif type_export == 'ia':
        return export_predictions_csv(request)
    else:
        return render(request, 'admin_entreprise/exports.html')

def export_utilisateurs_csv(request):
    entreprise = request.user.entreprise
    utilisateurs = entreprise.utilisateurs.all()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="utilisateurs.csv"'
    writer = csv.writer(response)
    writer.writerow(['Nom', 'Email', 'Rôle', 'Actif', 'Date inscription'])
    for u in utilisateurs:
        writer.writerow([u.get_full_name(), u.email, u.get_role_display(), u.is_active, u.date_joined.strftime('%d/%m/%Y')])
    return response

def export_entrepots_csv(request):
    entreprise = request.user.entreprise
    entrepots = Entrepot.objects.filter(entreprise=entreprise)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="entrepots.csv"'
    writer = csv.writer(response)
    writer.writerow(['Nom', 'Adresse', 'Ville', 'Pays', 'Responsable'])
    for e in entrepots:
        writer.writerow([e.nom, e.adresse, e.ville, e.pays, e.responsable.get_full_name() if e.responsable else ''])
    return response

def export_predictions_csv(request):
    entreprise = request.user.entreprise
    predictions = PredictionStock.objects.filter(produit__entreprise=entreprise)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="predictions_ia.csv"'
    writer = csv.writer(response)
    writer.writerow(['Produit', 'Date cible', 'Quantité prévue', 'Borne inf', 'Borne sup', 'Confiance', 'Recommandation'])
    for p in predictions:
        writer.writerow([
            p.produit.nom, p.date_cible.strftime('%d/%m/%Y'), p.quantite_prevue,
            p.borne_inferieure, p.borne_superieure, p.confiance,
            p.quantite_recommandee_commande
        ])
    return response

@role_required('admin_ent', 'super_admin')
def categories_view(request):
    """Gestion des catégories de produits"""
    entreprise = request.user.entreprise
    categories = Categorie.objects.filter(entreprise=entreprise)
    if request.method == 'POST':
        nom = request.POST.get('nom')
        parent_id = request.POST.get('parent')
        if nom:
            categorie = Categorie(nom=nom, entreprise=entreprise)
            if parent_id:
                categorie.parent_id = parent_id
            categorie.save()
            messages.success(request, "Catégorie ajoutée.")
            return redirect('admin_entreprise:categories')
    return render(request, 'admin_entreprise/categories.html', {'categories': categories})