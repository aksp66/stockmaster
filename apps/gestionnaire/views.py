# apps/gestionnaire/views.py
# ──────────────────────────────────────────────────────────────────────────────
# Toutes les vues du gestionnaire de stock
# ──────────────────────────────────────────────────────────────────────────────
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST, require_GET
import json, csv
from datetime import timedelta
from decimal import Decimal

from apps.accounts.decorators import role_required
from apps.stock.models import (
    Produit, Categorie, Entrepot, Emplacement, Stock,
    Mouvement, TypeMouvement, InventaireSession, LigneInventaire,
    Alerte, TypeAlerte, PrioriteAlerte, ScanLog, Fournisseur
)
from apps.core.models import AuditLog, TypeAction
import uuid

def get_entreprise(request):
    return request.user.entreprise


# ── DASHBOARD ──────────────────────────────────────────────────────────────────
@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def dashboard(request):
    ent = get_entreprise(request)
    produits = Produit.objects.filter(entreprise=ent, est_actif=True)
    alertes  = Alerte.objects.filter(produit__entreprise=ent, lue=False)

    # Valeur totale du stock
    stocks = Stock.objects.filter(entrepot__entreprise=ent)
    valeur_stock = sum(
        float(s.quantite) * float(s.produit.prix_unitaire)
        for s in stocks.select_related('produit')
    )

    # Mouvements des 30 derniers jours
    depuis = timezone.now() - timedelta(days=30)
    mouvements_recent = Mouvement.objects.filter(
        produit__entreprise=ent,
        date_mouvement__gte=depuis
    ).order_by('-date_mouvement')[:8]

    # Produits sous seuil d'alerte
    produits_alerte = [p for p in produits if p.est_en_alerte()]

    context = {
        'total_produits':    produits.count(),
        'total_entrepots':   Entrepot.objects.filter(entreprise=ent, est_actif=True).count(),
        'nb_alertes':        alertes.count(),
        'nb_inventaires':    InventaireSession.objects.filter(entrepot__entreprise=ent, statut='en_cours').count(),
        'valeur_stock':      valeur_stock,
        'mouvements_recent': mouvements_recent,
        'produits_alerte':   produits_alerte[:5],
        'today':             timezone.now(),          # ← AJOUTÉ
    }
    return render(request, 'gestionnaire/dashboard.html', context)

# ── PRODUITS ───────────────────────────────────────────────────────────────────
@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def produits_liste(request):
    ent  = get_entreprise(request)
    qs   = Produit.objects.filter(entreprise=ent).select_related('categorie', 'fournisseur_principal')

    q       = request.GET.get('q', '')
    cat_id  = request.GET.get('categorie', '')
    statut  = request.GET.get('statut', '')
    alerte  = request.GET.get('alerte', '')

    if q:       qs = qs.filter(Q(nom__icontains=q) | Q(sku__icontains=q) | Q(code_barres__icontains=q))
    if cat_id:  qs = qs.filter(categorie_id=cat_id)
    if statut == 'actif':   qs = qs.filter(est_actif=True)
    if statut == 'inactif': qs = qs.filter(est_actif=False)

    page = Paginator(qs.order_by('nom'), 20)
    produits = page.get_page(request.GET.get('page', 1))

    context = {
        'produits':    produits,
        'categories':  Categorie.objects.filter(entreprise=ent),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
        'q': q, 'cat_id': cat_id, 'statut': statut,
    }
    return render(request, 'gestionnaire/produit_list.html', context)


@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def produit_form(request, pk=None):
    ent = get_entreprise(request)
    produit = get_object_or_404(Produit, pk=pk, entreprise=ent) if pk else None

    # Données pour les sélecteurs
    categories = Categorie.objects.filter(entreprise=ent)
    fournisseurs = Fournisseur.objects.filter(entreprise=ent, est_actif=True)
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True)
    unites = Produit._meta.get_field('unite_mesure').choices if hasattr(Produit, '_meta') else []

    if request.method == 'POST':
        data = request.POST
        if produit:
            # Modification
            produit.nom = data.get('nom')
            # SKU non modifiable (readonly)
            produit.code_barre = data.get('code_barre', '')
            produit.unite_mesure = data.get('unite', 'unite')
            produit.seuil_alerte = Decimal(data.get('seuil_alerte', 0))
            produit.prix_unitaire = Decimal(data.get('prix_unitaire', 0))
            prix_vente = data.get('prix_vente')
            produit.prix_vente = Decimal(prix_vente) if prix_vente else None
            produit.description = data.get('description', '')
            cat_id = data.get('categorie')
            produit.categorie = categories.filter(pk=cat_id).first() if cat_id else None
            fourn_id = data.get('fournisseur')
            produit.fournisseur_principal = fournisseurs.filter(pk=fourn_id).first() if fourn_id else None
            # champs supplémentaires
            produit.delai_reappro = int(data.get('delai_reappro', 7))
            produit.qte_min_commande = int(data.get('qte_min_commande', 1))
            produit.est_actif = data.get('est_actif') == 'on'
            produit.save()
            messages.success(request, f"Produit « {produit.nom} » mis à jour.")
        else:
            # Création
            sku = data.get('sku')
            if Produit.objects.filter(sku=sku, entreprise=ent).exists():
                messages.error(request, "Ce SKU existe déjà.")
                return redirect('gestionnaire:produit_ajouter')
            produit = Produit.objects.create(
                entreprise=ent,
                nom=data.get('nom'),
                sku=sku,
                code_barre=data.get('code_barre', ''),
                unite_mesure=data.get('unite', 'unite'),
                seuil_alerte=Decimal(data.get('seuil_alerte', 0)),
                prix_unitaire=Decimal(data.get('prix_unitaire', 0)),
                prix_vente=Decimal(data.get('prix_vente', 0)) if data.get('prix_vente') else None,
                description=data.get('description', ''),
                categorie=categories.filter(pk=data.get('categorie')).first(),
                fournisseur_principal=fournisseurs.filter(pk=data.get('fournisseur')).first(),
                delai_reappro=int(data.get('delai_reappro', 7)),
                qte_min_commande=int(data.get('qte_min_commande', 1)),
                est_actif=True,
            )
            # Stock initial
            stock_initial = Decimal(data.get('stock_initial', 0))
            entrepot_id = data.get('entrepot_initial')
            if stock_initial > 0 and entrepot_id:
                entrepot = Entrepot.objects.filter(pk=entrepot_id, entreprise=ent).first()
                if entrepot:
                    Mouvement.objects.create(
                        type_mouvement=TypeMouvement.ENTREE,
                        produit=produit,
                        quantite=stock_initial,
                        entrepot_destination=entrepot,
                        utilisateur=request.user,
                        reference=f"INIT-{produit.sku}",
                        note="Stock initial lors de la création du produit",
                        prix_unitaire_snapshot=produit.prix_unitaire,
                    )
                    # Mise à jour du stock dans la table Stock
                    stock_obj, _ = Stock.objects.get_or_create(
                        produit=produit,
                        entrepot=entrepot,
                        defaults={'quantite': Decimal('0')}
                    )
                    stock_obj.quantite += stock_initial
                    stock_obj.save()
            messages.success(request, f"Produit « {produit.nom} » créé.")
        return redirect('gestionnaire:produits')

    # Calculs pour le panneau latéral (état du stock)
    stocks_par_entrepot = []
    valeur_stock = 0
    if produit:
        stocks = produit.stocks.select_related('emplacement__entrepot')
        for s in stocks:
            stocks_par_entrepot.append({
                'emplacement__entrepot__nom': s.emplacement.entrepot.nom if s.emplacement else s.entrepot.nom,
                'total': float(s.quantite)
            })
            valeur_stock += float(s.quantite) * float(produit.prix_unitaire)

    context = {
        'produit': produit,
        'categories': categories,
        'fournisseurs': fournisseurs,
        'entrepots': entrepots,
        'unites': unites,
        'stocks_par_entrepot': stocks_par_entrepot,
        'valeur_stock': valeur_stock,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'gestionnaire/produit_form.html', context)

@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def produit_detail(request, pk):
    ent = get_entreprise(request)
    produit = get_object_or_404(Produit, pk=pk, entreprise=ent)
    mouvements = produit.mouvements.order_by('-date_mouvement')[:20]
    stocks     = produit.stocks.select_related('entrepot', 'emplacement')
    alertes    = produit.alertes.filter(lue=False)[:5]
    predictions = produit.predictions.order_by('date_cible')[:6]
    return render(request, 'gestionnaire/produit_detail.html', {
        'produit': produit, 'mouvements': mouvements,
        'stocks': stocks, 'alertes': alertes, 'predictions': predictions,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    })


@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def produit_import(request):
    """Import CSV de produits."""
    ent = get_entreprise(request)
    if request.method == 'POST' and request.FILES.get('fichier'):
        fichier = request.FILES['fichier']
        import io
        decoded = fichier.read().decode('utf-8-sig')
        reader  = csv.DictReader(io.StringIO(decoded))
        crees, erreurs = 0, []
        for i, row in enumerate(reader, 1):
            try:
                Produit.objects.get_or_create(
                    sku=row.get('sku', '').strip(),
                    entreprise=ent,
                    defaults={
                        'nom':          row.get('nom', '').strip(),
                        'code_barres':  row.get('code_barres', '').strip(),
                        'prix_unitaire': float(row.get('prix_unitaire', 0) or 0),
                        'seuil_alerte':  float(row.get('seuil_alerte', 0) or 0),
                        'unite_mesure':  row.get('unite_mesure', 'unite').strip(),
                    }
                )
                crees += 1
            except Exception as e:
                erreurs.append(f"Ligne {i} : {e}")
        messages.success(request, f"{crees} produit(s) importé(s).")
        if erreurs:
            messages.warning(request, f"{len(erreurs)} erreur(s) : " + " | ".join(erreurs[:3]))
        return redirect('gestionnaire:produits')
    return render(request, 'gestionnaire/produit_import.html', {
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count()
    })


# ── MOUVEMENTS ─────────────────────────────────────────────────────────────────
@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def mouvements_liste(request):
    ent = get_entreprise(request)
    qs  = Mouvement.objects.filter(
        Q(entrepot_source__entreprise=ent) | Q(entrepot_destination__entreprise=ent) |
        Q(produit__entreprise=ent)
    ).select_related('produit','entrepot_source','entrepot_destination','utilisateur').distinct()

    q    = request.GET.get('q', '')
    type_m = request.GET.get('type', '')
    date_d = request.GET.get('date_debut', '')
    date_f = request.GET.get('date_fin', '')

    if q:     qs = qs.filter(Q(produit__nom__icontains=q) | Q(reference__icontains=q))
    if type_m: qs = qs.filter(type_mouvement=type_m)
    if date_d: qs = qs.filter(date_mouvement__date__gte=date_d)
    if date_f: qs = qs.filter(date_mouvement__date__lte=date_f)

    page = Paginator(qs.order_by('-date_mouvement'), 25)
    mouvements = page.get_page(request.GET.get('page', 1))
    return render(request, 'gestionnaire/mouvement_list.html', {
        'mouvements': mouvements,
        'types': TypeMouvement.choices,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
        'q': q, 'type_m': type_m,
    })


@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin', 'magasinier')
def mouvement_form(request):
    ent = get_entreprise(request)
    if request.method == 'POST':
        data      = request.POST
        produit   = get_object_or_404(Produit, pk=data.get('produit'), entreprise=ent)
        type_m    = data.get('type_mouvement')
        quantite  = float(data.get('quantite', 0))
        ent_src   = Entrepot.objects.filter(pk=data.get('entrepot_source'), entreprise=ent).first()
        ent_dst   = Entrepot.objects.filter(pk=data.get('entrepot_destination'), entreprise=ent).first()
        empl_src  = Emplacement.objects.filter(pk=data.get('emplacement_source')).first()
        empl_dst  = Emplacement.objects.filter(pk=data.get('emplacement_destination')).first()

        mouv = Mouvement.objects.create(
            type_mouvement=type_m,
            produit=produit,
            quantite=quantite,
            entrepot_source=ent_src,
            entrepot_destination=ent_dst,
            emplacement_source=empl_src,
            emplacement_destination=empl_dst,
            utilisateur=request.user,
            reference=data.get('reference', ''),
            note=data.get('note', ''),
            lot_numero=data.get('lot_numero', ''),
        )

        # Mise à jour du stock
        _appliquer_mouvement(mouv)
        # Vérification des seuils
        _verifier_seuil(produit, ent_dst or ent_src)

        AuditLog.log(request, TypeAction.MOUVEMENT_STOCK,
                     f"{mouv.get_type_mouvement_display()} : {produit.nom} × {quantite}", objet=mouv)
        messages.success(request, "Mouvement enregistré avec succès.")
        return redirect('gestionnaire:mouvements')

    context = {
        'produits':  Produit.objects.filter(entreprise=ent, est_actif=True),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'types':     TypeMouvement.choices,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'gestionnaire/mouvement_form.html', context)


def _appliquer_mouvement(mouv):
    """Met à jour la table Stock selon le type de mouvement."""
    def maj_stock(produit, entrepot, emplacement, delta):
        if not entrepot:
            return
        stock, _ = Stock.objects.get_or_create(
            produit=produit, entrepot=entrepot, emplacement=emplacement,
            defaults={'quantite': 0}
        )
        stock.quantite = max(0, float(stock.quantite) + delta)
        stock.save(update_fields=['quantite', 'updated_at'])

    p, q = mouv.produit, float(mouv.quantite)
    if mouv.type_mouvement == TypeMouvement.ENTREE:
        maj_stock(p, mouv.entrepot_destination, mouv.emplacement_destination, +q)
    elif mouv.type_mouvement in [TypeMouvement.SORTIE, TypeMouvement.PERTE]:
        maj_stock(p, mouv.entrepot_source, mouv.emplacement_source, -q)
    elif mouv.type_mouvement == TypeMouvement.TRANSFERT:
        maj_stock(p, mouv.entrepot_source,      mouv.emplacement_source,      -q)
        maj_stock(p, mouv.entrepot_destination, mouv.emplacement_destination, +q)
    elif mouv.type_mouvement == TypeMouvement.AJUSTEMENT:
        maj_stock(p, mouv.entrepot_destination or mouv.entrepot_source,
                  mouv.emplacement_destination or mouv.emplacement_source, q)


def _verifier_seuil(produit, entrepot):
    """Crée une alerte si le stock tombe sous le seuil."""
    if not entrepot:
        return
    total = produit.quantite_totale()
    if total <= produit.seuil_alerte:
        type_a = TypeAlerte.RUPTURE if total == 0 else TypeAlerte.SEUIL_BAS
        prio   = PrioriteAlerte.CRITIQUE if total == 0 else PrioriteAlerte.HAUTE
        Alerte.objects.get_or_create(
            produit=produit, entrepot=entrepot, type_alerte=type_a, lue=False,
            defaults={
                'priorite': prio,
                'message': f"Stock de « {produit.nom} » : {total} {produit.unite_mesure} (seuil : {produit.seuil_alerte})"
            }
        )


# ── SCAN CODE-BARRES ───────────────────────────────────────────────────────────
@login_required
@role_required('gestionnaire', 'admin_ent', 'magasinier', 'super_admin')
def scan_view(request):
    ent = get_entreprise(request)
    return render(request, 'gestionnaire/scan.html', {
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    })


@login_required
@require_POST
def api_scan(request):
    """API AJAX pour la résolution d'un code-barres."""
    ent  = request.user.entreprise
    data = json.loads(request.body)
    code = data.get('code', '').strip()
    produit = Produit.objects.filter(
        Q(code_barres=code) | Q(sku=code), entreprise=ent
    ).first()

    ScanLog.objects.create(
        utilisateur=request.user,
        produit=produit,
        code_barre_scanne=code,
        action_attendue=data.get('action', ''),
        succes=bool(produit),
        message_erreur='' if produit else f"Code-barres introuvable : {code}"
    )

    if produit:
        stocks = [{
            'entrepot': s.entrepot.nom,
            'entrepot_id': str(s.entrepot.id),
            'quantite': float(s.quantite),
        } for s in produit.stocks.select_related('entrepot')]
        return JsonResponse({
            'found': True,
            'produit': {'id': str(produit.id), 'nom': produit.nom, 'sku': produit.sku,
                        'unite': produit.unite_mesure, 'prix': float(produit.prix_unitaire)},
            'stocks': stocks,
        })
    return JsonResponse({'found': False, 'message': f"Aucun produit pour le code « {code} »"})


# ── INVENTAIRES ────────────────────────────────────────────────────────────────
@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def inventaires_liste(request):
    ent = get_entreprise(request)
    sessions = InventaireSession.objects.filter(
        entrepot__entreprise=ent
    ).select_related('entrepot', 'utilisateur_demarrage').order_by('-date_debut')
    return render(request, 'gestionnaire/inventaire_session_list.html', {
        'sessions': sessions,
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    })


@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def inventaire_creer(request):
    ent = get_entreprise(request)
    if request.method == 'POST':
        entrepot = get_object_or_404(Entrepot, pk=request.POST.get('entrepot'), entreprise=ent)
        session  = InventaireSession.objects.create(
            entrepot=entrepot,
            utilisateur_demarrage=request.user,
        )
        # Pré-remplir les lignes avec le stock théorique actuel
        stocks = Stock.objects.filter(entrepot=entrepot).select_related('produit', 'emplacement')
        lignes = [
            LigneInventaire(
                session=session,
                produit=s.produit,
                emplacement=s.emplacement,
                quantite_theorique=s.quantite,
            ) for s in stocks
        ]
        LigneInventaire.objects.bulk_create(lignes)
        messages.success(request, f"Session d'inventaire créée pour {entrepot.nom}.")
        return redirect('gestionnaire:inventaire_session_detail', pk=session.pk)
    return render(request, 'gestionnaire/inventaire_session_create.html', {
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    })


@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin', 'magasinier')
def inventaire_saisie(request, pk):
    ent = get_entreprise(request)
    session = get_object_or_404(InventaireSession, pk=pk, entrepot__entreprise=ent)
    lignes = session.lignes.select_related('produit', 'emplacement').order_by('produit__nom')

    total_lignes = lignes.count()
    lignes_comptees = lignes.filter(quantite_comptee__isnull=False).count()
    nb_ecarts = 0
    for ligne in lignes:
        if ligne.quantite_comptee is not None and ligne.quantite_comptee != ligne.quantite_theorique:
            nb_ecarts += 1
    progression = round((lignes_comptees / total_lignes * 100) if total_lignes else 0)
    pret_validation = (lignes_comptees == total_lignes)

    if request.method == 'POST':
        for ligne in lignes:
            val = request.POST.get(f'ligne_{ligne.pk}')
            if val is not None and val.strip() != '':
                ligne.quantite_comptee = float(val)
                ligne.save(update_fields=['quantite_comptee'])
        messages.success(request, "Quantités enregistrées.")
        return redirect('gestionnaire:inventaire_saisie', pk=session.pk)

    context = {
        'session': session,
        'lignes': lignes,
        'total_lignes': total_lignes,
        'lignes_comptees': lignes_comptees,
        'nb_ecarts': nb_ecarts,
        'progression': progression,
        'pret_validation': pret_validation,
        'ajustement_auto': True,
        'masquer_stock': False,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'gestionnaire/inventaire_session_detail.html', context)

@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def inventaire_valider(request, pk):
    ent = get_entreprise(request)
    session = get_object_or_404(InventaireSession, pk=pk, entrepot__entreprise=ent, statut='en_cours')
    if request.method == 'POST':
        session.statut = 'valide'
        session.date_fin = timezone.now()
        session.utilisateur_validation = request.user
        session.save()
        # Appliquer les écarts
        for ligne in session.lignes.filter(quantite_comptee__isnull=False):
            ecart = ligne.ecart()  # utilise la méthode du modèle
            if ecart != 0:
                mouv = Mouvement.objects.create(
                    type_mouvement=TypeMouvement.AJUSTEMENT,
                    produit=ligne.produit,
                    quantite=abs(ecart),
                    entrepot_destination=session.entrepot if ecart > 0 else None,
                    entrepot_source=session.entrepot if ecart < 0 else None,
                    emplacement_destination=ligne.emplacement if ecart > 0 else None,
                    emplacement_source=ligne.emplacement if ecart < 0 else None,
                    utilisateur=request.user,
                    reference=f"INVENTAIRE-{session.pk}",
                    note="Ajustement inventaire automatique",
                )
                _appliquer_mouvement(mouv)
        AuditLog.log(request, TypeAction.VALIDATION_INVENTAIRE,
                     f"Inventaire validé : {session.entrepot.nom}", objet=session)
        messages.success(request, "Inventaire validé. Les ajustements ont été appliqués.")
        return redirect('gestionnaire:inventaires')
    # Si accès GET, rediriger vers la page de saisie
    return redirect('gestionnaire:inventaire_saisie', pk=pk)

@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def inventaire_session_annuler(request, pk):
    ent = get_entreprise(request)
    session = get_object_or_404(InventaireSession, pk=pk, entrepot__entreprise=ent, statut='en_cours')
    if request.method == 'POST':
        session.statut = 'annule'
        session.date_fin = timezone.now()
        session.save()
        messages.success(request, f"Session d'inventaire {session.pk} annulée.")
    return redirect('gestionnaire:inventaires')


# ── ALERTES ────────────────────────────────────────────────────────────────────
@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def alertes_liste(request):
    from decimal import Decimal
    ent = get_entreprise(request)
    statut = request.GET.get('statut', 'actives')
    
    alertes_actives = Alerte.objects.filter(
        produit__entreprise=ent, lue=False
    ).select_related('produit', 'entrepot').order_by('-created_at')
    
    alertes_acquittees = Alerte.objects.filter(
        produit__entreprise=ent, lue=True
    ).select_related('produit', 'acquitte_par').order_by('-date_lecture')[:100]
    
    produits_rupture = []
    produits_seuil = []
    
    for alerte in alertes_actives:
        produit = alerte.produit
        qte = produit.quantite_totale()
        if qte is None:
            qte = Decimal('0')
        # seuil_alerte est un DecimalField, donc on le récupère directement
        seuil = produit.seuil_alerte or Decimal('0')
        
        if qte == 0:
            produits_rupture.append({
                'id': produit.id,
                'nom': produit.nom,
                'sku': produit.sku,
                'categorie': produit.categorie,
                'entrepot_principal': alerte.entrepot,
                'seuil_alerte': float(seuil),  # pour l'affichage on peut convertir
                'derniere_sortie': (produit.mouvements.filter(type_mouvement__in=['sortie','perte'])
                                     .first().date_mouvement if produit.mouvements.filter(type_mouvement__in=['sortie','perte']).exists() else None),
                'alerte_id': alerte.id,
            })
        elif seuil > 0 and qte <= seuil:
            # Ici qte et seuil sont des Decimal, donc la soustraction est valide
            manquant = max(Decimal('0'), seuil - qte)
            manquant_float = float(manquant)
            # Pour le pourcentage, on convertit d'abord en float
            pct_stock = float(qte) / float(seuil) * 100 if seuil > 0 else 0
            produits_seuil.append({
                'id': produit.id,
                'nom': produit.nom,
                'sku': produit.sku,
                'categorie': produit.categorie,
                'quantite_totale': float(qte),
                'seuil_alerte': float(seuil),
                'manquant': manquant_float,
                'pct_stock': pct_stock,
                'alerte_id': alerte.id,
            })
        else:
            # Cas anormal : alerte pour autre raison (ex: expiration)
            # On l'ajoute quand même dans les ruptures pour ne pas la perdre
            produits_rupture.append({
                'id': produit.id,
                'nom': produit.nom,
                'sku': produit.sku,
                'categorie': produit.categorie,
                'entrepot_principal': alerte.entrepot,
                'seuil_alerte': float(seuil),
                'derniere_sortie': None,
                'alerte_id': alerte.id,
            })
    
    nb_rupture = len(produits_rupture)
    nb_seuil = len(produits_seuil)
    nb_acquittees = alertes_acquittees.count()
    
    context = {
        'alertes_actives': alertes_actives,
        'alertes_acquittees': alertes_acquittees,
        'nb_rupture': nb_rupture,
        'nb_seuil': nb_seuil,
        'nb_acquittees': nb_acquittees,
        'produits_rupture': produits_rupture,
        'produits_seuil': produits_seuil,
    }
    return render(request, 'gestionnaire/alertes.html', context)

@login_required
@require_POST
def alerte_acquitter(request, pk):
    ent   = request.user.entreprise
    alerte = get_object_or_404(Alerte, pk=pk, produit__entreprise=ent)
    alerte.acquitter(request.user)
    messages.success(request, "Alerte acquittée.")
    return redirect('gestionnaire:alertes')


# ── TRANSFERT ──────────────────────────────────────────────────────────────────
@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin', 'magasinier')
def transfert_view(request):
    ent = get_entreprise(request)
    if request.method == 'POST':
        data    = request.POST
        produit = get_object_or_404(Produit, pk=data.get('produit'), entreprise=ent)
        src     = get_object_or_404(Entrepot, pk=data.get('entrepot_source'), entreprise=ent)
        dst     = get_object_or_404(Entrepot, pk=data.get('entrepot_destination'), entreprise=ent)
        quantite = float(data.get('quantite', 0))

        # Vérifier stock disponible
        stock_dispo = Stock.objects.filter(produit=produit, entrepot=src).first()
        if not stock_dispo or float(stock_dispo.quantite) < quantite:
            messages.error(request, "Stock insuffisant dans l'entrepôt source.")
            return redirect('gestionnaire:transfert')

        mouv = Mouvement.objects.create(
            type_mouvement=TypeMouvement.TRANSFERT,
            produit=produit, quantite=quantite,
            entrepot_source=src, entrepot_destination=dst,
            utilisateur=request.user, note=data.get('note', ''),
        )
        _appliquer_mouvement(mouv)
        messages.success(request, f"Transfert de {quantite} {produit.unite_mesure} effectué.")
        return redirect('gestionnaire:mouvements')


    context = {
        'produits': Produit.objects.filter(entreprise=ent, est_actif=True),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return redirect('gestionnaire:mouvement_form')


# ── RAPPORTS ───────────────────────────────────────────────────────────────────

def export_stock_csv(entreprise):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="stock.csv"'
    response.write('\ufeff')  # BOM pour UTF-8
    writer = csv.writer(response)
    writer.writerow(['Produit', 'SKU', 'Entrepôt', 'Emplacement', 'Quantité', 'Unité', 'Valeur (FCFA)'])
    stocks = Stock.objects.filter(entrepot__entreprise=entreprise).select_related('produit', 'entrepot', 'emplacement')
    for s in stocks:
        valeur = float(s.quantite) * float(s.produit.prix_unitaire)
        writer.writerow([
            s.produit.nom, s.produit.sku, s.entrepot.nom,
            s.emplacement.code if s.emplacement else '',
            s.quantite, s.produit.unite_mesure, round(valeur, 2)
        ])
    return response

def export_alertes_csv(entreprise):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="alertes.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Date', 'Produit', 'Type', 'Message', 'Priorité'])
    alertes = Alerte.objects.filter(produit__entreprise=entreprise, lue=False).select_related('produit')
    for a in alertes:
        writer.writerow([
            a.created_at.strftime('%d/%m/%Y %H:%M'),
            a.produit.nom,
            a.get_type_alerte_display(),
            a.message,
            a.get_priorite_display()
        ])
    return response

def export_valorisation_csv(entreprise):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="valorisation.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Produit', 'SKU', 'Quantité totale', 'Prix unitaire moyen (FCFA)', 'Valeur totale (FCFA)'])
    produits = Produit.objects.filter(entreprise=entreprise, est_actif=True)
    for p in produits:
        qte = p.quantite_totale()
        if qte > 0:
            prix_moyen = float(p.prix_unitaire)  # À améliorer avec CUMP réel
            valeur = qte * prix_moyen
            writer.writerow([p.nom, p.sku, qte, round(prix_moyen, 2), round(valeur, 2)])
    return response

@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def rapports_view(request):
    ent = get_entreprise(request)
    # Stock
    stocks = Stock.objects.filter(entrepot__entreprise=ent).select_related('produit', 'entrepot', 'emplacement')
    stock_rapport = []
    valeur_totale_stock = 0
    for s in stocks:
        valeur = float(s.quantite) * float(s.produit.prix_unitaire)
        valeur_totale_stock += valeur
        stock_rapport.append({
            'produit': s.produit,
            'entrepot': s.entrepot,
            'emplacement': s.emplacement,
            'quantite': s.quantite,
            'valeur': valeur,
        })
    # Mouvements
    mouvements_rapport = Mouvement.objects.filter(produit__entreprise=ent).select_related('produit', 'entrepot_source', 'entrepot_destination', 'utilisateur').order_by('-date_mouvement')[:500]
    # Alertes
    alertes_rapport = Alerte.objects.filter(produit__entreprise=ent, lue=False).select_related('produit').order_by('-created_at')[:100]
    # Valorisation (CUMP simplifié)
    produits = Produit.objects.filter(entreprise=ent, est_actif=True)
    valorisation_rapport = []
    valeur_totale_valorisation = 0
    for p in produits:
        qte = p.quantite_totale()
        if qte > 0:
            prix_moyen = p.prix_unitaire  # à améliorer avec CUMP réel
            valeur = qte * prix_moyen
            valeur_totale_valorisation += valeur
            valorisation_rapport.append({
                'nom': p.nom,
                'sku': p.sku,
                'unite_mesure': p.unite_mesure,
                'quantite_totale': qte,
                'prix_moyen': prix_moyen,
                'valeur_totale': valeur,
            })
    context = {
        'stock_rapport': stock_rapport,
        'valeur_totale_stock': valeur_totale_stock,
        'mouvements_rapport': mouvements_rapport,
        'alertes_rapport': alertes_rapport,
        'valorisation_rapport': valorisation_rapport,
        'valeur_totale_valorisation': valeur_totale_valorisation,
        'nb_alertes_actives': alertes_rapport.count(),
    }
    if request.GET.get('export') == 'stock':
        return export_stock_csv(ent)
    elif request.GET.get('export') == 'alertes':
        return export_alertes_csv(ent)
    elif request.GET.get('export') == 'valorisation':
        return export_valorisation_csv(ent)
    return render(request, 'gestionnaire/rapports.html', context)


def _export_mouvements_csv(ent):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="mouvements.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Date','Type','Produit','SKU','Quantité','Source','Destination','Référence','Utilisateur'])
    mouvs = Mouvement.objects.filter(produit__entreprise=ent).select_related(
        'produit','entrepot_source','entrepot_destination','utilisateur').order_by('-date_mouvement')
    for m in mouvs:
        writer.writerow([
            m.date_mouvement.strftime('%d/%m/%Y %H:%M'),
            m.get_type_mouvement_display(),
            m.produit.nom, m.produit.sku, m.quantite,
            m.entrepot_source.nom if m.entrepot_source else '',
            m.entrepot_destination.nom if m.entrepot_destination else '',
            m.reference,
            m.utilisateur.get_full_name() if m.utilisateur else '',
        ])
    return response


def _export_stock_csv(ent):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="stock.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Produit','SKU','Entrepôt','Emplacement','Quantité','Unité','Valeur HT'])
    for s in Stock.objects.filter(entrepot__entreprise=ent).select_related('produit','entrepot','emplacement'):
        writer.writerow([
            s.produit.nom, s.produit.sku, s.entrepot.nom,
            s.emplacement.code if s.emplacement else '',
            s.quantite, s.produit.unite_mesure,
            round(float(s.quantite) * float(s.produit.prix_unitaire), 2),
        ])
    return response


# ── EMPLACEMENTS ───────────────────────────────────────────────────────────────
@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def emplacements_view(request):
    ent = get_entreprise(request)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'creer':
            entrepot_id = request.POST.get('entrepot')
            code = request.POST.get('code', '').strip()
            description = request.POST.get('description', '').strip()

            if not code:
                messages.error(request, "Le code de l'emplacement est obligatoire.")
            elif not entrepot_id:
                messages.error(request, "Veuillez sélectionner un entrepôt.")
            else:
                # Récupération sécurisée de l'entrepôt
                entrepot = get_object_or_404(Entrepot, pk=entrepot_id, entreprise=ent)
                # Vérifier si un emplacement avec le même code existe déjà
                if Emplacement.objects.filter(entrepot=entrepot, code=code).exists():
                    messages.error(request, f"Un emplacement avec le code '{code}' existe déjà dans cet entrepôt.")
                else:
                    Emplacement.objects.create(
                        entrepot=entrepot,
                        code=code,
                        description=description
                    )
                    messages.success(request, f"Emplacement '{code}' créé avec succès.")
            return redirect('gestionnaire:emplacements')

        elif action == 'supprimer':
            emplacement_id = request.POST.get('emplacement_id')
            if emplacement_id:
                empl = get_object_or_404(Emplacement, pk=emplacement_id, entrepot__entreprise=ent)
                empl.delete()
                messages.success(request, "Emplacement supprimé.")
            return redirect('gestionnaire:emplacements')

    # GET : affichage
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True).prefetch_related('emplacements')
    return render(request, 'gestionnaire/emplacements.html', {
        'entrepots': entrepots,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    })

@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def produit_delete(request, pk):
    """Suppression douce (soft delete) d’un produit."""
    ent = request.user.entreprise
    produit = get_object_or_404(Produit, pk=pk, entreprise=ent)
    if request.method == 'POST':
        produit.est_actif = False
        produit.save()
        messages.success(request, f"Produit « {produit.nom} » désactivé.")
        return redirect('gestionnaire:produits')
    return redirect('gestionnaire:produits')

@login_required
@role_required('gestionnaire', 'admin_ent', 'magasinier', 'super_admin')
@require_GET
def produit_search_ajax(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    ent = request.user.entreprise
    produits = Produit.objects.filter(entreprise=ent, est_actif=True, nom__icontains=q)[:10]
    data = [{
        'id': str(p.id),
        'nom': p.nom,
        'sku': p.sku,
        'unite': p.unite_mesure,
        'stock_total': float(p.quantite_totale()),
        'prix': float(p.prix_unitaire),
    } for p in produits]
    return JsonResponse(data, safe=False)

@login_required
@require_POST
def alertes_acquitter_toutes(request):
    ent = request.user.entreprise
    alertes = Alerte.objects.filter(produit__entreprise=ent, lue=False)
    count = alertes.count()
    for alerte in alertes:
        alerte.acquitter(request.user)
    messages.success(request, f"{count} alerte(s) acquittée(s).")
    return redirect('gestionnaire:alertes')

@login_required
@role_required('gestionnaire', 'admin_ent', 'magasinier', 'super_admin')
def mouvement_form(request):
    ent = get_entreprise(request)

    # Récupération du produit depuis GET (pré-remplissage)
    produit_id_get = request.GET.get('produit', '').strip()
    produit_initial = None
    if produit_id_get:
        try:
            produit_initial = Produit.objects.get(pk=produit_id_get, entreprise=ent)
        except (ValueError, uuid.UUID, Produit.DoesNotExist):
            produit_initial = None

    # Construction des types de mouvement avec icônes et couleurs
    types_mouvement = []
    for val, label in TypeMouvement.choices:
        if val == 'entree':
            icon = 'fa-truck'
            color = 'green'      # correspond à var(--green-dim) et var(--green)
        elif val == 'sortie':
            icon = 'fa-arrow-right'
            color = 'red'
        elif val == 'transfert':
            icon = 'fa-right-left'   # icône valide FA6
            color = 'blue'
        elif val == 'ajustement':
            icon = 'fa-pen'
            color = 'orange'
        else:
            icon = 'fa-circle-info'
            color = 'gray'
        types_mouvement.append((val, label, icon, color))

    if request.method == 'POST':
        data = request.POST
        # Nettoyage et validation du produit
        prod_id = data.get('produit', '').strip()
        if not prod_id:
            messages.error(request, "Veuillez sélectionner un produit.")
            return redirect('gestionnaire:mouvement_form')
        try:
            produit = Produit.objects.get(pk=prod_id, entreprise=ent)
        except (ValueError, uuid.UUID, Produit.DoesNotExist):
            messages.error(request, "Produit invalide.")
            return redirect('gestionnaire:mouvement_form')
        
        type_m = data.get('type_mouvement')
        try:
            quantite = float(data.get('quantite', 0))
        except ValueError:
            messages.error(request, "Quantité invalide.")
            return redirect('gestionnaire:mouvement_form')
        
        # Gestion des entrepôts selon le type
        ent_src = None
        ent_dst = None
        if type_m == 'transfert':
            ent_src = Entrepot.objects.filter(pk=data.get('entrepot'), entreprise=ent).first()
            ent_dst = Entrepot.objects.filter(pk=data.get('entrepot_destination'), entreprise=ent).first()
        elif type_m in ('sortie', 'ajustement', 'perte'):
            ent_src = Entrepot.objects.filter(pk=data.get('entrepot'), entreprise=ent).first()
        elif type_m == 'entree':
            ent_dst = Entrepot.objects.filter(pk=data.get('entrepot'), entreprise=ent).first()
        
        mouv = Mouvement.objects.create(
            type_mouvement=type_m,
            produit=produit,
            quantite=quantite,
            entrepot_source=ent_src,
            entrepot_destination=ent_dst,
            utilisateur=request.user,
            reference=data.get('reference_document', ''),
            note=data.get('motif', ''),
        )
        _appliquer_mouvement(mouv)
        _verifier_seuil(produit, ent_dst or ent_src)
        messages.success(request, "Mouvement enregistré avec succès.")
        return redirect('gestionnaire:mouvements')

    # GET : affichage du formulaire
    context = {
        'types_mouvement': types_mouvement,
        'produits': Produit.objects.filter(entreprise=ent, est_actif=True),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
        'produit_initial': produit_initial,
        'now': timezone.now(),
    }
    return render(request, 'gestionnaire/mouvement_form.html', context)

@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def categories_list(request):
    ent = get_entreprise(request)
    categories = Categorie.objects.filter(entreprise=ent).select_related('parent').order_by('nom')

    def build_tree(parent=None, level=0):
        nodes = []
        for cat in categories.filter(parent=parent):
            nodes.append((cat, level))
            nodes.extend(build_tree(cat, level + 1))
        return nodes

    tree = build_tree()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'ajouter':
            nom = request.POST.get('nom', '').strip()
            parent_id = request.POST.get('parent') or None
            if nom:
                parent = Categorie.objects.filter(pk=parent_id, entreprise=ent).first() if parent_id else None
                Categorie.objects.create(nom=nom, parent=parent, entreprise=ent)
                messages.success(request, "Catégorie ajoutée.")
        elif action == 'modifier':
            cat_id = request.POST.get('categorie_id')
            nom = request.POST.get('nom', '').strip()
            parent_id = request.POST.get('parent') or None
            categorie = get_object_or_404(Categorie, pk=cat_id, entreprise=ent)
            if nom:
                categorie.nom = nom
                categorie.parent = Categorie.objects.filter(pk=parent_id, entreprise=ent).first() if parent_id else None
                categorie.save()
                messages.success(request, "Catégorie modifiée.")
        elif action == 'supprimer':
            cat_id = request.POST.get('categorie_id')
            categorie = get_object_or_404(Categorie, pk=cat_id, entreprise=ent)
            if categorie.sous_categories.exists() or categorie.produits.exists():
                messages.error(request, "Impossible de supprimer : cette catégorie contient des sous-catégories ou des produits.")
            else:
                categorie.delete()
                messages.success(request, "Catégorie supprimée.")
        return redirect('gestionnaire:categories')

    return render(request, 'gestionnaire/categories.html', {
        'tree': tree,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    })