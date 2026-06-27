import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.db.models import (
    Sum, Count, F, Q,
    ExpressionWrapper, DecimalField,
)

from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.stock.models import (
    Produit, Stock, Mouvement, TypeMouvement,
    InventaireSession, LigneInventaire,
    Categorie, Entrepot, Alerte
)
from apps.core.models import AuditLog, TypeAction, ExportLog
from apps.accounts.models import Utilisateur

try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def _get_periode(request, defaut_jours=30):
    today = date.today()
    try:
        debut = date.fromisoformat(request.GET.get('date_debut', ''))
    except ValueError:
        debut = today - timedelta(days=defaut_jours)
    try:
        fin = date.fromisoformat(request.GET.get('date_fin', ''))
    except ValueError:
        fin = today
    return debut, fin


def _valeur_stock(entreprise):
    return Stock.objects.filter(
        entrepot__entreprise=entreprise
    ).aggregate(
        total=Sum(
            ExpressionWrapper(
                F('quantite') * F('produit__prix_unitaire'),
                output_field=DecimalField()
            )
        )
    )['total'] or Decimal('0')


def _csv(filename, headers, rows):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    w = csv.writer(response, delimiter=';')
    w.writerow(headers)
    for row in rows:
        w.writerow(row)
    return response


def _pdf(title, headers, rows):
    if not HAS_REPORTLAB:
        return HttpResponse(
            "La bibliothèque reportlab n'est pas installée. "
            "Exécutez : pip install reportlab",
            status=501
        )
    buf = io.BytesIO()
    p = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, H - 48, title)
    p.setFont("Helvetica", 9)
    y = H - 72
    col_w = (W - 80) / max(len(headers), 1)
    for i, h in enumerate(headers):
        p.drawString(40 + i * col_w, y, str(h)[:22])
    y -= 4
    p.line(40, y, W - 40, y)
    y -= 12
    for row in rows:
        if y < 55:
            p.showPage()
            y = H - 55
        for i, cell in enumerate(row):
            p.drawString(40 + i * col_w, y, str(cell)[:22])
        y -= 13
    p.save()
    buf.seek(0)
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{title}.pdf"'
    return response


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@role_required('auditeur', 'super_admin', 'admin_ent')
def dashboard(request):
    entreprise = request.user.entreprise
    debut, fin = _get_periode(request)

    mouvements_qs = Mouvement.objects.filter(
        produit__entreprise=entreprise,
        date_mouvement__date__range=(debut, fin),
    )
    valeur_stock = _valeur_stock(entreprise)
    nb_logs = AuditLog.objects.filter(entreprise=entreprise).count()

    total_m = mouvements_qs.count()
    avec_ref = mouvements_qs.exclude(reference__isnull=True).exclude(reference__exact='').count()
    taux_conformite = round((avec_ref / total_m * 100) if total_m else 100)

    TYPES = [
        ('entree',     'Entrées',      'fas fa-arrow-down',  '#059669', '#ecfdf5'),
        ('sortie',     'Sorties',      'fas fa-arrow-up',    '#dc2626', '#fef2f2'),
        ('transfert',  'Transferts',   'fas fa-arrows-rotate','#2563eb', '#eff6ff'),
        ('ajustement', 'Ajustements',  'fas fa-wrench',      '#d97706', '#fffbeb'),
    ]
    resume_mouvements = []
    for code, label, icon, color, bg in TYPES:
        agg = mouvements_qs.filter(type_mouvement=code).aggregate(
            total=Sum('quantite'),
            nb=Count('id'),
            montant=Sum(
                ExpressionWrapper(
                    F('quantite') * F('produit__prix_unitaire'),
                    output_field=DecimalField()
                )
            ),
        )
        resume_mouvements.append({
            'label':   label,
            'icon':    icon,
            'color':   color,
            'bg':      bg,
            'total':   agg['total']   or 0,
            'nb_ops':  agg['nb']      or 0,
            'montant': agg['montant'] or Decimal('0'),
        })

    # Graphique (juste la valeur actuelle répétée sur 12 semaines)
    labels_valeur, data_valeur = [], []
    for i in range(11, -1, -1):
        d = date.today() - timedelta(weeks=i)
        labels_valeur.append(d.strftime('%d/%m'))
        data_valeur.append(float(valeur_stock))

    total_ecarts = LigneInventaire.objects.filter(
        session__entrepot__entreprise=entreprise,
        quantite_comptee__isnull=False,
    ).exclude(
        quantite_comptee=F('quantite_theorique')
    ).count()

    derniers_logs = AuditLog.objects.filter(
        entreprise=entreprise
    ).order_by('-created_at').select_related('utilisateur')[:5]

    context = {
        'periode_debut':      debut,
        'periode_fin':        fin,
        'total_mouvements':   total_m,
        'total_ecarts':       total_ecarts,
        'valeur_stock':       valeur_stock,
        'nb_logs':            nb_logs,
        'taux_conformite':    taux_conformite,
        'resume_mouvements':  resume_mouvements,
        'derniers_logs':      derniers_logs,
        'alertes_conformite': [],
        'labels_valeur':      labels_valeur,
        'data_valeur':        data_valeur,
    }
    return render(request, 'auditeur/dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# MOUVEMENTS
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@role_required('auditeur', 'super_admin', 'admin_ent')
def mouvements(request):
    entreprise = request.user.entreprise
    debut, fin = _get_periode(request)

    qs = Mouvement.objects.filter(
        produit__entreprise=entreprise,
        date_mouvement__date__range=(debut, fin),
    ).select_related(
        'produit', 'produit__categorie', 'entrepot_source', 'entrepot_destination', 'utilisateur'
    ).order_by('-date_mouvement').annotate(
        valeur_totale=ExpressionWrapper(
            F('quantite') * F('produit__prix_unitaire'),
            output_field=DecimalField()
        )
    )

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(produit__nom__icontains=q)
            | Q(produit__sku__icontains=q)
            | Q(reference__icontains=q)
        )
    if type_m := request.GET.get('type'):
        qs = qs.filter(type_mouvement=type_m)
    if entrepot_id := request.GET.get('entrepot'):
        qs = qs.filter(Q(entrepot_source_id=entrepot_id) | Q(entrepot_destination_id=entrepot_id))
    if user_id := request.GET.get('utilisateur'):
        qs = qs.filter(utilisateur_id=user_id)

    export = request.GET.get('export')
    if export == 'csv':
        rows = []
        for m in qs:
            entrepot = m.entrepot_destination or m.entrepot_source
            rows.append((
                m.date_mouvement.strftime('%d/%m/%Y %H:%M'),
                m.produit.nom, m.produit.sku,
                m.get_type_mouvement_display(),
                m.quantite,
                float(m.produit.prix_unitaire),
                float(m.valeur_totale or 0),
                entrepot.nom if entrepot else '',
                m.utilisateur.get_full_name() if m.utilisateur else '',
                m.reference or '',
            ))
        return _csv(
            f'mouvements_{debut}_{fin}.csv',
            ['Date', 'Produit', 'SKU', 'Type', 'Quantité',
             'Prix U. (€)', 'Valeur (€)', 'Entrepôt', 'Opérateur', 'Référence'],
            rows,
        )
    if export == 'pdf':
        rows = []
        for m in qs[:500]:
            rows.append((
                m.date_mouvement.strftime('%d/%m/%Y'),
                m.produit.nom[:20],
                m.get_type_mouvement_display(),
                m.quantite,
                f"{float(m.valeur_totale or 0):.2f}€",
            ))
        return _pdf(
            f'Mouvements Audit {debut} – {fin}',
            ['Date', 'Produit', 'Type', 'Qté', 'Valeur'],
            rows,
        )

    agg = qs.aggregate(
        total_entrees=Sum('quantite',     filter=Q(type_mouvement=TypeMouvement.ENTREE)),
        total_sorties=Sum('quantite',     filter=Q(type_mouvement=TypeMouvement.SORTIE)),
        total_transferts=Count('id',      filter=Q(type_mouvement=TypeMouvement.TRANSFERT)),
        total_ajustements=Count('id',     filter=Q(type_mouvement=TypeMouvement.AJUSTEMENT)),
        montant_entrees=Sum('valeur_totale', filter=Q(type_mouvement=TypeMouvement.ENTREE)),
        montant_sorties=Sum('valeur_totale', filter=Q(type_mouvement=TypeMouvement.SORTIE)),
    )

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))

    context = {
        **agg,
        'mouvements':       page,
        'total_mouvements': qs.count(),
        'entrepots':        Entrepot.objects.filter(entreprise=entreprise, est_actif=True),
        'utilisateurs':     Utilisateur.objects.filter(entreprise=entreprise, is_active=True),
        'date_debut':       debut,
        'date_fin':         fin,
    }
    return render(request, 'auditeur/mouvements.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# ÉCARTS INVENTAIRE
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@role_required('auditeur', 'super_admin', 'admin_ent')
def ecarts(request):
    entreprise = request.user.entreprise

    qs = LigneInventaire.objects.filter(
        session__entrepot__entreprise=entreprise,
        quantite_comptee__isnull=False,
    ).exclude(
        quantite_comptee=F('quantite_theorique')
    ).select_related(
        'produit', 'produit__categorie',
        'session', 'session__entrepot'
    ).order_by('-session__created_at')

    if session_id := request.GET.get('session'):
        qs = qs.filter(session_id=session_id)
    if sens := request.GET.get('sens'):
        if sens == 'positif':
            qs = qs.filter(quantite_comptee__gt=F('quantite_theorique'))
        elif sens == 'negatif':
            qs = qs.filter(quantite_comptee__lt=F('quantite_theorique'))
    if entrepot_id := request.GET.get('entrepot'):
        qs = qs.filter(session__entrepot_id=entrepot_id)

    def _enrichir(ligne):
        ligne.ecart = ligne.quantite_comptee - ligne.quantite_theorique
        ligne.valeur_ecart = ligne.ecart * ligne.produit.prix_unitaire
        ligne.pct_ecart = (
            ligne.ecart / ligne.quantite_theorique * 100
            if ligne.quantite_theorique else Decimal('0')
        )
        ligne.pct_ecart_abs = abs(ligne.pct_ecart)
        return ligne

    liste = [_enrichir(l) for l in qs]

    valeur_ecarts_abs = sum(abs(l.valeur_ecart) for l in liste)
    pcts = [abs(l.pct_ecart) for l in liste]
    taux_ecart = round(sum(pcts) / len(pcts), 1) if pcts else 0

    if request.GET.get('export') == 'csv':
        rows = []
        for l in liste:
            date_val = l.session.date_fin.strftime('%d/%m/%Y') if l.session.date_fin else ''
            rows.append((
                l.session.entrepot.nom,
                date_val,
                l.produit.nom, l.produit.sku,
                l.quantite_theorique, l.quantite_comptee,
                l.ecart,
                float(l.valeur_ecart),
                f"{float(l.pct_ecart):.1f}%",
            ))
        return _csv(
            f'ecarts_inventaire_{date.today()}.csv',
            ['Entrepôt', 'Session', 'Produit', 'SKU',
             'Théorique', 'Compté', 'Écart', 'Valeur écart (€)', '% écart'],
            rows,
        )

    paginator = Paginator(liste, 50)
    page = paginator.get_page(request.GET.get('page'))

    context = {
        'ecarts':           page,
        'nb_ecarts_total':  len(liste),
        'nb_sessions':      InventaireSession.objects.filter(entrepot__entreprise=entreprise).count(),
        'valeur_ecarts_abs': valeur_ecarts_abs,
        'taux_ecart':       taux_ecart,
        'sessions':         InventaireSession.objects.filter(
                                entrepot__entreprise=entreprise
                            ).order_by('-created_at'),
        'entrepots':        Entrepot.objects.filter(entreprise=entreprise, est_actif=True),
    }
    return render(request, 'auditeur/ecarts.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# VALORISATION (CUMP / FIFO)
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@role_required('auditeur', 'super_admin', 'admin_ent')
def valorisation(request):
    entreprise = request.user.entreprise
    methode = request.GET.get('methode', 'cump')
    categorie_id = request.GET.get('categorie')

    stocks_dict = {
        s['produit']: s['total']
        for s in Stock.objects.filter(
            entrepot__entreprise=entreprise
        ).values('produit').annotate(total=Sum('quantite'))
    }

    produits_qs = Produit.objects.filter(
        entreprise=entreprise, est_actif=True
    ).select_related('categorie')
    if categorie_id:
        produits_qs = produits_qs.filter(categorie_id=categorie_id)

    valorisations = []
    for p in produits_qs:
        qte = stocks_dict.get(p.id, 0)
        if qte <= 0:
            continue

        if methode == 'fifo':
            first_entry = Mouvement.objects.filter(
                produit=p, type_mouvement=TypeMouvement.ENTREE,
                prix_unitaire_snapshot__isnull=False
            ).order_by('date_mouvement').first()
            prix = first_entry.prix_unitaire_snapshot if first_entry else p.prix_unitaire
        else:  # CUMP
            agg = Mouvement.objects.filter(
                produit=p, type_mouvement=TypeMouvement.ENTREE,
                prix_unitaire_snapshot__isnull=False
            ).aggregate(
                total_qte=Sum('quantite'),
                total_val=Sum(
                    ExpressionWrapper(
                        F('quantite') * F('prix_unitaire_snapshot'),
                        output_field=DecimalField()
                    )
                ),
            )
            if agg['total_qte']:
                prix = (agg['total_val'] or Decimal('0')) / agg['total_qte']
            else:
                prix = p.prix_unitaire

        valeur = qte * prix
        valorisations.append({
            'nom':                 p.nom,
            'sku':                 p.sku,
            'categorie__nom':      p.categorie.nom if p.categorie else None,
            'quantite_totale':     qte,
            'prix_unitaire_calcule': prix,
            'valeur_totale':       valeur,
            'pct_total':           Decimal('0'),
            'variation':           Decimal('0'),
        })

    valeur_totale = sum(v['valeur_totale'] for v in valorisations)
    for v in valorisations:
        v['pct_total'] = (
            v['valeur_totale'] / valeur_totale * 100
            if valeur_totale else Decimal('0')
        )

    from collections import defaultdict
    par_cat = defaultdict(Decimal)
    for v in valorisations:
        par_cat[v['categorie__nom'] or 'Autres'] += v['valeur_totale']
    labels_cat = list(par_cat.keys())
    data_cat   = [float(par_cat[k]) for k in labels_cat]

    export = request.GET.get('export')
    if export == 'csv':
        rows = [
            (v['nom'], v['sku'], v['categorie__nom'],
             v['quantite_totale'],
             float(v['prix_unitaire_calcule']),
             float(v['valeur_totale']))
            for v in valorisations
        ]
        return _csv(
            f'valorisation_{methode}_{date.today()}.csv',
            ['Produit', 'SKU', 'Catégorie', 'Quantité',
             f'PU {methode.upper()} (€)', 'Valeur totale (€)'],
            rows,
        )
    if export == 'pdf':
        rows = [
            (v['nom'][:20], v['quantite_totale'],
             f"{float(v['prix_unitaire_calcule']):.2f}€",
             f"{float(v['valeur_totale']):.2f}€")
            for v in valorisations
        ]
        return _pdf(
            f'Valorisation {methode.upper()} — {date.today()}',
            ['Produit', 'Qté', f'PU {methode.upper()}', 'Valeur (€)'],
            rows,
        )

    paginator = Paginator(valorisations, 50)
    page = paginator.get_page(request.GET.get('page'))

    context = {
        'valorisations':       page,
        'valeur_totale':       valeur_totale,
        'nb_produits_valorises': len(valorisations),
        'methode_affichee':    methode.upper(),
        'variation_mois':      Decimal('0'),
        'categories':          Categorie.objects.filter(entreprise=entreprise),
        'labels_cat':          labels_cat,
        'data_cat':            data_cat,
    }
    return render(request, 'auditeur/valorisation.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# LOGS D'AUDIT
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@role_required('auditeur', 'super_admin', 'admin_ent')
def logs(request):
    entreprise = request.user.entreprise
    debut, fin = _get_periode(request)

    qs = AuditLog.objects.filter(
        entreprise=entreprise,
        created_at__date__range=(debut, fin),
    ).select_related('utilisateur').order_by('-created_at')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(description__icontains=q)
            | Q(utilisateur__first_name__icontains=q)
            | Q(utilisateur__last_name__icontains=q)
            | Q(objet_type__icontains=q)
        )
    if action := request.GET.get('action'):
        qs = qs.filter(type_action=action)
    if user_id := request.GET.get('utilisateur'):
        qs = qs.filter(utilisateur_id=user_id)

    if request.GET.get('export') == 'csv':
        rows = []
        for l in qs:
            rows.append((
                l.created_at.strftime('%d/%m/%Y %H:%M:%S'),
                l.utilisateur.get_full_name() if l.utilisateur else '',
                l.get_type_action_display(),
                l.objet_type,
                l.description[:100],
                l.ip_address or '',
            ))
        return _csv(
            f'logs_audit_{debut}_{fin}.csv',
            ['Date/Heure', 'Utilisateur', 'Action', 'Type objet', 'Description', 'Adresse IP'],
            rows,
        )

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))

    # Liste des types d'action (choix du modèle)
    types_action = [
        (t.value, t.label) for t in TypeAction
    ] if hasattr(TypeAction, '__iter__') else []

    context = {
        'logs':           page,
        'total_logs':     qs.count(),
        'utilisateurs':   Utilisateur.objects.filter(entreprise=entreprise, is_active=True),
        'types_action':   types_action,
        'date_debut':     debut,
        'date_fin':       fin,
    }
    return render(request, 'auditeur/logs.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# CONFORMITÉ
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@role_required('auditeur', 'super_admin', 'admin_ent')
def conformite(request):
    entreprise = request.user.entreprise
    debut, fin = _get_periode(request)

    mouvements_qs = Mouvement.objects.filter(
        produit__entreprise=entreprise,
        date_mouvement__date__range=(debut, fin),
    )
    total = mouvements_qs.count()
    avec_ref = mouvements_qs.exclude(reference__isnull=True).exclude(reference__exact='').count()
    taux_conformite = round((avec_ref / total * 100) if total else 100)

    nb_sessions = InventaireSession.objects.filter(entrepot__entreprise=entreprise).count()
    nb_produits = Produit.objects.filter(entreprise=entreprise, est_actif=True).count()

    domaines = [
        {
            'nom':            'Traçabilité mouvements',
            'icon':           'fas fa-arrows-rotate',
            'color':          '#f97316',
            'bg':             '#fff7ed',
            'nb_controles':   total,
            'score':          taux_conformite,
            'derniere_alerte': (
                f"{total - avec_ref} mouvement(s) sans référence document"
                if taux_conformite < 90 else None
            ),
        },
        {
            'nom':            'Inventaires réguliers',
            'icon':           'fas fa-clipboard-list',
            'color':          '#2563eb',
            'bg':             '#eff6ff',
            'nb_controles':   nb_sessions,
            'score':          85,
            'derniere_alerte': None,
        },
        {
            'nom':            'Alertes traitées',
            'icon':           'fas fa-bell',
            'color':          '#059669',
            'bg':             '#ecfdf5',
            'nb_controles':   0,
            'score':          92,
            'derniere_alerte': None,
        },
        {
            'nom':            'Valorisation cohérente',
            'icon':           'fas fa-coins',
            'color':          '#7c3aed',
            'bg':             '#f5f3ff',
            'nb_controles':   nb_produits,
            'score':          98,
            'derniere_alerte': None,
        },
    ]

    anomalies = []
    
    # 1. Mouvements sans référence document
    nb_sans_ref = total - avec_ref
    if nb_sans_ref > 0:
        ratio = nb_sans_ref / total if total else 0
        if ratio > 0.05:
            niveau = 'critique'
        elif ratio > 0.02:
            niveau = 'majeure'
        else:
            niveau = 'mineure'
        anomalies.append({
            'titre': 'Mouvements sans référence document',
            'description': f'{nb_sans_ref} mouvement(s) sur {total} ne possèdent pas de référence (facture, bon de commande, etc.).',
            'niveau': niveau,
            'action': 'Exiger que chaque mouvement soit rattaché à un document justificatif.',
        })

    # 2. Écarts d'inventaire significatifs
    total_ecarts_valeur = Decimal('0')
    lignes_ecarts = LigneInventaire.objects.filter(
        session__entrepot__entreprise=entreprise,
        quantite_comptee__isnull=False,
    ).exclude(quantite_comptee=F('quantite_theorique')).select_related('produit')
    valeur_stock_total = _valeur_stock(entreprise) or Decimal('1')
    for ligne in lignes_ecarts:
        ecart = ligne.quantite_comptee - ligne.quantite_theorique
        valeur_ecart = abs(ecart * ligne.produit.prix_unitaire)
        total_ecarts_valeur += valeur_ecart
    pct_ecarts = (total_ecarts_valeur / valeur_stock_total * 100) if valeur_stock_total else 0
    if pct_ecarts > 0:
        if pct_ecarts > 10:
            niveau = 'critique'
        elif pct_ecarts > 5:
            niveau = 'majeure'
        else:
            niveau = 'mineure'
        anomalies.append({
            'titre': 'Écarts d\'inventaire significatifs',
            'description': f'Les écarts représentent {pct_ecarts:.1f}% de la valeur totale du stock ({total_ecarts_valeur:.2f} FCFA).',
            'niveau': niveau,
            'action': 'Organiser un inventaire complet et analyser les causes des écarts.',
        })

    # 3. Alertes non traitées depuis plus de 7 jours
    alertes_non_lues = Alerte.objects.filter(
        produit__entreprise=entreprise,
        lue=False,
        created_at__lte=timezone.now() - timedelta(days=7)
    ).count()
    if alertes_non_lues > 0:
        if alertes_non_lues > 5:
            niveau = 'critique'
        elif alertes_non_lues > 2:
            niveau = 'majeure'
        else:
            niveau = 'mineure'
        anomalies.append({
            'titre': 'Alertes non traitées',
            'description': f'{alertes_non_lues} alerte(s) restent non acquittées depuis plus de 7 jours.',
            'niveau': niveau,
            'action': 'Traiter rapidement les alertes de stock pour éviter les ruptures.',
        })

    # 4. Stocks négatifs (incohérence)
    stocks_negatifs = Stock.objects.filter(quantite__lt=0, entrepot__entreprise=entreprise).count()
    if stocks_negatifs > 0:
        anomalies.append({
            'titre': 'Stocks négatifs détectés',
            'description': f'{stocks_negatifs} ligne(s) de stock ont une quantité négative.',
            'niveau': 'critique',
            'action': 'Corriger les mouvements ayant créé ces stocks négatifs.',
        })

    nb_critiques = sum(1 for a in anomalies if a['niveau'] == 'critique')
    nb_majeures  = sum(1 for a in anomalies if a['niveau'] == 'majeure')
    nb_mineures  = sum(1 for a in anomalies if a['niveau'] == 'mineure')

    context = {
        'taux_conformite': taux_conformite,
        'nb_critiques':    nb_critiques,
        'nb_majeures':     nb_majeures,
        'nb_mineures':     nb_mineures,
        'domaines_conformite': domaines,
        'anomalies':       anomalies,
    }
    return render(request, 'auditeur/conformite.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@role_required('auditeur', 'super_admin', 'admin_ent')
def exports(request):
    entreprise = request.user.entreprise
    type_export = request.GET.get('type', '')

    try:
        debut = date.fromisoformat(request.GET.get('date_debut', ''))
    except ValueError:
        debut = date.today().replace(day=1)
    try:
        fin = date.fromisoformat(request.GET.get('date_fin', ''))
    except ValueError:
        fin = date.today()

    if type_export == 'mouvements_csv':
        qs = Mouvement.objects.filter(
            produit__entreprise=entreprise,
            date_mouvement__date__range=(debut, fin),
        ).annotate(
            valeur_totale=ExpressionWrapper(
                F('quantite') * F('produit__prix_unitaire'),
                output_field=DecimalField()
            )
        ).select_related('produit', 'entrepot_source', 'entrepot_destination', 'utilisateur')
        rows = []
        for m in qs:
            entrepot = m.entrepot_destination or m.entrepot_source
            rows.append((
                m.date_mouvement.strftime('%d/%m/%Y %H:%M'),
                m.produit.nom, m.produit.sku,
                m.get_type_mouvement_display(),
                m.quantite,
                float(m.valeur_totale or 0),
                entrepot.nom if entrepot else '',
                m.utilisateur.get_full_name() if m.utilisateur else '',
            ))
        return _csv(
            f'mouvements_{debut}_{fin}.csv',
            ['Date', 'Produit', 'SKU', 'Type', 'Quantité',
             'Valeur (€)', 'Entrepôt', 'Opérateur'],
            rows,
        )

    if type_export == 'ecarts_csv':
        qs = LigneInventaire.objects.filter(
            session__entrepot__entreprise=entreprise,
            quantite_comptee__isnull=False,
            session__date_fin__date__range=(debut, fin) if not None else Q(),
        ).exclude(
            quantite_comptee=F('quantite_theorique')
        ).select_related('produit', 'session', 'session__entrepot')
        rows = []
        for l in qs:
            rows.append((
                l.produit.nom, l.produit.sku,
                l.quantite_theorique, l.quantite_comptee,
                l.quantite_comptee - l.quantite_theorique,
                float((l.quantite_comptee - l.quantite_theorique) * l.produit.prix_unitaire),
                l.session.entrepot.nom,
                l.session.date_fin.strftime('%d/%m/%Y') if l.session.date_fin else '',
            ))
        return _csv(
            f'ecarts_{debut}_{fin}.csv',
            ['Produit', 'SKU', 'Théorique', 'Compté',
             'Écart', 'Valeur écart (€)', 'Entrepôt', 'Date validation'],
            rows,
        )

    if type_export == 'logs_csv':
        qs = AuditLog.objects.filter(
            entreprise=entreprise,
            created_at__date__range=(debut, fin),
        ).select_related('utilisateur').order_by('-created_at')
        rows = []
        for l in qs:
            rows.append((
                l.created_at.strftime('%d/%m/%Y %H:%M:%S'),
                l.utilisateur.get_full_name() if l.utilisateur else '',
                l.get_type_action_display(),
                l.objet_type,
                l.description[:100],
                l.ip_address or '',
            ))
        return _csv(
            f'logs_audit_{debut}_{fin}.csv',
            ['Date/Heure', 'Utilisateur', 'Action', 'Type objet', 'Description', 'IP'],
            rows,
        )

    if type_export == 'mouvements_pdf':
        qs = Mouvement.objects.filter(
            produit__entreprise=entreprise,
            date_mouvement__date__range=(debut, fin),
        ).annotate(
            valeur_totale=ExpressionWrapper(
                F('quantite') * F('produit__prix_unitaire'),
                output_field=DecimalField()
            )
        ).select_related('produit')[:500]
        rows = []
        for m in qs:
            rows.append((
                m.date_mouvement.strftime('%d/%m/%Y'),
                m.produit.nom[:20],
                m.get_type_mouvement_display(),
                m.quantite,
                f"{float(m.valeur_totale or 0):.2f}€",
            ))
        return _pdf(
            f'Rapport Mouvements {debut} – {fin}',
            ['Date', 'Produit', 'Type', 'Qté', 'Valeur'],
            rows,
        )

    types_rapports = [
        {
            'nom':         'Mouvements de stock',
            'description': 'Historique détaillé des entrées, sorties et ajustements',
            'code':        'mouvements',
            'icon':        'fas fa-arrows-rotate',
            'color':       '#f97316',
            'bg':          '#fff7ed',
        },
        {
            'nom':         'Écarts inventaire',
            'description': 'Comparaison stock théorique vs quantités comptées',
            'code':        'ecarts',
            'icon':        'fas fa-scale-unbalanced',
            'color':       '#dc2626',
            'bg':          '#fef2f2',
        },
        {
            'nom':         'Logs d\'audit',
            'description': 'Journal complet des actions utilisateurs et modifications',
            'code':        'logs',
            'icon':        'fas fa-list-check',
            'color':       '#2563eb',
            'bg':          '#eff6ff',
        },
    ]
    exports_recents = ExportLog.objects.filter(
        entreprise=entreprise
    ).order_by('-date_creation')[:10]
    exports_list = []
    for exp in exports_recents:
        exports_list.append({
            'type': exp.get_type_export_display(),
            'nom_fichier': exp.nom_fichier,
            'date': exp.date_creation.strftime('%d/%m/%Y %H:%M'),
            'periode': exp.periode,
            'url': exp.url,
            'utilisateur': exp.utilisateur.get_full_name() if exp.utilisateur else '',
        })

    context = {
        'types_rapports': types_rapports,
        'exports_recents': exports_list,
    }
    
    return render(request, 'auditeur/exports.html', context)