from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from apps.accounts.models import Utilisateur, RoleUtilisateur
from apps.core.models import AuditLog, TypeAction
from apps.entreprises.models import THEMES, Entreprise, ParametresEntreprise
from decimal import Decimal, InvalidOperation
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from apps.stock.reappro import calculer_reappro
from apps.accounts.decorators import role_required
from .forms import EntrepotForm
from django.db import models
from django.core.paginator import Paginator
from django.http import HttpResponse
import csv
from apps.core import csv_safe
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

def _dernier_admin(utilisateur):
    """True si c'est le seul admin actif de son entreprise : le supprimer, le désactiver ou le rétrograder
    laisserait l'entreprise sans personne pour la gérer."""
    return (utilisateur.role == RoleUtilisateur.ADMIN_ENT and utilisateur.is_active
            and not Utilisateur.objects.filter(entreprise=utilisateur.entreprise, role=RoleUtilisateur.ADMIN_ENT,
                                               is_active=True).exclude(pk=utilisateur.pk).exists())


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
        AuditLog.log(request, TypeAction.CREATION_USER, f"Invitation de {email} au rôle {user.get_role_display()}", user)
        lien = request.build_absolute_uri(reverse('accounts:accept_invitation', args=[token_str]))
        
        sujet = "Invitation à rejoindre StockMaster"
        html_message = render_to_string('emails/invitation_email.html', {
            'first_name': first_name,
            'inviter_nom': request.user.get_full_name(),
            'lien': lien,
        })
        plain_message = strip_tags(html_message)
        try:
            send_mail(
                subject=sujet,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception:
            # Le compte existe déjà : on donne le lien à transmettre manuellement
            messages.warning(request, f"Compte créé, mais l'email n'a pas pu être envoyé. "
                                      f"Transmettez ce lien d'activation à {email} : {lien}")
            return redirect('admin_entreprise:utilisateurs')

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
        if utilisateur == request.user and nouveau_role != ancien_role:
            messages.error(request, "Vous ne pouvez pas modifier votre propre rôle.")
            nouveau_role = ancien_role
        if nouveau_role in request.user.entreprise.get_roles_disponibles():
            if nouveau_role != ancien_role and _dernier_admin(utilisateur):
                messages.error(request, "Impossible : c'est le dernier administrateur actif de l'entreprise.")
                nouveau_role = ancien_role
            utilisateur.role = nouveau_role
        utilisateur.save()
        if nouveau_role != ancien_role:
            AuditLog.log(request, TypeAction.CHANGEMENT_ROLE,
                         f"Rôle de {utilisateur.email} : {dict(RoleUtilisateur.choices).get(ancien_role)} → "
                         f"{utilisateur.get_role_display()}", utilisateur, {'role': ancien_role}, {'role': nouveau_role})
        else:
            AuditLog.log(request, TypeAction.MODIFICATION_USER, f"Utilisateur {utilisateur.email} modifié", utilisateur)
        messages.success(request, f"Utilisateur {utilisateur.email} modifié.")
        
        # Prévenir l'utilisateur par email si son rôle a changé
        if request.user != utilisateur and nouveau_role != ancien_role:
            html_message = render_to_string('emails/role_changed.html', {
                'first_name': utilisateur.first_name,
                'nouveau_role': dict(RoleUtilisateur.choices).get(nouveau_role),
                'entreprise': utilisateur.entreprise.nom,
            })
            plain_message = strip_tags(html_message)
            send_mail(
                subject="Changement de rôle sur StockMaster",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
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
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect('admin_entreprise:utilisateurs')
    if request.method == 'POST':
        if _dernier_admin(user):
            messages.error(request, "Impossible : c'est le dernier administrateur actif de l'entreprise.")
            return redirect('admin_entreprise:utilisateurs')
        AuditLog.log(request, TypeAction.SUPPRESSION_USER, f"Utilisateur {user.email} supprimé", user, {'role': user.role}, None)
        user.delete()
        messages.success(request, f"L'utilisateur {user.email} a été supprimé.")
        return redirect('admin_entreprise:utilisateurs')
    # Optionnel : afficher une page de confirmation
    return render(request, 'admin_entreprise/confirmer_suppression.html', {'utilisateur': user})

@login_required
@role_required('super_admin', 'admin_ent')
def desactiver_utilisateur(request, user_id):
    utilisateur = get_object_or_404(Utilisateur, id=user_id, entreprise=request.user.entreprise)
    if request.method != 'POST':
        return redirect('admin_entreprise:utilisateurs')
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect('admin_entreprise:utilisateurs')
    if _dernier_admin(utilisateur):
        messages.error(request, "Impossible : c'est le dernier administrateur actif de l'entreprise.")
        return redirect('admin_entreprise:utilisateurs')
    utilisateur.is_active = not utilisateur.is_active
    utilisateur.est_actif = utilisateur.is_active
    utilisateur.save()
    AuditLog.log(request, TypeAction.ACTIVATION_USER if utilisateur.is_active else TypeAction.DESACTIVATION_USER,
                 f"Utilisateur {utilisateur.email} {'activé' if utilisateur.is_active else 'désactivé'}", utilisateur)
    messages.success(request, f"Utilisateur {'activé' if utilisateur.is_active else 'désactivé'}.")
    return redirect('admin_entreprise:utilisateurs')

@login_required
@role_required('super_admin', 'admin_ent')
def modifier_entreprise(request):
    entreprise = request.user.entreprise
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        try:
            nb_entrepots = int(request.POST.get('nb_entrepots') or 1)
        except ValueError:
            nb_entrepots = -1
        if not nom or nb_entrepots < 0:
            messages.error(request, "Le nom est obligatoire et le nombre d'entrepôts doit être un entier positif.")
            return redirect('admin_entreprise:entreprise_edit')
        entreprise.nom = nom
        entreprise.pays = request.POST.get('pays', '').strip()
        entreprise.ville = request.POST.get('ville', '').strip()
        entreprise.taille = request.POST.get('taille', '').strip()
        entreprise.nb_entrepots = nb_entrepots
        entreprise.save()
        messages.success(request, "Informations mises à jour.")
        return redirect('admin_entreprise:entreprise_edit')
    return render(request, 'admin_entreprise/entreprise_edit.html', {'entreprise': entreprise})

@login_required
@role_required('super_admin', 'admin_ent')
def parametres(request):
    params = ParametresEntreprise.pour(request.user.entreprise)
    options = [
        ("Alertes de stock par email (rupture, seuil bas, expiration)", 'alertes_email'),
        ("Rapport hebdomadaire (chaque lundi)", 'rapport_hebdo'),
        ("Suggestions d'achat IA par email (chaque matin)", 'ia_email'),
    ]
    if request.method == 'POST':
        section = request.POST.get('section')
        if section == 'notifications':
            for _, champ in options:
                setattr(params, champ, request.POST.get(champ) == 'on')
            params.save()
            AuditLog.log(request, TypeAction.PARAMETRES, "Préférences de notification modifiées", params)
            messages.success(request, "Préférences de notification enregistrées.")
        elif section == 'apparence':
            code = request.POST.get('theme')
            if code in {c for c, *_ in THEMES}:
                avant = params.theme
                params.theme = code
                params.save()
                AuditLog.log(request, TypeAction.PARAMETRES, f"Thème de l'entreprise : {avant} → {code}", params,
                             {'theme': avant}, {'theme': code})
                messages.success(request, "Thème enregistré : il s'applique à tous les utilisateurs de l'entreprise.")
            else:
                messages.error(request, "Thème inconnu.")
        elif section == 'seuils':
            try:
                seuil = Decimal(request.POST.get('seuil_defaut', ''))
                jours = int(request.POST.get('jours_expiration', ''))
            except (InvalidOperation, ValueError):
                seuil = jours = None
            if seuil is None or seuil < 0 or not 1 <= jours <= 365:
                messages.error(request, "Seuil (≥ 0) et délai d'expiration (1 à 365 jours) invalides.")
            else:
                params.seuil_alerte_defaut, params.jours_alerte_expiration = seuil, jours
                params.save()
                AuditLog.log(request, TypeAction.PARAMETRES, f"Seuils par défaut : alerte {seuil}, expiration {jours} jours", params)
                messages.success(request, "Seuils par défaut enregistrés.")
        return redirect('admin_entreprise:parametres')
    return render(request, 'admin_entreprise/parametres.html', {
        'notif_options': [(label, champ, getattr(params, champ)) for label, champ in options],
        'themes': [{'code': c, 'nom': n, 'sidebar': sb, 'principal': pr, 'clair': cl} for c, n, sb, pr, cl in THEMES],
        'theme_actuel': params.theme,
        'seuil_defaut': params.seuil_alerte_defaut,
        'jours_expiration': params.jours_alerte_expiration,
    })

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
        a_historique = (entrepot.mouvements_entrants.exists() or entrepot.mouvements_sortants.exists()
                        or entrepot.stocks.filter(quantite__gt=0).exists())
        AuditLog.log(request, TypeAction.AUTRE, f"Entrepôt « {entrepot.nom} » "
                     f"{'désactivé (historique conservé)' if a_historique else 'supprimé'}", entrepot)
        if a_historique:
            entrepot.est_actif = False
            entrepot.save(update_fields=['est_actif', 'updated_at'])
            messages.warning(request, "Cet entrepôt a un historique de stock : il a été désactivé au lieu d'être supprimé.")
        else:
            entrepot.delete()
            messages.success(request, "Entrepôt supprimé.")
        return redirect('admin_entreprise:entrepot_list')
    return render(request, 'admin_entreprise/entrepot_confirm_delete.html', {'entrepot': entrepot})

@role_required('admin_ent', 'super_admin')
def ia_dashboard(request):
    entreprise = request.user.entreprise
    toutes = PredictionStock.objects.filter(produit__entreprise=entreprise)
    # La tâche IA crée une nouvelle prédiction chaque jour : on n'affiche que la plus récente par produit
    plus_recente = toutes.filter(produit=OuterRef('produit')).order_by('-created_at', '-date_cible').values('pk')[:1]
    predictions = list(toutes.filter(pk=Subquery(plus_recente)).select_related('produit'))

    for p in predictions:
        # Quantité prévue et bornes = totaux entre la date du calcul et la date cible
        p.horizon = max((p.date_cible - timezone.localdate(p.created_at)).days, 1)
        p.conso_jour = p.quantite_prevue / p.horizon
        p.confiance_pct = None if p.confiance is None else round(p.confiance * 100 if p.confiance <= 1 else p.confiance)
        reappro = calculer_reappro(p.produit)  # même calcul que les suggestions d'achat
        p.a_commander, p.jours_rupture = reappro['quantite_suggeree'], reappro['jours_rupture']
    # Produits à commander d'abord, les plus proches de la rupture en tête
    predictions.sort(key=lambda p: (not p.a_commander, p.jours_rupture is None, p.jours_rupture or 0, p.produit.nom))

    confiances = [p.confiance_pct for p in predictions if p.confiance_pct is not None]
    context = {
        'predictions': predictions[:20],
        'nb_predictions': len(predictions),
        'nb_recommandations': sum(1 for p in predictions if p.a_commander),
        'confiance_moyenne': round(sum(confiances) / len(confiances)) if confiances else None,
        'derniere_analyse': max((p.created_at for p in predictions), default=None),
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
    if request.method != 'POST':
        return redirect('admin_entreprise:ia_dashboard')
    try:
        # Vérifier que Celery peut se connecter au broker
        current_app.control.ping(timeout=1.0)
    except CeleryError:
        messages.error(request, "Le service d'analyse IA n'est pas disponible. Contactez l'administrateur.")
        return redirect('admin_entreprise:ia_dashboard')
    
    analyser_entreprise_immediate.delay(str(entreprise.id))
    AuditLog.log(request, TypeAction.IA_ANALYSE, "Analyse IA déclenchée pour tous les produits", entreprise)
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
    writer = csv_safe.writer(response)
    writer.writerow(['Nom', 'Email', 'Rôle', 'Actif', 'Date inscription'])
    for u in utilisateurs:
        writer.writerow([u.get_full_name(), u.email, u.get_role_display(), u.is_active, u.date_joined.strftime('%d/%m/%Y')])
    return response

def export_entrepots_csv(request):
    entreprise = request.user.entreprise
    entrepots = Entrepot.objects.filter(entreprise=entreprise)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="entrepots.csv"'
    writer = csv_safe.writer(response)
    writer.writerow(['Nom', 'Adresse', 'Ville', 'Pays', 'Responsable'])
    for e in entrepots:
        writer.writerow([e.nom, e.adresse, e.ville, e.pays, e.responsable.get_full_name() if e.responsable else ''])
    return response

def export_predictions_csv(request):
    entreprise = request.user.entreprise
    predictions = PredictionStock.objects.filter(produit__entreprise=entreprise).select_related('produit')         .order_by('produit__nom', '-created_at')
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="predictions_ia.csv"'
    writer = csv_safe.writer(response)
    writer.writerow(['Produit', 'Calculée le', 'Date cible', 'Consommation prévue (total)', 'Consommation / jour',
                     'Borne basse (total)', 'Borne haute (total)', 'Confiance (%)', 'Quantité recommandée'])
    for p in predictions:
        jours = max((p.date_cible - timezone.localdate(p.created_at)).days, 1)
        confiance = None if p.confiance is None else round(p.confiance * 100 if p.confiance <= 1 else p.confiance)
        writer.writerow([
            p.produit.nom, timezone.localdate(p.created_at).strftime('%d/%m/%Y'), p.date_cible.strftime('%d/%m/%Y'),
            p.quantite_prevue, round(p.quantite_prevue / jours, 2), p.borne_inferieure, p.borne_superieure,
            confiance, p.quantite_recommandee_commande,
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
                categorie.parent = categories.filter(pk=parent_id).first()
            categorie.save()
            messages.success(request, "Catégorie ajoutée.")
            return redirect('admin_entreprise:categories')
    return render(request, 'admin_entreprise/categories.html', {'categories': categories})