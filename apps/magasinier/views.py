from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import csv

from apps.accounts.decorators import role_required
from apps.stock.models import (
    Produit, Stock, Mouvement, TypeMouvement, Entrepot, Emplacement,
    InventaireSession, LigneInventaire, Alerte, ScanLog
)
from apps.gestionnaire.views import _appliquer_mouvement, _verifier_seuil

def _entreprise(request):
    return request.user.entreprise


# ---------- Dashboard ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def dashboard_magasinier(request):
    ent = _entreprise(request)
    # Sessions d'inventaire en cours
    inventaires_en_cours = InventaireSession.objects.filter(
        entrepot__entreprise=ent, statut='en_cours'
    ).select_related('entrepot')[:5]
    # Alertes (lecture seule)
    alertes = Alerte.objects.filter(produit__entreprise=ent, lue=False)[:5]
    # Derniers mouvements effectués par le magasinier
    mouvements_recents = Mouvement.objects.filter(
        utilisateur=request.user, produit__entreprise=ent
    ).order_by('-date_mouvement')[:10]
    context = {
        'inventaires_en_cours': inventaires_en_cours,
        'alertes': alertes,
        'mouvements_recents': mouvements_recents,
        'nb_alertes': alertes.count(),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'produits_count': Produit.objects.filter(entreprise=ent, est_actif=True).count(),
    }
    return render(request, 'magasinier/dashboard.html', context)


# ---------- Scan rapide ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def scan_view(request):
    ent = _entreprise(request)
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True)
    return render(request, 'magasinier/scan.html', {'entrepots': entrepots})


@login_required
@role_required('magasinier', 'admin_ent', 'gestionnaire', 'super_admin')
@require_http_methods(["GET", "POST"])
def api_scan(request):
    if request.method == 'GET':
        # Recherche de produit par code-barres (GET)
        code = request.GET.get('code', '').strip()
        if not code:
            return JsonResponse({'found': False, 'message': 'Code vide'})
        ent = _entreprise(request)
        produit = Produit.objects.filter(Q(code_barres=code) | Q(sku=code), entreprise=ent).first()
        if produit:
            return JsonResponse({
                'found': True,
                'id': str(produit.id),
                'nom': produit.nom,
                'sku': produit.sku,
                'stock_total': float(produit.quantite_totale()),
                'seuil_alerte': float(produit.seuil_alerte),
            })
        return JsonResponse({'found': False, 'message': f'Produit introuvable pour le code "{code}"'})

    elif request.method == 'POST':
        # Enregistrement du mouvement (votre code existant)
        data = json.loads(request.body)
        code = data.get('code', '').strip()
        action = data.get('action', '')  # 'entree' ou 'sortie'
        quantite = float(data.get('quantite', 1))
        entrepot_id = data.get('entrepot_id')
        produit = Produit.objects.filter(
            Q(code_barres=code) | Q(sku=code), entreprise=_entreprise(request)
        ).first()

        # Log du scan
        ScanLog.objects.create(
            utilisateur=request.user,
            produit=produit,
            code_barre_scanne=code,
            action_attendue=action,
            succes=bool(produit),
            message_erreur='' if produit else f"Code non trouvé : {code}"
        )

        if not produit:
            return JsonResponse({'success': False, 'error': 'Produit non trouvé'})

        if not entrepot_id:
            return JsonResponse({'success': False, 'error': 'Entrepôt non spécifié'})

        try:
            entrepot = Entrepot.objects.get(pk=entrepot_id, entreprise=_entreprise(request))
        except Entrepot.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Entrepôt invalide'})

        if action not in ('entree', 'sortie'):
            return JsonResponse({'success': False, 'error': 'Action non reconnue'})
        if quantite <= 0:
            return JsonResponse({'success': False, 'error': 'Quantité invalide'})

        # Créer le mouvement et l'appliquer dans la même transaction : si le
        # stock est insuffisant, _appliquer_mouvement lève ValidationError et
        # tout est annulé (pas de mouvement fantôme jamais appliqué).
        try:
            with transaction.atomic():
                if action == 'entree':
                    mouv = Mouvement.objects.create(
                        type_mouvement=TypeMouvement.ENTREE,
                        produit=produit,
                        quantite=quantite,
                        entrepot_destination=entrepot,
                        utilisateur=request.user,
                        reference=f"SCAN-{timezone.now().timestamp()}",
                        note=f"Scan rapide par {request.user.get_full_name()}"
                    )
                else:
                    mouv = Mouvement.objects.create(
                        type_mouvement=TypeMouvement.SORTIE,
                        produit=produit,
                        quantite=quantite,
                        entrepot_source=entrepot,
                        utilisateur=request.user,
                        reference=f"SCAN-{timezone.now().timestamp()}",
                        note=f"Scan rapide par {request.user.get_full_name()}"
                    )
                _appliquer_mouvement(mouv)
        except ValidationError as e:
            return JsonResponse({'success': False, 'error': e.messages[0] if hasattr(e, 'messages') else str(e)})
        _verifier_seuil(produit, entrepot)

        return JsonResponse({
            'success': True,
            'produit': {
                'nom': produit.nom,
                'sku': produit.sku,
                'stock_actuel': float(produit.quantite_totale())
            }
        })


# ---------- Consultation des stocks ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def consultation_stock(request):
    ent = _entreprise(request)
    
    # Récupérer tous les entrepôts de l'entreprise
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True)
    
    # Récupérer les produits actifs
    produits_qs = Produit.objects.filter(entreprise=ent, est_actif=True).select_related('categorie')
    
    # Filtres
    q = request.GET.get('q', '')
    entrepot_id = request.GET.get('entrepot', '')
    statut = request.GET.get('statut', '')
    
    if q:
        produits_qs = produits_qs.filter(Q(nom__icontains=q) | Q(sku__icontains=q) | Q(code_barres__icontains=q))
    
    # Enrichir les produits
    produits_list = []
    for p in produits_qs:
        qte_totale = p.quantite_totale()
        if qte_totale is None:
            qte_totale = 0
        seuil = p.seuil_alerte or 0
        # Déterminer statut
        if qte_totale == 0:
            statut_produit = 'rupture'
        elif qte_totale <= seuil:
            statut_produit = 'alerte'
        else:
            statut_produit = 'ok'
        
        # Filtre par statut
        if statut and statut != statut_produit:
            continue
        
        # Stock par entrepôt (pour affichage détails)
        stocks_par_entrepot = Stock.objects.filter(produit=p, entrepot__entreprise=ent).values('entrepot__nom').annotate(total=Sum('quantite'))
        
        # Filtre par entrepôt (si spécifié, on exclut les produits sans stock dans cet entrepôt)
        if entrepot_id:
            if not Stock.objects.filter(produit=p, entrepot_id=entrepot_id, quantite__gt=0).exists():
                continue
        
        produits_list.append({
            'id': p.id,
            'nom': p.nom,
            'sku': p.sku,
            'categorie': p.categorie,
            'quantite_totale': float(qte_totale),
            'seuil_alerte': float(seuil),
            'stocks_par_entrepot': list(stocks_par_entrepot),
            'statut': statut_produit,
        })
    
    # Pagination
    paginator = Paginator(produits_list, 20)
    page_number = request.GET.get('page', 1)
    produits_page = paginator.get_page(page_number)
    
    # Compteurs (sur l'ensemble des produits après filtres, pas paginés)
    total_produits = len(produits_list)  # ou produits_qs.count() pour le total sans filtres
    nb_rupture = sum(1 for p in produits_list if p['statut'] == 'rupture')
    nb_alerte = sum(1 for p in produits_list if p['statut'] == 'alerte')
    
    context = {
        'produits': produits_page,
        'entrepots': entrepots,
        'total_produits': total_produits,
        'nb_rupture': nb_rupture,
        'nb_alerte': nb_alerte,
    }
    return render(request, 'magasinier/stocks.html', context)

# ---------- Mouvement rapide (formulaire) ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def mouvement_rapide(request):
    ent = _entreprise(request)
    if request.method == 'POST':
        produit_id = request.POST.get('produit')
        try:
            quantite = float(request.POST.get('quantite', 1))
        except ValueError:
            quantite = 0
        type_mvt = request.POST.get('type_mouvement')
        entrepot_id = request.POST.get('entrepot')

        if not produit_id or not type_mvt or not entrepot_id:
            messages.error(request, "Tous les champs obligatoires doivent être remplis.")
            return redirect('magasinier:mouvement_rapide')
        if type_mvt not in ('entree', 'sortie'):
            messages.error(request, "Type de mouvement invalide.")
            return redirect('magasinier:mouvement_rapide')
        if quantite <= 0:
            messages.error(request, "La quantité doit être strictement positive.")
            return redirect('magasinier:mouvement_rapide')

        produit = get_object_or_404(Produit, pk=produit_id, entreprise=ent)
        entrepot = get_object_or_404(Entrepot, pk=entrepot_id, entreprise=ent)

        try:
            with transaction.atomic():
                if type_mvt == 'entree':
                    mouv = Mouvement.objects.create(
                        type_mouvement=TypeMouvement.ENTREE,
                        produit=produit,
                        quantite=quantite,
                        entrepot_destination=entrepot,
                        utilisateur=request.user,
                        note="Mouvement rapide magasinier"
                    )
                else:
                    mouv = Mouvement.objects.create(
                        type_mouvement=TypeMouvement.SORTIE,
                        produit=produit,
                        quantite=quantite,
                        entrepot_source=entrepot,
                        utilisateur=request.user,
                        note="Mouvement rapide magasinier"
                    )
                _appliquer_mouvement(mouv)
        except ValidationError as e:
            messages.error(request, e.messages[0] if hasattr(e, 'messages') else str(e))
            return redirect('magasinier:mouvement_rapide')
        _verifier_seuil(produit, entrepot)
        messages.success(request, f"{quantite} {produit.unite_mesure} enregistré(s).")
        return redirect('magasinier:mouvement_rapide')

    produits = Produit.objects.filter(entreprise=ent, est_actif=True).order_by('nom')
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True)
    return render(request, 'magasinier/mouvement_rapide.html', {
        'produits': produits,
        'entrepots': entrepots,
    })


# ---------- Gestion des inventaires ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def inventaire_list(request):
    ent = _entreprise(request)
    sessions = InventaireSession.objects.filter(entrepot__entreprise=ent).select_related('entrepot')
    statut = request.GET.get('statut')
    if statut:
        sessions = sessions.filter(statut=statut)
    paginator = Paginator(sessions.order_by('-date_debut'), 20)
    page = request.GET.get('page', 1)
    sessions_page = paginator.get_page(page)
    return render(request, 'magasinier/inventaire_list.html', {
        'sessions': sessions_page,
        'statut_sel': statut,
    })


@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def inventaire_create(request):
    ent = _entreprise(request)
    if request.method == 'POST':
        entrepot_id = request.POST.get('entrepot')
        entrepot = get_object_or_404(Entrepot, pk=entrepot_id, entreprise=ent)
        session = InventaireSession.objects.create(
            entrepot=entrepot,
            utilisateur_demarrage=request.user,
            statut='en_cours'
        )
        # Pré-remplir les lignes avec le stock théorique actuel
        stocks = Stock.objects.filter(entrepot=entrepot).select_related('produit', 'emplacement')
        lignes = []
        for s in stocks:
            lignes.append(LigneInventaire(
                session=session,
                produit=s.produit,
                emplacement=s.emplacement,
                quantite_theorique=s.quantite,
                quantite_comptee=None
            ))
        LigneInventaire.objects.bulk_create(lignes)
        messages.success(request, f"Session d'inventaire créée pour {entrepot.nom}.")
        return redirect('magasinier:inventaire_detail', pk=session.pk)
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True)
    return render(request, 'magasinier/inventaire_create.html', {'entrepots': entrepots})


@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def inventaire_detail(request, pk):
    ent = _entreprise(request)
    session = get_object_or_404(InventaireSession, pk=pk, entrepot__entreprise=ent)
    lignes = session.lignes.select_related('produit', 'emplacement').order_by('produit__nom')
    if request.method == 'POST':
        # Sauvegarde des quantités comptées
        for ligne in lignes:
            val = request.POST.get(f'quantite_{ligne.pk}')
            if val is not None and val.strip() != '':
                ligne.quantite_comptee = float(val)
                ligne.save()
        messages.success(request, "Comptage sauvegardé.")
        return redirect('magasinier:inventaire_detail', pk=pk)
    return render(request, 'magasinier/inventaire_detail.html', {
        'session': session,
        'lignes': lignes,
    })


# ---------- Historique des mouvements ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def historique(request):
    ent = _entreprise(request)
    mouvements = Mouvement.objects.filter(produit__entreprise=ent).select_related('produit', 'entrepot_source', 'entrepot_destination')
    q = request.GET.get('q')
    if q:
        mouvements = mouvements.filter(Q(produit__nom__icontains=q) | Q(produit__sku__icontains=q))
    type_mvt = request.GET.get('type')
    if type_mvt:
        mouvements = mouvements.filter(type_mouvement=type_mvt)
    paginator = Paginator(mouvements.order_by('-date_mouvement'), 30)
    page = request.GET.get('page', 1)
    mouvements_page = paginator.get_page(page)
    return render(request, 'magasinier/historique.html', {
        'mouvements': mouvements_page,
        'q': q,
        'type_sel': type_mvt,
        'types_mouvement': TypeMouvement.choices,
    })


# ---------- Alertes (lecture seule) ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def alertes(request):
    ent = _entreprise(request)
    alertes = Alerte.objects.filter(produit__entreprise=ent, lue=False).select_related('produit')
    return render(request, 'magasinier/alertes.html', {'alertes': alertes})


# ---------- Paramètres (préférences) ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def parametres(request):
    # Simplifié : on peut stocker dans la session ou un modèle UserPreferences
    if request.method == 'POST':
        entrepot_defaut = request.POST.get('entrepot_defaut')
        if entrepot_defaut:
            request.session['magasinier_entrepot_defaut'] = entrepot_defaut
        messages.success(request, "Préférences enregistrées.")
        return redirect('magasinier:parametres')
    entrepot_defaut = request.session.get('magasinier_entrepot_defaut')
    entrepots = Entrepot.objects.filter(entreprise=_entreprise(request), est_actif=True)
    return render(request, 'magasinier/parametres.html', {
        'entrepots': entrepots,
        'entrepot_defaut': entrepot_defaut,
    })

@login_required
@require_GET
def produit_search_ajax(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    ent = _entreprise(request)
    produits = Produit.objects.filter(entreprise=ent, est_actif=True, nom__icontains=q)[:10]
    data = [{
        'id': str(p.id),
        'nom': p.nom,
        'sku': p.sku,
        'stock_total': float(p.quantite_totale()),
    } for p in produits]
    return JsonResponse(data, safe=False)