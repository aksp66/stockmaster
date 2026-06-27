import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.db.models import (
    Count, F, Max, Q, Sum,
    ExpressionWrapper, DecimalField,
)

from apps.accounts.decorators import role_required
from apps.stock.models import Produit, Stock, Mouvement, Categorie, Entrepot
from apps.core.models import AuditLog
from apps.core.models import ExportLog  # centralisé

try:
    from responsable_achat.models import LigneCommande
    HAS_ACHATS = True
except ImportError:
    HAS_ACHATS = False

try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def _get_periode(request):
    """Extrait (debut, fin) depuis les paramètres GET, défaut : mois courant."""
    today = date.today()
    try:
        debut = date.fromisoformat(request.GET.get('date_debut', ''))
    except ValueError:
        debut = today.replace(day=1)
    try:
        fin = date.fromisoformat(request.GET.get('date_fin', ''))
    except ValueError:
        fin = today
    return debut, fin


def _stocks_dict(entreprise):
    """Retourne {produit_id: quantite_totale} pour toute l'entreprise."""
    return {
        s['produit']: s['total']
        for s in Stock.objects.filter(
            emplacement__entrepot__entreprise=entreprise
        ).values('produit').annotate(total=Sum('quantite'))
    }


def _cump(produit):
    """
    Coût Unitaire Moyen Pondéré calculé depuis les mouvements d'entrée
    qui ont un prix_unitaire_snapshot renseigné.
    """
    agg = Mouvement.objects.filter(
        produit=produit,
        type_mouvement='entree',
        prix_unitaire_snapshot__isnull=False,
    ).aggregate(
        total_qte=Sum('quantite'),
        total_val=Sum(
            ExpressionWrapper(
                F('quantite') * F('prix_unitaire_snapshot'),
                output_field=DecimalField()
            )
        ),
    )
    if agg['total_qte'] and agg['total_qte'] > 0:
        return (agg['total_val'] or Decimal('0')) / agg['total_qte']
    return produit.prix_unitaire or Decimal('0')


def _fifo(produit):
    """
    FIFO simplifié : prix du lot le plus ancien (premier mouvement d'entrée
    avec prix, ou premier bon de commande reçu).
    """
    if HAS_ACHATS:
        ligne = LigneCommande.objects.filter(
            produit=produit,
            bon_commande__statut__in=['recu', 'cloture'],
        ).order_by('bon_commande__date_creation').first()
        if ligne:
            return ligne.prix_unitaire
    entry = Mouvement.objects.filter(
        produit=produit,
        type_mouvement='entree',
        prix_unitaire_snapshot__isnull=False,
    ).order_by('date_mouvement').first()
    return entry.prix_unitaire_snapshot if entry else (produit.prix_unitaire or Decimal('0'))


def _csv(filename, headers, rows):
    """Génère une HttpResponse CSV avec BOM UTF-8 (compatible Excel)."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    w = csv.writer(response, delimiter=';')
    w.writerow(headers)
    for row in rows:
        w.writerow(row)
    return response


def _pdf(title, headers, rows):
    """Génère un PDF tabulaire simple avec reportlab."""
    if not HAS_REPORTLAB:
        return HttpResponse(
            "La bibliothèque reportlab n'est pas installée. "
            "Exécutez : pip install reportlab",
            status=501,
        )
    buf = io.BytesIO()
    p = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    p.setFont("Helvetica-Bold", 13)
    p.drawString(40, H - 46, title)
    p.setFont("Helvetica", 8)
    cw = (W - 80) / max(len(headers), 1)
    y = H - 68
    for i, h in enumerate(headers):
        p.drawString(40 + i * cw, y, str(h)[:20])
    y -= 4
    p.line(40, y, W - 40, y)
    y -= 12
    for row in rows:
        if y < 55:
            p.showPage()
            y = H - 55
        for i, cell in enumerate(row):
            p.drawString(40 + i * cw, y, str(cell)[:20])
        y -= 12
    p.save()
    buf.seek(0)
    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{title}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# VUE 1 : DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('comptable', 'super_admin', 'admin_ent')
def dashboard(request):
    entreprise = request.user.entreprise
    stocks = _stocks_dict(entreprise)
    produits = list(
        Produit.objects.filter(entreprise=entreprise, est_actif=True)
        .select_related('categorie')
    )

    valeur_cump = Decimal('0')
    valeur_fifo = Decimal('0')
    top_valeur = []

    for p in produits:
        qte = stocks.get(p.id, 0)
        if qte <= 0:
            continue
        vc = qte * _cump(p)
        vf = qte * _fifo(p)
        valeur_cump += vc
        valeur_fifo += vf
        top_valeur.append({'nom': p.nom, 'sku': p.sku, 'valeur_totale': vc})

    top_valeur.sort(key=lambda x: x['valeur_totale'], reverse=True)

    # Graphique 12 derniers mois (valeur courante)
    labels_mois, data_cump_chart, data_fifo_chart = [], [], []
    for i in range(11, -1, -1):
        d = (date.today().replace(day=1) - timedelta(days=30 * i))
        labels_mois.append(d.strftime('%b %y'))
        data_cump_chart.append(float(valeur_cump))
        data_fifo_chart.append(float(valeur_fifo))

    sorties_val = Mouvement.objects.filter(
        produit__entreprise=entreprise, type_mouvement='sortie'
    ).aggregate(
        val=Sum(
            ExpressionWrapper(
                F('quantite') * F('produit__prix_unitaire'),
                output_field=DecimalField()
            )
        )
    )['val'] or Decimal('0')

    ca_estime = sorties_val * Decimal('1.30')
    marge_brute = ca_estime - sorties_val
    marge_globale = (marge_brute / ca_estime * 100) if ca_estime else Decimal('0')

    context = {
        'valeur_stock_cump': valeur_cump,
        'valeur_stock_fifo': valeur_fifo,
        'marge_globale': marge_globale,
        'depreciation_totale': Decimal('0'),
        'nb_produits': len(top_valeur),
        'top_valeur': top_valeur[:5],
        'labels_mois': labels_mois,
        'data_cump': data_cump_chart,
        'data_fifo': data_fifo_chart,
        'exercice': date.today().year,
        'today': date.today(),
        'marge_nette_total': marge_brute,
    }
    return render(request, 'comptable/dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# VUE 2 : VALORISATION CUMP / FIFO
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('comptable', 'super_admin', 'admin_ent')
def valorisation(request):
    entreprise = request.user.entreprise
    methode = request.GET.get('methode', 'cump')
    categorie_id = request.GET.get('categorie')

    stocks = _stocks_dict(entreprise)
    produits_qs = Produit.objects.filter(
        entreprise=entreprise, est_actif=True
    ).select_related('categorie')
    if categorie_id:
        produits_qs = produits_qs.filter(categorie_id=categorie_id)

    valorisations = []
    for p in produits_qs:
        qte = stocks.get(p.id, 0)
        if qte <= 0:
            continue
        prix = _cump(p) if methode == 'cump' else _fifo(p)
        valeur = qte * prix
        valorisations.append({
            'nom': p.nom,
            'sku': p.sku,
            'categorie__nom': p.categorie.nom if p.categorie else None,
            'quantite_totale': qte,
            'prix_unitaire_calcule': prix,
            'valeur_totale': valeur,
            'pct_total': Decimal('0'),
            'variation': Decimal('0'),
        })

    valeur_totale = sum(v['valeur_totale'] for v in valorisations)
    for v in valorisations:
        v['pct_total'] = (
            v['valeur_totale'] / valeur_totale * 100
            if valeur_totale else Decimal('0')
        )

    export = request.GET.get('export')
    if export == 'csv':
        rows = [
            (
                v['nom'], v['sku'], v['categorie__nom'],
                v['quantite_totale'],
                float(v['prix_unitaire_calcule']),
                float(v['valeur_totale']),
                '370000',
                f"{float(v['pct_total']):.1f}%",
            )
            for v in valorisations
        ]
        return _csv(
            f'valorisation_{methode}_{date.today()}.csv',
            ['Produit', 'SKU', 'Catégorie', 'Quantité',
             f'PU {methode.upper()} (€)', 'Valeur (€)', 'N° Compte', '% Total'],
            rows,
        )
    if export == 'pdf':
        rows = [
            (
                v['nom'][:20], v['quantite_totale'],
                f"{float(v['prix_unitaire_calcule']):.2f}€",
                f"{float(v['valeur_totale']):.2f}€",
                '370000',
            )
            for v in valorisations
        ]
        return _pdf(
            f'Valorisation {methode.upper()} — {date.today()}',
            ['Produit', 'Qté', f'PU {methode.upper()}', 'Valeur (€)', 'N° Compte'],
            rows,
        )

    paginator = Paginator(valorisations, 50)
    page = paginator.get_page(request.GET.get('page'))

    context = {
        'valorisations': page,
        'valeur_totale': valeur_totale,
        'nb_produits': len(valorisations),
        'methode_affichee': methode.upper(),
        'variation_mois': Decimal('0'),
        'categories': Categorie.objects.filter(entreprise=entreprise),
    }
    return render(request, 'comptable/valorisation.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# VUE 3 : HISTORIQUE DES PRIX D'ACHAT
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('comptable', 'super_admin', 'admin_ent')
def prix(request):
    entreprise = request.user.entreprise
    debut, fin = _get_periode(request)

    qs = Mouvement.objects.filter(
        produit__entreprise=entreprise,
        type_mouvement='entree',
        prix_unitaire_snapshot__isnull=False,
        date_mouvement__date__range=(debut, fin),
    ).select_related('produit', 'produit__categorie').order_by('produit', 'date_mouvement')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(produit__nom__icontains=q) | Q(produit__sku__icontains=q)
        )

    precedents = {}
    historique = []
    for m in qs:
        pid = m.produit_id
        prix_courant = m.prix_unitaire_snapshot
        variation = None
        if pid in precedents and precedents[pid]:
            prev = precedents[pid]
            variation = ((prix_courant - prev) / prev * 100) if prev else None
        precedents[pid] = prix_courant
        historique.append({
            'produit__nom': m.produit.nom,
            'produit__sku': m.produit.sku,
            'fournisseur__nom': None,
            'date': m.date_mouvement.date(),
            'prix_unitaire': prix_courant,
            'quantite': m.quantite,
            'reference_bc': m.reference,
            'variation_pct': variation,
        })

    if request.GET.get('export') == 'csv':
        rows = [
            (
                h['produit__nom'], h['produit__sku'],
                str(h['date']),
                float(h['prix_unitaire']),
                h['quantite'],
                h['reference_bc'] or '',
                f"{float(h['variation_pct']):.1f}%" if h['variation_pct'] is not None else 'Premier prix',
            )
            for h in historique
        ]
        return _csv(
            f'historique_prix_{debut}_{fin}.csv',
            ['Produit', 'SKU', 'Date', 'Prix achat (€)',
             'Quantité', 'Référence BC', 'Variation'],
            rows,
        )

    paginator = Paginator(historique, 50)
    page = paginator.get_page(request.GET.get('page'))

    context = {
        'historique_prix': page,
        'fournisseurs': [],
        'date_debut': debut,
        'date_fin': fin,
    }
    return render(request, 'comptable/prix.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# VUE 4 : MARGES (nécessite le champ prix_vente dans Produit)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('comptable', 'super_admin', 'admin_ent')
def marges(request):
    entreprise = request.user.entreprise
    categorie_id = request.GET.get('categorie')
    tri = request.GET.get('tri', 'marge_desc')

    produits_qs = Produit.objects.filter(
        entreprise=entreprise, est_actif=True, prix_vente__isnull=False
    ).exclude(prix_vente=0).select_related('categorie')
    if categorie_id:
        produits_qs = produits_qs.filter(categorie_id=categorie_id)

    marges_data = []
    for p in produits_qs:
        qte_vendue = (
            Mouvement.objects.filter(produit=p, type_mouvement='sortie')
            .aggregate(total=Sum('quantite'))['total'] or 0
        )
        prix_achat = _cump(p)
        prix_vente = p.prix_vente or Decimal('0')
        marge_u = prix_vente - prix_achat
        marge_pct = (marge_u / prix_vente * 100) if prix_vente else Decimal('0')
        marge_tot = marge_u * qte_vendue

        marges_data.append({
            'nom': p.nom,
            'sku': p.sku,
            'prix_achat_cump': prix_achat,
            'prix_vente': prix_vente,
            'marge_unitaire': marge_u,
            'marge_pct': marge_pct,
            'qte_vendue': qte_vendue,
            'marge_totale': marge_tot,
        })

    cle = 'marge_pct' if 'marge' in tri else 'marge_totale'
    reverse = not tri.endswith('asc')
    marges_data.sort(key=lambda x: x[cle], reverse=reverse)

    ca_total = sum(m['prix_vente'] * m['qte_vendue'] for m in marges_data)
    cout_total = sum(m['prix_achat_cump'] * m['qte_vendue'] for m in marges_data)
    marge_brute_glob = (ca_total - cout_total) / ca_total * 100 if ca_total else Decimal('0')
    marge_nette_tot = ca_total - cout_total

    nb_haute = sum(1 for m in marges_data if m['marge_pct'] > 20)
    nb_med = sum(1 for m in marges_data if 10 <= m['marge_pct'] <= 20)
    nb_basse = sum(1 for m in marges_data if m['marge_pct'] < 10)

    if request.GET.get('export') == 'csv':
        rows = [
            (
                m['nom'], m['sku'],
                float(m['prix_achat_cump']),
                float(m['prix_vente']),
                float(m['marge_unitaire']),
                f"{float(m['marge_pct']):.1f}%",
                m['qte_vendue'],
                float(m['marge_totale']),
            )
            for m in marges_data
        ]
        return _csv(
            f'marges_{date.today()}.csv',
            ['Produit', 'SKU', 'PU achat CUMP (€)', 'PU vente (€)',
             'Marge U. (€)', 'Marge %', 'Qté vendue', 'Marge totale (€)'],
            rows,
        )

    context = {
        'marges': marges_data,
        'ca_total': ca_total,
        'cout_total': cout_total,
        'marge_brute_globale': marge_brute_glob,
        'marge_nette_total': marge_nette_tot,
        'nb_marge_haute': nb_haute,
        'nb_marge_med': nb_med,
        'nb_marge_basse': nb_basse,
        'categories': Categorie.objects.filter(entreprise=entreprise),
    }
    return render(request, 'comptable/marges.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# VUE 5 : DÉPRÉCIATION
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('comptable', 'super_admin', 'admin_ent')
def depreciation(request):
    entreprise = request.user.entreprise
    seuil_jours = int(request.GET.get('seuil', 90))
    seuil_date = date.today() - timedelta(days=seuil_jours)
    stocks = _stocks_dict(entreprise)

    deprecies = []
    for p in Produit.objects.filter(entreprise=entreprise, est_actif=True):
        qte = stocks.get(p.id, 0)
        if qte <= 0:
            continue
        dernier = Mouvement.objects.filter(produit=p).aggregate(
            Max('date_mouvement')
        )['date_mouvement__max']
        if not dernier or dernier.date() >= seuil_date:
            continue

        jours_inactif = (date.today() - dernier.date()).days
        taux = min(Decimal('50'), Decimal('5') * (jours_inactif // 30))
        valeur_init = qte * (p.prix_unitaire or Decimal('0'))
        montant_dep = valeur_init * taux / 100

        deprecies.append({
            'nom': p.nom,
            'sku': p.sku,
            'valeur_initiale': valeur_init,
            'valeur_actuelle': valeur_init - montant_dep,
            'montant_depreciation': montant_dep,
            'taux': taux,
            'motif': f"Inactif depuis {jours_inactif} jours",
            'date': dernier.date(),
        })

    depreciation_totale = sum(d['montant_depreciation'] for d in deprecies)
    taux_moyen = (
        sum(d['taux'] for d in deprecies) / len(deprecies)
        if deprecies else Decimal('0')
    )

    if request.GET.get('export') == 'csv':
        rows = [
            (
                d['nom'], d['sku'],
                float(d['valeur_initiale']),
                float(d['valeur_actuelle']),
                float(d['montant_depreciation']),
                f"{float(d['taux']):.0f}%",
                str(d['date']),
                d['motif'],
            )
            for d in deprecies
        ]
        return _csv(
            f'depreciation_{date.today()}.csv',
            ['Produit', 'SKU', 'Valeur init. (€)', 'Valeur actuelle (€)',
             'Dépréciation (€)', 'Taux', 'Dernier mouvement', 'Motif'],
            rows,
        )

    context = {
        'produits_deprecies': deprecies,
        'depreciation_totale': depreciation_totale,
        'nb_produits_deprecies': len(deprecies),
        'taux_depreciation_moyen': taux_moyen,
        'seuils': [60, 90, 120, 180],
    }
    return render(request, 'comptable/depreciation.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# VUE 6 : RAPPORTS COMPTABLES
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('comptable', 'super_admin', 'admin_ent')
def rapports(request):
    entreprise = request.user.entreprise
    periode_param = request.GET.get('periode', 'mois_courant')
    today = date.today()

    # Calcul de la période
    if periode_param == 'trimestre':
        mois_debut = ((today.month - 1) // 3) * 3 + 1
        debut = today.replace(month=mois_debut, day=1)
        fin = today
        periode_label = f"T{(mois_debut - 1) // 3 + 1} {today.year}"
    elif periode_param == 'annee':
        debut = today.replace(month=1, day=1)
        fin = today
        periode_label = str(today.year)
    elif periode_param == 'custom':
        debut, fin = _get_periode(request)
        periode_label = f"{debut.strftime('%d/%m/%Y')} – {fin.strftime('%d/%m/%Y')}"
    else:
        debut = today.replace(day=1)
        fin = today
        periode_label = today.strftime('%B %Y')

    stocks = _stocks_dict(entreprise)
    produits = list(
        Produit.objects.filter(entreprise=entreprise, est_actif=True)
        .select_related('categorie')
    )

    valeur_finale = sum(
        stocks.get(p.id, 0) * _cump(p) for p in produits
    )

    entrees_periode = Mouvement.objects.filter(
        produit__entreprise=entreprise,
        type_mouvement='entree',
        date_mouvement__date__range=(debut, fin),
    ).aggregate(
        val=Sum(
            ExpressionWrapper(
                F('quantite') * F('prix_unitaire_snapshot'),
                output_field=DecimalField()
            )
        )
    )['val'] or Decimal('0')

    sorties_periode = Mouvement.objects.filter(
        produit__entreprise=entreprise,
        type_mouvement='sortie',
        date_mouvement__date__range=(debut, fin),
    ).aggregate(
        val=Sum(
            ExpressionWrapper(
                F('quantite') * F('produit__prix_unitaire'),
                output_field=DecimalField()
            )
        )
    )['val'] or Decimal('0')

    stock_initial = valeur_finale - entrees_periode + sorties_periode
    ca_estime = sorties_periode * Decimal('1.30')
    marge_brute = ca_estime - sorties_periode
    taux_marge = (marge_brute / ca_estime * 100) if ca_estime else Decimal('0')

    cats = Categorie.objects.filter(entreprise=entreprise)
    rapport_categories = []
    totaux = {
        'debut': Decimal('0'),
        'entrees': Decimal('0'),
        'sorties': Decimal('0'),
        'fin': Decimal('0'),
        'marge_pct': Decimal('0'),
    }

    for cat in cats:
        prods_cat = [p for p in produits if p.categorie_id == cat.id]
        val_fin = sum(stocks.get(p.id, 0) * _cump(p) for p in prods_cat)

        ent_cat = Mouvement.objects.filter(
            produit__categorie=cat,
            produit__entreprise=entreprise,
            type_mouvement='entree',
            date_mouvement__date__range=(debut, fin),
        ).aggregate(
            val=Sum(
                ExpressionWrapper(
                    F('quantite') * F('prix_unitaire_snapshot'),
                    output_field=DecimalField()
                )
            )
        )['val'] or Decimal('0')

        sor_cat = Mouvement.objects.filter(
            produit__categorie=cat,
            produit__entreprise=entreprise,
            type_mouvement='sortie',
            date_mouvement__date__range=(debut, fin),
        ).aggregate(
            val=Sum(
                ExpressionWrapper(
                    F('quantite') * F('produit__prix_unitaire'),
                    output_field=DecimalField()
                )
            )
        )['val'] or Decimal('0')

        val_debut = val_fin - ent_cat + sor_cat
        ca_cat = sor_cat * Decimal('1.30')
        marge_p = ((ca_cat - sor_cat) / ca_cat * 100) if ca_cat else Decimal('0')

        rapport_categories.append({
            'nom': cat.nom,
            'nb_produits': len(prods_cat),
            'valeur_debut': val_debut,
            'entrees': ent_cat,
            'sorties': sor_cat,
            'valeur_fin': val_fin,
            'marge_pct': marge_p,
            'compte_comptable': '370000',
        })
        totaux['debut'] += val_debut
        totaux['entrees'] += ent_cat
        totaux['sorties'] += sor_cat
        totaux['fin'] += val_fin

    tot_ca = totaux['sorties'] * Decimal('1.30')
    totaux['marge_pct'] = (
        (tot_ca - totaux['sorties']) / tot_ca * 100
        if tot_ca else Decimal('0')
    )

    if request.GET.get('export') == 'pdf':
        rows = [
            (
                c['nom'],
                f"{float(c['valeur_debut']):.2f}€",
                f"+{float(c['entrees']):.2f}€",
                f"-{float(c['sorties']):.2f}€",
                f"{float(c['valeur_fin']):.2f}€",
                f"{float(c['marge_pct']):.1f}%",
            )
            for c in rapport_categories
        ]
        rows.append((
            'TOTAL',
            f"{float(totaux['debut']):.2f}€",
            f"+{float(totaux['entrees']):.2f}€",
            f"-{float(totaux['sorties']):.2f}€",
            f"{float(totaux['fin']):.2f}€",
            f"{float(totaux['marge_pct']):.1f}%",
        ))
        return _pdf(
            f'Rapport Comptable Stock — {periode_label}',
            ['Catégorie', 'Stock début', 'Entrées', 'Sorties', 'Stock fin', 'Marge'],
            rows,
        )

    context = {
        'rapport_categories': rapport_categories,
        'totaux': totaux,
        'stock_initial': stock_initial,
        'entrees_periode': entrees_periode,
        'sorties_periode': sorties_periode,
        'depreciations_periode': Decimal('0'),
        'stock_final': valeur_finale,
        'ca_estime': ca_estime,
        'cout_ventes': sorties_periode,
        'marge_brute': marge_brute,
        'taux_marge': taux_marge,
        'periode_label': periode_label,
        'exercice': today.year,
        'today': today,
    }
    return render(request, 'comptable/rapports.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# VUE 7 : EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('comptable', 'super_admin', 'admin_ent')
def exports(request):
    entreprise = request.user.entreprise
    type_export = request.GET.get('type', '')
    debut, fin = _get_periode(request)

    if type_export == 'valorisation_cump_csv':
        stocks = _stocks_dict(entreprise)
        rows = []
        for p in Produit.objects.filter(entreprise=entreprise, est_actif=True).select_related('categorie'):
            qte = stocks.get(p.id, 0)
            if qte <= 0:
                continue
            prix = _cump(p)
            rows.append((
                p.nom, p.sku,
                p.categorie.nom if p.categorie else '',
                qte,
                float(prix),
                float(qte * prix),
                '370000',
            ))
        return _csv(
            f'valorisation_cump_{date.today()}.csv',
            ['Produit', 'SKU', 'Catégorie', 'Quantité',
             'PU CUMP (€)', 'Valeur (€)', 'N° Compte'],
            rows,
        )

    if type_export == 'marges_csv':
        rows = []
        for p in Produit.objects.filter(entreprise=entreprise, est_actif=True, prix_vente__isnull=False).exclude(prix_vente=0):
            qte_v = Mouvement.objects.filter(produit=p, type_mouvement='sortie').aggregate(t=Sum('quantite'))['t'] or 0
            pa = _cump(p)
            pv = p.prix_vente or Decimal('0')
            mu = pv - pa
            mp = (mu / pv * 100) if pv else Decimal('0')
            rows.append((
                p.nom, p.sku,
                float(pa), float(pv),
                float(mu), f"{float(mp):.1f}%",
                qte_v, float(mu * qte_v),
            ))
        return _csv(
            f'marges_{date.today()}.csv',
            ['Produit', 'SKU', 'PU achat (€)', 'PU vente (€)',
             'Marge U. (€)', 'Marge %', 'Qté vendue', 'Marge totale (€)'],
            rows,
        )

    if type_export == 'rapport_comptable_pdf':
        stocks = _stocks_dict(entreprise)
        val = sum(
            stocks.get(p.id, 0) * _cump(p)
            for p in Produit.objects.filter(entreprise=entreprise, est_actif=True)
        )
        return _pdf(
            f'Rapport Comptable Stock — {date.today()}',
            ['Désignation', 'Montant (€)', 'N° Compte'],
            [('Stock total valorisé CUMP', f"{float(val):.2f}", '370000')],
        )

    if type_export == 'depreciation_csv':
        seuil_date = date.today() - timedelta(days=90)
        stocks = _stocks_dict(entreprise)
        rows = []
        for p in Produit.objects.filter(entreprise=entreprise, est_actif=True):
            qte = stocks.get(p.id, 0)
            if qte <= 0:
                continue
            dernier = Mouvement.objects.filter(produit=p).aggregate(Max('date_mouvement'))['date_mouvement__max']
            if not dernier or dernier.date() >= seuil_date:
                continue
            jours = (date.today() - dernier.date()).days
            taux = min(Decimal('50'), Decimal('5') * (jours // 30))
            val_init = qte * (p.prix_unitaire or Decimal('0'))
            dep = val_init * taux / 100
            rows.append((
                p.nom, p.sku,
                float(val_init), float(val_init - dep),
                float(dep), f"{float(taux):.0f}%", str(dernier.date())
            ))
        return _csv(
            f'depreciation_{date.today()}.csv',
            ['Produit', 'SKU', 'Valeur init. (€)', 'Valeur actuelle (€)',
             'Dépréciation (€)', 'Taux', 'Dernier mouvement'],
            rows,
        )

    blocs_export = [
        {'nom': 'Valorisation CUMP', 'description': 'Stock valorisé au Coût Unitaire Moyen Pondéré',
         'code': 'valorisation_cump', 'icon': 'fas fa-calculator', 'color': '#f97316', 'bg': '#fff7ed'},
        {'nom': 'Analyse des marges', 'description': 'Prix achat CUMP vs prix de vente, marge par produit',
         'code': 'marges', 'icon': 'fas fa-chart-line', 'color': '#059669', 'bg': '#ecfdf5'},
        {'nom': 'Rapport comptable', 'description': 'Compte 370000 — variation de stock sur la période',
         'code': 'rapport_comptable', 'icon': 'fas fa-book', 'color': '#2563eb', 'bg': '#eff6ff'},
        {'nom': 'Dépréciation', 'description': 'Stocks inactifs depuis plus de 90 jours',
         'code': 'depreciation', 'icon': 'fas fa-arrow-trend-down', 'color': '#dc2626', 'bg': '#fef2f2'},
    ]
    context = {
        'blocs_export': blocs_export,
        'exports_recents': ExportLog.objects.filter(entreprise=entreprise).select_related('utilisateur')[:10],
    }
    return render(request, 'comptable/exports.html', context)