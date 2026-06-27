from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from apps.entreprises.models import Entreprise, TypeEntreprise
from apps.accounts.models import Utilisateur
from apps.accounts.decorators import superadmin_required
from .models import AuditLog

# ==================== DASHBOARD ====================
@superadmin_required
def dashboard(request):
    context = {
        'total_entreprises': Entreprise.objects.count(),
        'entreprises_actives': Entreprise.objects.filter(est_active=True).count(),
        'entreprises_inactives': Entreprise.objects.filter(est_active=False).count(),
        'total_users': Utilisateur.objects.count(),
        'users_actifs': Utilisateur.objects.filter(is_active=True).count(),
        'dernieres_entreprises': Entreprise.objects.order_by('-created_at')[:5],
        'derniers_utilisateurs': Utilisateur.objects.order_by('-date_joined')[:5],
        'entreprises_inactives_liste': Entreprise.objects.filter(est_active=False)[:10],
    }
    return render(request, 'superadmin/dashboard.html', context)

# ==================== ENTREPRISES ====================
@superadmin_required
def liste_entreprises(request):
    entreprises = Entreprise.objects.all().order_by('-created_at')

    # Filtres
    q = request.GET.get('q')
    if q:
        entreprises = entreprises.filter(nom__icontains=q)

    statut = request.GET.get('statut')
    if statut == 'active':
        entreprises = entreprises.filter(est_active=True)
    elif statut == 'inactive':
        entreprises = entreprises.filter(est_active=False)

    type_ent = request.GET.get('type')
    if type_ent:
        entreprises = entreprises.filter(type_entreprise=type_ent)

    # Pagination
    paginator = Paginator(entreprises, 20)
    page = request.GET.get('page', 1)
    try:
        entreprises_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        entreprises_page = paginator.page(1)

    context = {
        'entreprises': entreprises_page,
        'types_entreprise': TypeEntreprise.choices,
    }
    return render(request, 'superadmin/entreprise_liste.html', context)

@superadmin_required
def activer_entreprise(request, entreprise_id):
    entreprise = get_object_or_404(Entreprise, id=entreprise_id)
    entreprise.est_active = True
    entreprise.save()
    messages.success(request, f"L'entreprise {entreprise.nom} a été activée.")
    return redirect('superadmin:entreprises')

@superadmin_required
def desactiver_entreprise(request, entreprise_id):
    entreprise = get_object_or_404(Entreprise, id=entreprise_id)
    entreprise.est_active = False
    entreprise.save()
    messages.warning(request, f"L'entreprise {entreprise.nom} a été désactivée.")
    return redirect('superadmin:entreprises')

@superadmin_required
def detail_entreprise(request, entreprise_id):
    entreprise = get_object_or_404(Entreprise, id=entreprise_id)
    utilisateurs = entreprise.utilisateurs.all()
    context = {
        'entreprise': entreprise,
        'utilisateurs': utilisateurs,
    }
    return render(request, 'superadmin/entreprise_detail.html', context)

@superadmin_required
def supprimer_entreprise_view(request, pk):
    entreprise = get_object_or_404(Entreprise, id=pk)
    if request.method == 'POST':
        entreprise.est_active = False
        entreprise.save()
        messages.warning(request, f"L'entreprise {entreprise.nom} a été désactivée (soft delete).")
        return redirect('superadmin:entreprises')
    return redirect('superadmin:entreprises')

# ==================== UTILISATEURS ====================
@superadmin_required
def liste_utilisateurs(request):
    utilisateurs = Utilisateur.objects.all().order_by('-date_joined')

    q = request.GET.get('q')
    if q:
        utilisateurs = utilisateurs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )

    role = request.GET.get('role')
    if role:
        utilisateurs = utilisateurs.filter(role=role)

    statut = request.GET.get('statut')
    if statut == 'actif':
        utilisateurs = utilisateurs.filter(is_active=True)
    elif statut == 'inactif':
        utilisateurs = utilisateurs.filter(is_active=False)

    entreprise_id = request.GET.get('entreprise')
    if entreprise_id:
        utilisateurs = utilisateurs.filter(entreprise_id=entreprise_id)

    paginator = Paginator(utilisateurs, 20)
    page = request.GET.get('page', 1)
    try:
        utilisateurs_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        utilisateurs_page = paginator.page(1)

    context = {
        'utilisateurs': utilisateurs_page,
        'entreprises_liste': Entreprise.objects.all(),
    }
    return render(request, 'superadmin/utilisateurs_liste.html', context)

@superadmin_required
def activer_utilisateur(request, user_id):
    user = get_object_or_404(Utilisateur, id=user_id)
    user.is_active = True
    user.est_actif = True
    user.save()
    messages.success(request, f"L'utilisateur {user.email} a été activé.")
    return redirect('superadmin:utilisateurs')

@superadmin_required
def desactiver_utilisateur(request, user_id):
    user = get_object_or_404(Utilisateur, id=user_id)
    user.is_active = False
    user.est_actif = False
    user.save()
    messages.warning(request, f"L'utilisateur {user.email} a été désactivé.")
    return redirect('superadmin:utilisateurs')

@superadmin_required
def changer_role_view(request, pk):
    user = get_object_or_404(Utilisateur, id=pk)
    if request.method == 'POST':
        new_role = request.POST.get('role')
        if new_role in dict(Utilisateur.RoleUtilisateur.choices):
            user.role = new_role
            user.save()
            messages.success(request, f"Rôle de {user.get_full_name()} mis à jour : {user.get_role_display()}.")
        else:
            messages.error(request, "Rôle invalide.")
        return redirect('superadmin:utilisateurs')
    return redirect('superadmin:utilisateurs')

# ==================== LOGS ====================

@superadmin_required
def logs_audit_view(request):
    logs = AuditLog.objects.all()
    return render(request, 'superadmin/logs_audit.html', {'logs': logs})