from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import HttpResponse
import csv
from apps.core import csv_safe
from datetime import date
from apps.entreprises.models import Entreprise, TypeEntreprise
from apps.accounts.models import Utilisateur, RoleUtilisateur
from django.views.decorators.http import require_POST
from apps.accounts.decorators import superadmin_required
from apps.core.models import AuditLog, TypeAction


def _super_admins_actifs():
    return Utilisateur.objects.filter(role=RoleUtilisateur.SUPER_ADMIN, is_active=True)


def _dernier_super_admin(user):
    """True si cet utilisateur est le seul super admin actif : le désactiver ou le rétrograder verrouillerait la plateforme."""
    return user.role == RoleUtilisateur.SUPER_ADMIN and user.is_active and not _super_admins_actifs().exclude(pk=user.pk).exists()


def _etat_entreprise(e):
    return {'est_active': e.est_active}


def _etat_utilisateur(u):
    return {'is_active': u.is_active, 'role': u.role}

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
@require_POST
def activer_entreprise(request, entreprise_id):
    entreprise = get_object_or_404(Entreprise, id=entreprise_id)
    avant = _etat_entreprise(entreprise)
    entreprise.est_active = True
    entreprise.save()
    AuditLog.log(request, TypeAction.ACTIVATION_ENT, f"Entreprise « {entreprise.nom} » activée", entreprise,
                 avant, _etat_entreprise(entreprise))
    messages.success(request, f"L'entreprise {entreprise.nom} a été activée.")
    return redirect('superadmin:entreprises')

@superadmin_required
@require_POST
def desactiver_entreprise(request, entreprise_id):
    entreprise = get_object_or_404(Entreprise, id=entreprise_id)
    avant = _etat_entreprise(entreprise)
    entreprise.est_active = False
    entreprise.save()
    AuditLog.log(request, TypeAction.DESACTIVATION_ENT, f"Entreprise « {entreprise.nom} » désactivée", entreprise,
                 avant, _etat_entreprise(entreprise))
    messages.warning(request, f"L'entreprise {entreprise.nom} a été désactivée.")
    return redirect('superadmin:entreprises')

@superadmin_required
def detail_entreprise(request, entreprise_id):
    entreprise = get_object_or_404(Entreprise, id=entreprise_id)
    utilisateurs = entreprise.utilisateurs.all()
    context = {
        'entreprise': entreprise,
        'utilisateurs': utilisateurs,
        'entrepots_count': entreprise.entrepots.count(),
        'produits_count': entreprise.produits.count(),
    }
    return render(request, 'superadmin/entreprise_detail.html', context)

@superadmin_required
@require_POST
def supprimer_entreprise_view(request, pk):
    """« Suppression » douce : l'entreprise est désactivée, ses données sont conservées."""
    entreprise = get_object_or_404(Entreprise, id=pk)
    avant = _etat_entreprise(entreprise)
    entreprise.est_active = False
    entreprise.save()
    AuditLog.log(request, TypeAction.SUPPRESSION_ENT, f"Entreprise « {entreprise.nom} » supprimée (désactivée, données conservées)",
                 entreprise, avant, _etat_entreprise(entreprise))
    messages.warning(request, f"L'entreprise {entreprise.nom} a été désactivée (suppression douce : ses données sont conservées).")
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
@require_POST
def activer_utilisateur(request, user_id):
    user = get_object_or_404(Utilisateur, id=user_id)
    avant = _etat_utilisateur(user)
    user.is_active = True
    user.est_actif = True
    user.save()
    AuditLog.log(request, TypeAction.ACTIVATION_USER, f"Utilisateur {user.email} activé", user, avant, _etat_utilisateur(user))
    messages.success(request, f"L'utilisateur {user.email} a été activé.")
    return redirect('superadmin:utilisateurs')

@superadmin_required
@require_POST
def desactiver_utilisateur(request, user_id):
    user = get_object_or_404(Utilisateur, id=user_id)
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect('superadmin:utilisateurs')
    if _dernier_super_admin(user):
        messages.error(request, "Impossible : c'est le dernier super administrateur actif.")
        return redirect('superadmin:utilisateurs')
    avant = _etat_utilisateur(user)
    user.is_active = False
    user.est_actif = False
    user.save()
    AuditLog.log(request, TypeAction.DESACTIVATION_USER, f"Utilisateur {user.email} désactivé", user, avant, _etat_utilisateur(user))
    messages.warning(request, f"L'utilisateur {user.email} a été désactivé.")
    return redirect('superadmin:utilisateurs')

@superadmin_required
@require_POST
def changer_role_view(request, pk):
    user = get_object_or_404(Utilisateur, id=pk)
    new_role = request.POST.get('role')
    if new_role not in dict(RoleUtilisateur.choices):
        messages.error(request, "Rôle invalide.")
    elif user == request.user:
        messages.error(request, "Vous ne pouvez pas modifier votre propre rôle.")
    elif _dernier_super_admin(user) and new_role != RoleUtilisateur.SUPER_ADMIN:
        messages.error(request, "Impossible : c'est le dernier super administrateur actif.")
    elif new_role != RoleUtilisateur.SUPER_ADMIN and user.entreprise_id is None:
        messages.error(request, "Cet utilisateur n'est rattaché à aucune entreprise : seul le rôle super administrateur lui convient.")
    elif new_role != user.role:
        avant = _etat_utilisateur(user)
        user.role = new_role
        user.save()
        AuditLog.log(request, TypeAction.CHANGEMENT_ROLE,
                     f"Rôle de {user.email} : {dict(RoleUtilisateur.choices)[avant['role']]} → {user.get_role_display()}",
                     user, avant, _etat_utilisateur(user))
        messages.success(request, f"Rôle de {user.get_full_name()} mis à jour : {user.get_role_display()}.")
    return redirect('superadmin:utilisateurs')

# ==================== LOGS ====================

FAMILLES_LOG = [
    ('activation', 'Activation', 'activation'),
    ('desactivation', 'Désactivation', 'desactivation'),
    ('role', 'Changement de rôle', 'changement_role'),
    ('suppression', 'Suppression', 'suppression'),
    ('connexion', 'Connexion', 'connexion'),
]


def _famille(type_action):
    """Famille d'affichage d'un type d'action (icône et couleur du journal)."""
    if type_action == TypeAction.CHANGEMENT_ROLE:
        return 'role'
    for cle in ('desactivation', 'activation', 'suppression', 'connexion'):
        if type_action.startswith(cle):
            return cle
    return 'autre'


@superadmin_required
def logs_audit_view(request):
    logs = AuditLog.objects.select_related('utilisateur', 'entreprise')
    q = request.GET.get('q', '').strip()
    if q:
        logs = logs.filter(Q(description__icontains=q) | Q(utilisateur__email__icontains=q) | Q(entreprise__nom__icontains=q))
    famille = request.GET.get('type_action', '')
    if famille == 'role':
        logs = logs.filter(type_action=TypeAction.CHANGEMENT_ROLE)
    elif famille in ('activation', 'desactivation', 'suppression', 'connexion'):
        logs = logs.filter(type_action__startswith=famille)
    for champ, op in (('date_debut', 'gte'), ('date_fin', 'lte')):
        try:
            jour = date.fromisoformat(request.GET.get(champ, ''))
        except ValueError:
            continue
        logs = logs.filter(**{f'created_at__date__{op}': jour})

    if request.GET.get('export') == 'csv':
        reponse = HttpResponse(content_type='text/csv; charset=utf-8')
        reponse['Content-Disposition'] = 'attachment; filename="logs_audit.csv"'
        reponse.write('\ufeff')
        w = csv_safe.writer(reponse, delimiter=';')
        w.writerow(['Date', 'Utilisateur', 'Entreprise', 'Action', 'Description', 'Adresse IP'])
        for log in logs[:5000]:
            w.writerow([log.created_at.strftime('%d/%m/%Y %H:%M:%S'), log.utilisateur.email if log.utilisateur else 'Système',
                        log.entreprise.nom if log.entreprise else '', log.get_type_action_display(), log.description,
                        log.ip_address or ''])
        return reponse

    page = Paginator(logs, 50).get_page(request.GET.get('page'))
    for log in page:
        log.famille = _famille(log.type_action)
    filtres = request.GET.copy()
    filtres.pop('page', None)
    filtres.pop('export', None)
    return render(request, 'superadmin/logs_audit.html', {'logs': page, 'page_obj': page, 'familles': FAMILLES_LOG,
                                                           'qs': filtres.urlencode()})
