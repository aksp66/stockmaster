from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Q, Sum, Count, F
from django.db.models.functions import Coalesce
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET, require_http_methods
import json
import csv
import uuid
from decimal import Decimal, InvalidOperation

from apps.accounts.decorators import role_required
from apps.stock.models import (
    Produit, Stock, Mouvement, TypeMouvement, Entrepot, Emplacement, Categorie,
    InventaireSession, LigneInventaire, Alerte, ScanLog
)
from apps.gestionnaire.views import _appliquer_mouvement, _prix_saisi, _prix_vente_json, _verifier_seuil

def _entreprise(request):
    return request.user.entreprise


def _prefs(request):
    """Préférences du magasinier (session) : entrepôt et type de mouvement par défaut."""
    entrepot = request.session.get('magasinier_entrepot_defaut')
    try:
        entrepot = uuid.UUID(entrepot) if entrepot else None
    except ValueError:
        entrepot = None
    return {'entrepot_defaut_id': entrepot, 'type_defaut': request.session.get('magasinier_type_defaut', 'entree')}


def _produits_en_alerte(ent):
    """Produits actifs dont le stock total est sous le seuil, avec `total` annoté."""
    return (Produit.objects.filter(entreprise=ent, est_actif=True)
            .annotate(total=Coalesce(Sum('stocks__quantite'), Decimal(0)))
            .filter(total__lte=F('seuil_alerte')).order_by('total', 'nom'))


# ---------- Dashboard ----------
@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def dashboard_magasinier(request):
    ent = _entreprise(request)
    aujourd_hui = timezone.localdate()
    sessions_en_cours = InventaireSession.objects.filter(
        entrepot__entreprise=ent, statut='en_cours'
    ).select_related('entrepot').order_by('-date_debut')
    produits_alerte = list(_produits_en_alerte(ent)[:20])
    mouvements_recents = Mouvement.objects.filter(
        utilisateur=request.user, produit__entreprise=ent
    ).select_related('produit', 'entrepot_source', 'entrepot_destination').order_by('-date_mouvement')[:10]
    context = {
        'today': timezone.localtime(),
        'scans_aujourd_hui': ScanLog.objects.filter(utilisateur=request.user, created_at__date=aujourd_hui).count(),
        'mouvements_aujourd_hui': Mouvement.objects.filter(
            utilisateur=request.user, produit__entreprise=ent, date_mouvement__date=aujourd_hui).count(),
        'nb_alertes': _produits_en_alerte(ent).count(),
        'nb_inventaires_en_cours': sessions_en_cours.count(),
        'sessions_en_cours': sessions_en_cours[:5],
        'produits_alerte': produits_alerte,
        'mouvements_recents': mouvements_recents,
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'produits_count': Produit.objects.filter(entreprise=ent, est_actif=True).count(),
    }
    return render(request, 'magasinier/dashboard.html', context)


@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def scan_view(request):
    ent = _entreprise(request)
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True)
    # Historique du jour : mouvements saisis par ce magasinier aujourd'hui
    mouvements = Mouvement.objects.filter(
        utilisateur=request.user, produit__entreprise=ent, date_mouvement__date=timezone.localdate(),
    ).select_related('produit', 'entrepot_source', 'entrepot_destination').order_by('-date_mouvement')[:30]
    historique = [{
        'type': m.type_mouvement, 'produit': m.produit.nom, 'quantite': m.quantite,
        'entrepot': m.entrepot.nom if m.entrepot else '—',
        'heure': timezone.localtime(m.date_mouvement).strftime('%H:%M'),
    } for m in mouvements]
    return render(request, 'magasinier/scan.html', {
        'entrepots': entrepots, 'historique_session': historique,
        'entrepot_defaut_id': _prefs(request)['entrepot_defaut_id'],
    })


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
                'prix_vente': float(produit.prix_vente) if produit.prix_vente is not None else None,
            })
        return JsonResponse({'found': False, 'message': f'Produit introuvable pour le code "{code}"'})

    elif request.method == 'POST':
        # Page de scan : produit_id (produit déjà identifié par le GET) + type.
        # Également accepté : code (code-barres ou SKU) + action.
        try:
            data = json.loads(request.body)
            quantite = float(data.get('quantite', 1))
        except (ValueError, TypeError, AttributeError):
            return JsonResponse({'success': False, 'error': 'Requête invalide'}, status=400)
        ent = _entreprise(request)
        code = str(data.get('code') or '').strip()
        action = data.get('type') or data.get('action', '')  # 'entree' ou 'sortie'
        entrepot_id = data.get('entrepot_id')
        if data.get('produit_id'):
            try:
                produit = Produit.objects.filter(pk=data['produit_id'], entreprise=ent).first()
            except (ValueError, ValidationError):
                produit = None
            code = code or (produit.code_barres or produit.sku if produit else str(data['produit_id']))
        else:
            produit = Produit.objects.filter(Q(code_barres=code) | Q(sku=code), entreprise=ent).first()

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
            entrepot = Entrepot.objects.get(pk=entrepot_id, entreprise=ent)
        except (Entrepot.DoesNotExist, ValueError, ValidationError):
            return JsonResponse({'success': False, 'error': 'Entrepôt invalide'})

        if action not in ('entree', 'sortie'):
            return JsonResponse({'success': False, 'error': 'Action non reconnue'})
        if quantite <= 0:
            return JsonResponse({'success': False, 'error': 'Quantité invalide'})
        prix_vente, erreur = _prix_vente_json(data)
        if erreur:
            return JsonResponse({'success': False, 'error': erreur})
        note = str(data.get('motif') or '').strip() or f"Scan rapide par {request.user.get_full_name()}"

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
                        note=note,
                    )
                else:
                    mouv = Mouvement.objects.create(
                        type_mouvement=TypeMouvement.SORTIE,
                        produit=produit,
                        quantite=quantite,
                        entrepot_source=entrepot,
                        utilisateur=request.user,
                        reference=f"SCAN-{timezone.now().timestamp()}",
                        note=note,
                        prix_vente_snapshot=prix_vente,  # None : prix de vente du produit
                    )
                _appliquer_mouvement(mouv)
        except ValidationError as e:
            return JsonResponse({'success': False, 'error': e.messages[0] if hasattr(e, 'messages') else str(e)})
        _verifier_seuil(produit, entrepot)

        return JsonResponse({
            'success': True,
            'nouveau_stock': float(produit.quantite_totale()),
            'entrepot_nom': entrepot.nom,
            'heure': timezone.localtime(mouv.date_mouvement).strftime('%H:%M'),
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
                        note=request.POST.get('motif', '').strip() or "Mouvement rapide magasinier"
                    )
                else:
                    mouv = Mouvement.objects.create(
                        type_mouvement=TypeMouvement.SORTIE,
                        produit=produit,
                        quantite=quantite,
                        entrepot_source=entrepot,
                        utilisateur=request.user,
                        note=request.POST.get('motif', '').strip() or "Mouvement rapide magasinier",
                        prix_vente_snapshot=_prix_saisi(request.POST.get('prix_vente')),
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
    produit_id = request.GET.get('produit')
    produit_preselect = None
    if produit_id:
        try:
            produit_preselect = produits.filter(pk=produit_id).first()
        except ValidationError:
            produit_preselect = None
    return render(request, 'magasinier/mouvement_rapide.html', {
        'produits': produits,
        'entrepots': entrepots,
        'produit_preselect': produit_preselect,
        'entrepot_defaut_id': _prefs(request)['entrepot_defaut_id'],
        'type_initial': request.GET.get('type') if request.GET.get('type') in ('entree', 'sortie') else _prefs(request)['type_defaut'],
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
        'nb_en_cours': InventaireSession.objects.filter(entrepot__entreprise=ent, statut='en_cours').count(),
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
            statut='en_cours',
            note=request.POST.get('commentaire', '').strip(),
            masquer_stock=request.POST.get('masquer_stock') == 'on',
        )
        # Pré-remplir les lignes avec le stock théorique actuel (éventuellement limité à une catégorie)
        stocks = Stock.objects.filter(entrepot=entrepot).select_related('produit', 'emplacement')
        categorie_id = request.POST.get('categorie')
        if categorie_id:
            stocks = stocks.filter(produit__categorie_id=categorie_id, produit__categorie__entreprise=ent)
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
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True) \
        .annotate(nb_produits=Count('stocks__produit', distinct=True))
    return render(request, 'magasinier/inventaire_create.html', {
        'entrepots': entrepots,
        'categories': Categorie.objects.filter(entreprise=ent).order_by('nom'),
        'entrepot_defaut_id': _prefs(request)['entrepot_defaut_id'],
    })


@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def inventaire_detail(request, pk):
    ent = _entreprise(request)
    session = get_object_or_404(InventaireSession, pk=pk, entrepot__entreprise=ent)
    lignes = session.lignes.select_related('produit', 'emplacement').order_by('produit__nom')
    if request.method == 'POST':
        return inventaire_sauvegarder(request, pk)
    total_lignes = len(lignes)
    lignes_comptees = sum(1 for l in lignes if l.quantite_comptee is not None)
    return render(request, 'magasinier/inventaire_detail.html', {
        'session': session,
        'lignes': lignes,
        'total_lignes': total_lignes,
        'lignes_comptees': lignes_comptees,
        'progression': round(lignes_comptees * 100 / total_lignes) if total_lignes else 0,
    })


def _sauvegarder_comptage(session, post):
    """Enregistre les quantités comptées envoyées sous la forme `qte_<pk ligne>`. Retourne le nombre de lignes mises à jour."""
    nb = 0
    for ligne in session.lignes.all():
        val = (post.get(f'qte_{ligne.pk}') or '').strip()
        if not val:
            continue
        try:
            qte = Decimal(val)
        except InvalidOperation:
            continue
        if qte < 0:
            continue
        ligne.quantite_comptee = qte
        ligne.save(update_fields=['quantite_comptee', 'updated_at'])
        nb += 1
    return nb


@login_required
@role_required('magasinier', 'gestionnaire', 'admin_ent', 'super_admin')
@require_POST
def inventaire_sauvegarder(request, pk):
    """Sauvegarde du comptage terrain. La validation (ajustements de stock) reste réservée au gestionnaire."""
    ent = _entreprise(request)
    session = get_object_or_404(InventaireSession, pk=pk, entrepot__entreprise=ent)
    if session.statut != 'en_cours':
        messages.error(request, "Cette session d'inventaire est clôturée : le comptage ne peut plus être modifié.")
        return redirect('magasinier:inventaire_detail', pk=pk)
    nb = _sauvegarder_comptage(session, request.POST)
    if request.POST.get('action') == 'suspendre':
        messages.info(request, f"Comptage suspendu ({nb} ligne(s) enregistrée(s)). Vous pourrez le reprendre plus tard.")
        return redirect('magasinier:inventaire_list')
    messages.success(request, f"Comptage sauvegardé ({nb} ligne(s) enregistrée(s)).")
    return redirect('magasinier:inventaire_detail', pk=pk)


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
    produits_rupture, produits_seuil = [], []
    for p in _produits_en_alerte(ent):
        if p.total <= 0:
            produits_rupture.append(p)
        else:
            p.pct_stock = round(p.total * 100 / p.seuil_alerte) if p.seuil_alerte else 0
            produits_seuil.append(p)
    return render(request, 'magasinier/alertes.html', {
        'produits_rupture': produits_rupture, 'produits_seuil': produits_seuil,
        'nb_rupture': len(produits_rupture), 'nb_seuil': len(produits_seuil),
    })


@login_required
@role_required('magasinier', 'admin_ent', 'super_admin')
def parametres(request):
    if request.method == 'POST':
        entrepot_defaut = request.POST.get('entrepot_defaut')
        if entrepot_defaut and Entrepot.objects.filter(pk=entrepot_defaut, entreprise=_entreprise(request)).exists():
            request.session['magasinier_entrepot_defaut'] = entrepot_defaut
        else:
            request.session.pop('magasinier_entrepot_defaut', None)
        if request.POST.get('type_defaut') in ('entree', 'sortie'):
            request.session['magasinier_type_defaut'] = request.POST['type_defaut']
        messages.success(request, "Préférences enregistrées.")
        return redirect('magasinier:parametres')
    return render(request, 'magasinier/parametres.html', {
        'entrepots': Entrepot.objects.filter(entreprise=_entreprise(request), est_actif=True),
        'prefs': _prefs(request),
    })


@login_required
@role_required('magasinier', 'admin_ent', 'gestionnaire', 'super_admin')
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
        'prix_vente': float(p.prix_vente) if p.prix_vente is not None else None,
    } for p in produits]
    return JsonResponse(data, safe=False)