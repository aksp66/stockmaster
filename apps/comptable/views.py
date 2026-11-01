import csv
from apps.core import csv_safe
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
from .valorisation import FLUX, prix_fifo_produits, valoriser_produits

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
            entrepot__entreprise=entreprise
        ).values('produit').annotate(total=Sum('quantite'))
    }


def _cumps(produits):
    """CUMP permanent de plusieurs produits en un seul rejeu (une requête au lieu d'une par produit)."""
    return {pid: v['cump'] for pid, v in valoriser_produits(produits).items()}


def _lignes_marges(produits):
    """
    Marge réalisée par produit, sur tout l'historique :
    - coût des ventes au coût moyen du moment de chaque vente (rejeu au CUMP permanent) ;
    - chiffre d'affaires au prix de vente pratiqué lors de chaque vente (enregistré sur le mouvement) ;
    - quantités et montants nets des retours clients (un retour annule une vente).
    Le prix de vente affiché est le prix moyen pratiqué. Produit jamais vendu : prix de vente actuel et
    CUMP actuel (marge théorique), quantités à zéro.
    """
    produits = list(produits)
    valeurs = valoriser_produits(produits)
    lignes = []
    for p in produits:
        v = valeurs[p.pk]
        qte_nette = v['qte_ventes'] - v['qte_retours_clients']
        cout_ventes = v['cout_ventes_pv']
        vendu = qte_nette > 0
        cout_unitaire = cout_ventes / qte_nette if vendu else v['cump']
        prix_vente = v['ca'] / qte_nette if vendu else (p.prix_vente or Decimal('0'))
        marge_u = prix_vente - cout_unitaire
        lignes.append({
            'nom': p.nom,
            'sku': p.sku,
            'prix_achat_cump': cout_unitaire,
            'prix_vente': prix_vente,
            'prix_vente_actuel': p.prix_vente or Decimal('0'),
            'marge_unitaire': marge_u,
            'marge_pct': (marge_u / prix_vente * 100) if prix_vente else Decimal('0'),
            'qte_vendue': qte_nette,
            'qte_retournee': v['qte_retours_clients'],
            'chiffre_affaires': v['ca'] if vendu else Decimal('0'),
            'cout_ventes': cout_ventes if vendu else Decimal('0'),
            'marge_totale': (v['ca'] - cout_ventes) if vendu else Decimal('0'),
        })
    return lignes


def _csv(filename, headers, rows):
    """Génère une HttpResponse CSV avec BOM UTF-8 (compatible Excel)."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    w = csv_safe.writer(response, delimiter=';')
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

    cumps = _cumps(produits)
    fifos = prix_fifo_produits(produits)
    for p in produits:
        qte = stocks.get(p.id, 0)
        if qte <= 0:
            continue
        vc = qte * cumps[p.pk]
        vf = qte * fifos[p.pk]
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
    prix_unitaires = _cumps(produits_qs) if methode == 'cump' else prix_fifo_produits(produits_qs)
    for p in produits_qs:
        qte = stocks.get(p.id, 0)
        if qte <= 0:
            continue
        prix = prix_unitaires[p.pk]
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
             f'PU {methode.upper()} (FCFA)', 'Valeur (FCFA)', 'N° Compte', '% Total'],
            rows,
        )
    if export == 'pdf':
        rows = [
            (
                v['nom'][:20], v['quantite_totale'],
                f"{float(v['prix_unitaire_calcule']):.2f} FCFA",
                f"{float(v['valeur_totale']):.2f} FCFA",
                '370000',
            )
            for v in valorisations
        ]
        return _pdf(
            f'Valorisation {methode.upper()} — {date.today()}',
            ['Produit', 'Qté', f'PU {methode.upper()}', 'Valeur (FCFA)', 'N° Compte'],
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
            ['Produit', 'SKU', 'Date', 'Prix achat (FCFA)',
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

    marges_data = _lignes_marges(produits_qs)

    cle = 'marge_pct' if 'marge' in tri else 'marge_totale'
    reverse = not tri.endswith('asc')
    marges_data.sort(key=lambda x: x[cle], reverse=reverse)

    ca_total = sum(m['chiffre_affaires'] for m in marges_data)
    cout_total = sum(m['cout_ventes'] for m in marges_data)
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
                m['qte_retournee'],
                float(m['marge_totale']),
            )
            for m in marges_data
        ]
        return _csv(
            f'marges_{date.today()}.csv',
            ['Produit', 'SKU', 'Coût unitaire réel (FCFA)', 'PU vente moyen pratiqué (FCFA)',
             'Marge U. (FCFA)', 'Marge %', 'Qté vendue nette', 'dont retours clients', 'Marge totale (FCFA)'],
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
            ['Produit', 'SKU', 'Valeur init. (FCFA)', 'Valeur actuelle (FCFA)',
             'Dépréciation (FCFA)', 'Taux', 'Dernier mouvement', 'Motif'],
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

    # Tous les produits (y compris inactifs : ils peuvent avoir du stock ou des mouvements sur la période)
    produits = list(Produit.objects.filter(entreprise=entreprise).select_related('categorie'))
    valeurs = valoriser_produits(produits, debut, fin)

    def cumuler(liste):
        total = {cle: Decimal('0') for cle in ('debut', 'fin', 'ca', 'cout_ventes_pv', *FLUX)}
        for p in liste:
            v = valeurs[p.pk]
            total['debut'] += v['valeur_debut']
            total['fin'] += v['valeur_fin']
            for cle in FLUX:
                total[cle] += v[cle]
            total['ca'] += v['ca']  # au prix pratiqué, net des retours clients
            total['cout_ventes_pv'] += v['cout_ventes_pv']
        total['entrees_total'] = sum(total[c] for c, sens in FLUX.items() if sens > 0)
        total['sorties_total'] = sum(total[c] for c, sens in FLUX.items() if sens < 0)
        total['marge_pct'] = ((total['ca'] - total['cout_ventes_pv']) / total['ca'] * 100) if total['ca'] else None
        return total

    groupes = defaultdict(list)
    for p in produits:
        groupes[p.categorie.nom if p.categorie else 'Sans catégorie'].append(p)
    rapport_categories = [
        {'nom': nom, 'nb_produits': len(liste), 'compte_comptable': '370000', **cumuler(liste)}
        for nom, liste in sorted(groupes.items(), key=lambda g: (g[0] == 'Sans catégorie', g[0].lower()))
    ]
    totaux = cumuler(produits)
    sans_pv = sum(1 for p in produits if valeurs[p.pk]['qte_sans_prix_vente'] > 0)
    marge_brute = totaux['ca'] - totaux['cout_ventes_pv']

    if request.GET.get('export') in ('pdf', 'csv'):
        def montant(v):
            return f"{v:,.0f}".replace(',', ' ')
        entetes = ['Catégorie', 'Stock début', 'Achats', 'Retours clients', 'Ajust. +', 'Ventes (coût)',
                   'Pertes', 'Retours fourn.', 'Ajust. −', 'Stock fin', 'Marge']
        lignes = [
            [c['nom'], montant(c['debut']), montant(c['entrees']), montant(c['retours_clients']),
             montant(c['ajustements_plus']), montant(c['sorties']), montant(c['pertes']),
             montant(c['retours_fournisseurs']), montant(c['ajustements_moins']), montant(c['fin']),
             '—' if c['marge_pct'] is None else f"{c['marge_pct']:.1f} %"]
            for c in rapport_categories + [{'nom': 'TOTAL', **totaux}]
        ]
        if request.GET['export'] == 'csv':
            return _csv(f"rapport_stock_{debut}_{fin}.csv", entetes, lignes)
        return _pdf(f'Rapport de stock (FCFA) — {periode_label}', entetes, lignes)

    context = {
        'rapport_categories': rapport_categories,
        'totaux': totaux,
        'stock_initial': totaux['debut'],
        'stock_final': totaux['fin'],
        'flux': totaux,
        'ca': totaux['ca'],
        'cout_ventes': totaux['cout_ventes_pv'],
        'marge_brute': marge_brute,
        'taux_marge': totaux['marge_pct'],
        'nb_produits_sans_pv': sans_pv,
        'debut': debut,
        'fin': fin,
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
        produits = list(Produit.objects.filter(entreprise=entreprise, est_actif=True).select_related('categorie'))
        cumps = _cumps(produits)
        for p in produits:
            qte = stocks.get(p.id, 0)
            if qte <= 0:
                continue
            prix = cumps[p.pk]
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
             'PU CUMP (FCFA)', 'Valeur (FCFA)', 'N° Compte'],
            rows,
        )

    if type_export == 'marges_csv':
        produits = Produit.objects.filter(entreprise=entreprise, est_actif=True, prix_vente__isnull=False).exclude(prix_vente=0)
        rows = [
            (m['nom'], m['sku'], float(m['prix_achat_cump']), float(m['prix_vente']), float(m['marge_unitaire']),
             f"{float(m['marge_pct']):.1f}%", m['qte_vendue'], float(m['marge_totale']))
            for m in _lignes_marges(produits)
        ]
        return _csv(
            f'marges_{date.today()}.csv',
            ['Produit', 'SKU', 'Coût unitaire réel (FCFA)', 'PU vente moyen pratiqué (FCFA)',
             'Marge U. (FCFA)', 'Marge %', 'Qté vendue nette', 'Marge totale (FCFA)'],
            rows,
        )

    if type_export == 'rapport_comptable_pdf':
        stocks = _stocks_dict(entreprise)
        produits = list(Produit.objects.filter(entreprise=entreprise, est_actif=True))
        cumps = _cumps(produits)
        val = sum(stocks.get(p.id, 0) * cumps[p.pk] for p in produits)
        return _pdf(
            f'Rapport Comptable Stock — {date.today()}',
            ['Désignation', 'Montant (FCFA)', 'N° Compte'],
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
            ['Produit', 'SKU', 'Valeur init. (FCFA)', 'Valeur actuelle (FCFA)',
             'Dépréciation (FCFA)', 'Taux', 'Dernier mouvement'],
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