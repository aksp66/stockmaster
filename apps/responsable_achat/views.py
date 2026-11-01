from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from apps.accounts.decorators import role_required
from apps.gestionnaire.views import _appliquer_mouvement, _verifier_seuil
from apps.stock.models import (
    Fournisseur, BonCommande, LigneCommande, StatutBonCommande,
    Produit, Entrepot, Mouvement, TypeMouvement, Alerte
)
from apps.stock.models import PredictionStock, Categorie, Mouvement, TypeMouvement
from .models import UserPreferences
import csv
from apps.core import csv_safe
import io
from xml.sax.saxutils import escape
from datetime import timedelta, date
from decimal import Decimal, InvalidOperation
from django.core.paginator import Paginator
from django.db.models import Sum, Q, F, FloatField, Avg, Count
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.db.models import OuterRef, Subquery
from apps.core.models import AuditLog, ExportLog, TypeAction
from apps.stock.reappro import calculer_reappro

def _entreprise(request):
    return request.user.entreprise

# ---------- Dashboard ----------
@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def dashboard(request):
    ent = _entreprise(request)
    bons = BonCommande.objects.filter(entreprise=ent).select_related('fournisseur')
    en_attente = bons.filter(statut__in=['envoye', 'recu_partiel'])
    montant_ligne = F('bons_commande__lignes__quantite_commandee') * F('bons_commande__lignes__prix_unitaire_ht')
    top_fournisseurs = (
        Fournisseur.objects.filter(entreprise=ent, est_actif=True)
        .exclude(bons_commande__statut=StatutBonCommande.ANNULE)
        .annotate(nb_commandes=Count('bons_commande', distinct=True), total=Sum(montant_ligne))
        .filter(nb_commandes__gt=0)
        .order_by('-total')[:5]
    )
    suggestions = _calculer_suggestions(ent)
    context = {
        'today': timezone.now(),
        'derniers_bc': bons.order_by('-date_commande', '-created_at')[:6],
        'bc_en_attente_reception': en_attente.order_by('date_livraison_prevue')[:5],
        'nb_bc_en_attente': en_attente.count(),
        'nb_bc_total': bons.count(),
        'montant_total_bc': LigneCommande.objects.filter(bon_commande__entreprise=ent)
            .exclude(bon_commande__statut=StatutBonCommande.ANNULE)
            .aggregate(t=Sum(F('quantite_commandee') * F('prix_unitaire_ht')))['t'] or 0,
        'nb_fournisseurs': Fournisseur.objects.filter(entreprise=ent, est_actif=True).count(),
        'top_fournisseurs': top_fournisseurs,
        'suggestions_ia': suggestions[:5],
        'nb_suggestions': len(suggestions),
    }
    return render(request, 'responsable_achat/dashboard.html', context)

# ---------- Fournisseurs ----------
def _entier(valeur, defaut, minimum=0, maximum=3650):
    try:
        return min(max(int(valeur), minimum), maximum)
    except (TypeError, ValueError):
        return defaut


def _remise(valeur):
    try:
        remise = Decimal(str(valeur or 0).replace(',', '.'))
    except InvalidOperation:
        return Decimal(0)
    return min(max(remise, Decimal(0)), Decimal(100)) if remise.is_finite() else Decimal(0)


def _champs_fournisseur(d):
    """Champs Fournisseur depuis le POST (accepte les noms du formulaire HTML et ceux du modèle)."""
    delai = _entier(d.get('delai_livraison') or d.get('delai_moyen_jours'), 7)
    return {
        'code': (d.get('code') or '').strip()[:30],
        'site_web': (d.get('site_web') or '').strip()[:200],
        'code_postal': (d.get('code_postal') or '').strip()[:20],
        'ville': (d.get('ville') or '').strip()[:100],
        'delai_paiement': _entier(d.get('delai_paiement'), 30),
        'devise': d.get('devise') if d.get('devise') in ('XOF', 'EUR', 'USD') else 'XOF',
        'remise': _remise(d.get('remise')),
        'contact': d.get('contact_nom', d.get('contact', '')),
        'email': d.get('email', ''),
        'telephone': d.get('telephone', ''),
        'adresse': d.get('adresse', ''),
        'pays': d.get('pays', ''),
        'delai_moyen_jours': delai,
        'notes': d.get('description', d.get('notes', '')),
        'est_actif': d.get('actif', '1') != '0',
    }

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def fournisseur_list(request):
    ent = _entreprise(request)
    qs = Fournisseur.objects.filter(entreprise=ent).annotate(
        nb_commandes=Count('bons_commande', distinct=True),
    )
    q = request.GET.get('q')
    if q:
        qs = qs.filter(nom__icontains=q)
    statut = request.GET.get('statut')
    if statut == 'actif':
        qs = qs.filter(est_actif=True)
    elif statut == 'inactif':
        qs = qs.filter(est_actif=False)
    paginator = Paginator(qs.order_by('nom'), 20)
    fournisseurs = paginator.get_page(request.GET.get('page', 1))
    # Montant total commandé (hors annulés) pour les fournisseurs de la page
    montants = dict(
        LigneCommande.objects.filter(bon_commande__fournisseur__in=list(fournisseurs))
        .exclude(bon_commande__statut=StatutBonCommande.ANNULE)
        .values_list('bon_commande__fournisseur')
        .annotate(total=Sum(F('quantite_commandee') * F('prix_unitaire_ht')))
    )
    for f in fournisseurs:
        f.montant_total = montants.get(f.pk, 0)
    return render(request, 'responsable_achat/fournisseur_list.html', {
        'fournisseurs': fournisseurs,
        'q': q or '',
    })

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def fournisseur_detail(request, pk):
    ent = _entreprise(request)
    four = get_object_or_404(Fournisseur, pk=pk, entreprise=ent)
    bons = four.bons_commande.filter(entreprise=ent).order_by('-date_commande')
    montant_total = (
        LigneCommande.objects.filter(bon_commande__in=bons)
        .exclude(bon_commande__statut=StatutBonCommande.ANNULE)
        .aggregate(total=Sum(F('quantite_commandee') * F('prix_unitaire_ht')))['total'] or 0
    )
    return render(request, 'responsable_achat/fournisseur_detail.html', {
        'fournisseur': four,
        'derniers_bc': bons[:10],
        'nb_commandes': bons.count(),
        'montant_total': montant_total,
        'produits': Produit.objects.filter(entreprise=ent, fournisseur_principal=four, est_actif=True),
    })

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def fournisseur_create(request):
    if request.method == 'POST':
        d = request.POST
        nom = (d.get('nom') or '').strip()[:200]
        if not nom:
            messages.error(request, "Le nom du fournisseur est obligatoire.")
            return render(request, 'responsable_achat/fournisseur_form.html', {'fournisseur': None})
        Fournisseur.objects.create(
            entreprise=_entreprise(request),
            nom=nom,
            **_champs_fournisseur(d),
        )
        messages.success(request, "Fournisseur créé.")
        return redirect('responsable_achat:fournisseur_list')
    return render(request, 'responsable_achat/fournisseur_form.html', {'fournisseur': None})

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def fournisseur_edit(request, pk):
    ent = _entreprise(request)
    four = get_object_or_404(Fournisseur, pk=pk, entreprise=ent)
    if request.method == 'POST':
        d = request.POST
        nom = (d.get('nom') or '').strip()[:200]
        if not nom:
            messages.error(request, "Le nom du fournisseur est obligatoire.")
            return redirect('responsable_achat:fournisseur_edit', pk=pk)
        four.nom = nom
        for champ, valeur in _champs_fournisseur(d).items():
            setattr(four, champ, valeur)
        four.save()
        messages.success(request, "Fournisseur mis à jour.")
        return redirect('responsable_achat:fournisseur_list')
    # Statistiques affichées dans le panneau latéral du formulaire
    four.nb_commandes = four.bons_commande.count()
    four.montant_total = (
        LigneCommande.objects.filter(bon_commande__fournisseur=four)
        .exclude(bon_commande__statut=StatutBonCommande.ANNULE)
        .aggregate(total=Sum(F('quantite_commandee') * F('prix_unitaire_ht')))['total'] or 0
    )
    return render(request, 'responsable_achat/fournisseur_form.html', {'fournisseur': four})

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def fournisseur_delete(request, pk):
    ent = _entreprise(request)
    four = get_object_or_404(Fournisseur, pk=pk, entreprise=ent)
    if request.method == 'POST':
        four.est_actif = False
        four.save()
        AuditLog.log(request, TypeAction.SUPPRESSION_FOURN, f"Fournisseur « {four.nom} » désactivé", four)
        messages.success(request, "Fournisseur désactivé.")
        return redirect('responsable_achat:fournisseur_list')
    # La confirmation se fait dans la modale de la fiche fournisseur
    return redirect('responsable_achat:fournisseur_edit', pk=pk)

# ---------- Bons de commande ----------
def _lignes_depuis_post(post):
    """
    Extrait les lignes de commande du formulaire : `lignes[N][produit]`, `lignes[N][quantite]`,
    `lignes[N][prix_unitaire]`, `lignes[N][remise]` (%). Accepte aussi l'ancien format à listes
    parallèles `produit_id` / `quantite` / `prix_unitaire`. Retourne [(produit_id, qte, prix_net)].
    """
    lignes = {}
    for cle, valeur in post.items():
        if cle.startswith('lignes[') and cle.endswith(']'):
            idx, _, champ = cle[len('lignes['):-1].partition('][')
            lignes.setdefault(idx, {})[champ] = valeur
    brutes = list(lignes.values()) or [
        {'produit': pid, 'quantite': q, 'prix_unitaire': pu}
        for pid, q, pu in zip(post.getlist('produit_id'), post.getlist('quantite'), post.getlist('prix_unitaire'))
    ]
    resultat = []
    for l in brutes:
        try:
            qte = Decimal(l.get('quantite') or 0)
            prix = Decimal(l.get('prix_unitaire') or 0)
            remise = Decimal(l.get('remise') or 0)
        except InvalidOperation:
            continue
        if l.get('produit') and qte > 0 and prix >= 0:
            remise = min(max(remise, Decimal(0)), Decimal(100)) if remise.is_finite() else Decimal(0)
            prix_net = (prix * (100 - remise) / 100).quantize(Decimal('0.01'))
            resultat.append((l['produit'], qte, prix_net, remise.quantize(Decimal('0.01'))))
    return resultat


def _ligne_depuis_suggestion(request, ent):
    """Ligne pré-remplie quand on arrive depuis une suggestion d'achat (?produit=<id>&qte=<quantité>)."""
    try:
        produit = Produit.objects.filter(pk=request.GET.get('produit') or None, entreprise=ent).first()
        quantite = Decimal(request.GET.get('qte') or 0)
    except (ValidationError, InvalidOperation):
        return []
    if not produit or quantite <= 0:
        return []
    return [{'produit_id': produit.pk, 'quantite_commandee': quantite, 'prix_unitaire_ht': produit.prix_unitaire,
             'montant_ht': quantite * produit.prix_unitaire}]


def _enregistrer_lignes(bc, post, ent):
    for pid, qte, prix, remise in _lignes_depuis_post(post):
        try:
            prod = Produit.objects.filter(pk=pid, entreprise=ent).first()
        except (ValueError, ValidationError):
            continue
        if prod:
            LigneCommande.objects.create(bon_commande=bc, produit=prod, quantite_commandee=qte,
                                         prix_unitaire_ht=prix, remise=remise)

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_list(request):
    ent = _entreprise(request)
    tous = BonCommande.objects.filter(entreprise=ent)
    qs = tous.select_related('fournisseur', 'utilisateur_createur')
    q = request.GET.get('q')
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(fournisseur__nom__icontains=q))
    statut = request.GET.get('statut')
    if statut:
        qs = qs.filter(statut=statut)
    fournisseur_id = request.GET.get('fournisseur')
    if fournisseur_id:
        qs = qs.filter(fournisseur_id=fournisseur_id)
    qs = qs.order_by('-date_commande', '-created_at')

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="bons_commande.csv"'
        writer = csv_safe.writer(response)
        writer.writerow(['Numéro', 'Fournisseur', 'Date commande', 'Statut', 'Total HT', 'Livraison prévue'])
        for bc in qs:
            writer.writerow([bc.numero, bc.fournisseur.nom, bc.date_commande, bc.get_statut_display(),
                             bc.total_ht(), bc.date_livraison_prevue or ''])
        return response

    compte = dict(tous.values_list('statut').annotate(n=Count('id')))
    resume_statuts = [
        {'label': label, 'count': compte.get(code, 0), 'color': color, 'border': border}
        for code, label, color, border in [
            ('brouillon',    'Brouillons',          '#6b7280',       '#e5e7eb'),
            ('envoye',       'Envoyés',             'var(--blue)',   '#bfdbfe'),
            ('recu_partiel', 'Réception partielle', 'var(--yellow)', '#fde68a'),
            ('recu_complet', 'Reçus',               'var(--green)',  '#a7f3d0'),
            ('cloture',      'Clôturés',            '#6b7280',       '#e5e7eb'),
        ]
    ]
    paginator = Paginator(qs, 20)
    bons = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'responsable_achat/boncommande_list.html', {
        'bons_commande': bons,
        'statuts': StatutBonCommande.choices,
        'statut_sel': statut,
        'fournisseurs': Fournisseur.objects.filter(entreprise=ent),
        'resume_statuts': resume_statuts,
    })

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_create(request):
    ent = _entreprise(request)
    if request.method == 'POST':
        d = request.POST
        four = get_object_or_404(Fournisseur, pk=d.get('fournisseur') or None, entreprise=ent)
        entrepot_dst = Entrepot.objects.filter(pk=d.get('entrepot_destination') or None, entreprise=ent).first()
        bc = BonCommande.objects.create(
            entreprise=ent,
            fournisseur=four,
            utilisateur_createur=request.user,
            date_livraison_prevue=d.get('date_livraison_prevue') or None,
            note=d.get('commentaire', d.get('note', '')),
            entrepot_destination=entrepot_dst,
        )
        _enregistrer_lignes(bc, d, ent)
        messages.success(request, f"Bon de commande {bc.numero} créé.")
        if d.get('action') == 'envoyer':
            _changer_statut(request, bc, StatutBonCommande.ENVOYE)
        return redirect('responsable_achat:boncommande_detail', pk=bc.pk)
    context = {
        'fournisseurs': Fournisseur.objects.filter(entreprise=ent, est_actif=True),
        'produits': Produit.objects.filter(entreprise=ent, est_actif=True),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'lignes': _ligne_depuis_suggestion(request, ent),
    }
    return render(request, 'responsable_achat/boncommande_form.html', context)

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_edit(request, pk):
    ent = _entreprise(request)
    bc = get_object_or_404(BonCommande, pk=pk, entreprise=ent)
    if bc.statut != 'brouillon':
        messages.error(request, "Seul un brouillon peut être modifié.")
        return redirect('responsable_achat:boncommande_detail', pk=pk)
    if request.method == 'POST':
        d = request.POST
        bc.fournisseur = get_object_or_404(Fournisseur, pk=d.get('fournisseur') or None, entreprise=ent)
        bc.date_livraison_prevue = d.get('date_livraison_prevue') or None
        bc.note = d.get('commentaire', d.get('note', ''))
        bc.entrepot_destination = Entrepot.objects.filter(pk=d.get('entrepot_destination') or None, entreprise=ent).first()
        with transaction.atomic():
            bc.save()
            # Supprimer les anciennes lignes et recréer
            bc.lignes.all().delete()
            _enregistrer_lignes(bc, d, ent)
        messages.success(request, "Bon de commande modifié.")
        if d.get('action') == 'envoyer':
            _changer_statut(request, bc, StatutBonCommande.ENVOYE)
        return redirect('responsable_achat:boncommande_detail', pk=pk)
    context = {
        'bc': bc,
        'lignes': bc.lignes.select_related('produit'),
        'fournisseurs': Fournisseur.objects.filter(entreprise=ent, est_actif=True),
        'produits': Produit.objects.filter(entreprise=ent, est_actif=True),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
    }
    return render(request, 'responsable_achat/boncommande_form.html', context)

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_detail(request, pk):
    ent = _entreprise(request)
    bc = get_object_or_404(BonCommande, pk=pk, entreprise=ent)
    receptions = Mouvement.objects.filter(
        reference=f"BC-{bc.numero}", produit__entreprise=ent, type_mouvement=TypeMouvement.ENTREE,
    ).select_related('produit', 'entrepot_destination', 'utilisateur').order_by('-date_mouvement')
    return render(request, 'responsable_achat/boncommande_detail.html', {'bc': bc, 'receptions': receptions})

# Transitions autorisées du workflow BC (statut actuel -> statuts cibles)
TRANSITIONS_BC = {
    'brouillon': ['envoye', 'annule'],
    'envoye': ['recu_partiel', 'recu_complet', 'annule'],
    'recu_partiel': ['recu_complet', 'cloture'],
    'recu_complet': ['cloture'],
}


def _changer_statut(request, bc, statut):
    """Applique une transition de statut si le workflow l'autorise. Retourne True si appliquée."""
    if statut not in TRANSITIONS_BC.get(bc.statut, []):
        messages.error(request, "Transition de statut non autorisée.")
        return False
    if statut == 'envoye' and not bc.lignes.exists():
        messages.error(request, "Impossible d'envoyer un bon de commande sans ligne.")
        return False
    ancien = bc.statut
    bc.statut = statut
    if statut == 'envoye':
        bc.date_envoi = timezone.now()
    if statut in ['recu_complet', 'cloture']:
        bc.utilisateur_validation = request.user
        bc.date_livraison_effective = bc.date_livraison_effective or timezone.now().date()
    bc.save()
    type_action = {'envoye': TypeAction.VALIDATION_BC, 'cloture': TypeAction.CLOTURE_BC, 'annule': TypeAction.ANNULATION_BC,
                   'recu_complet': TypeAction.RECEPTION_BC, 'recu_partiel': TypeAction.RECEPTION_BC}.get(statut, TypeAction.AUTRE)
    AuditLog.log(request, type_action, f"Bon de commande {bc.numero} : {ancien} → {statut}", bc, {'statut': ancien}, {'statut': statut})
    messages.success(request, f"Statut mis à jour : {bc.get_statut_display()}")
    return True


@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
@require_POST
def boncommande_changer_statut(request, pk, statut):
    ent = _entreprise(request)
    bc = get_object_or_404(BonCommande, pk=pk, entreprise=ent)
    _changer_statut(request, bc, statut)
    return redirect('responsable_achat:boncommande_detail', pk=pk)


def _action_statut(statut):
    """Fabrique une vue POST qui fait passer un BC au statut donné."""
    @login_required
    @role_required('responsable_achat', 'admin_ent', 'super_admin')
    @require_POST
    def vue(request, pk):
        bc = get_object_or_404(BonCommande, pk=pk, entreprise=_entreprise(request))
        _changer_statut(request, bc, statut)
        return redirect('responsable_achat:boncommande_detail', pk=pk)
    return vue


boncommande_envoyer = _action_statut(StatutBonCommande.ENVOYE)
boncommande_cloturer = _action_statut(StatutBonCommande.CLOTURE)
boncommande_annuler = _action_statut(StatutBonCommande.ANNULE)


def _montant(valeur):
    return f"{valeur:,.2f}".replace(',', ' ')


@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_pdf(request, pk):
    """Bon de commande imprimable (PDF A4) à transmettre au fournisseur."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    ent = _entreprise(request)
    bc = get_object_or_404(
        BonCommande.objects.select_related('fournisseur', 'entrepot_destination', 'utilisateur_createur'),
        pk=pk, entreprise=ent,
    )
    four = bc.fournisseur
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"BC-{bc.numero}", author=ent.nom)
    st = getSampleStyleSheet()
    elements = [
        Paragraph(f"<b>{escape(ent.nom)}</b>", st['Title']),
        Paragraph(f"Bon de commande <b>BC-{bc.numero}</b> — {bc.get_statut_display()}", st['Heading2']),
        Spacer(1, 4 * mm),
        Table([
            ['Fournisseur', four.nom, 'Date de commande', bc.date_commande.strftime('%d/%m/%Y')],
            ['Contact', four.contact or '—', 'Livraison prévue',
             bc.date_livraison_prevue.strftime('%d/%m/%Y') if bc.date_livraison_prevue else '—'],
            ['Email', four.email or '—', 'Entrepôt de réception',
             bc.entrepot_destination.nom if bc.entrepot_destination else '—'],
            ['Téléphone', four.telephone or '—', 'Émis par',
             bc.utilisateur_createur.get_full_name() if bc.utilisateur_createur else '—'],
        ], colWidths=[28 * mm, 60 * mm, 38 * mm, 48 * mm], style=TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
            ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])),
        Spacer(1, 6 * mm),
    ]
    lignes = [['Produit', 'SKU', 'Qté', 'Prix unit. HT', 'Total HT']]
    for l in bc.lignes.select_related('produit'):
        lignes.append([
            Paragraph(escape(l.produit.nom), st['BodyText']), l.produit.sku,
            f"{l.quantite_commandee:g}", _montant(l.prix_unitaire_ht), _montant(l.montant_ht()),
        ])
    lignes.append(['', '', '', 'Total HT', f"{_montant(bc.total_ht())} FCFA"])
    elements.append(Table(lignes, colWidths=[70 * mm, 30 * mm, 18 * mm, 28 * mm, 28 * mm], repeatRows=1,
                          style=TableStyle([
                              ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f97316')),
                              ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                              ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                              ('FONTSIZE', (0, 0), (-1, -1), 9),
                              ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
                              ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                              ('GRID', (0, 0), (-1, -2), 0.25, colors.HexColor('#e5e7eb')),
                              ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
                          ])))
    if bc.note:
        elements += [Spacer(1, 6 * mm), Paragraph(f"<b>Note :</b> {escape(bc.note)}", st['BodyText'])]
    doc.build(elements)
    buf.seek(0)
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="BC-{bc.numero}.pdf"'
    return response

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_reception(request, pk):
    ent = _entreprise(request)
    bc = get_object_or_404(BonCommande, pk=pk, entreprise=ent, statut__in=['envoye', 'recu_partiel'])
    entrepots = Entrepot.objects.filter(entreprise=ent, est_actif=True)
    if request.method == 'POST':
        entrepot = entrepots.filter(pk=request.POST.get('entrepot') or None).first() or bc.entrepot_destination
        if entrepot is None:
            messages.error(request, "Choisissez l'entrepôt de réception.")
            return redirect('responsable_achat:boncommande_reception', pk=pk)
        reference_bl = request.POST.get('reference_bl', '').strip()
        try:
            with transaction.atomic():
                for ligne in bc.lignes.all():
                    try:
                        recu = Decimal(request.POST.get(f'recu_{ligne.pk}') or 0)
                    except InvalidOperation:
                        recu = Decimal(0)
                    nouveau = min(recu, ligne.quantite_restante())
                    if nouveau > 0:
                        ligne.quantite_recue += nouveau
                        ligne.save()
                        # Créer le mouvement d'entrée ET l'appliquer au stock réel
                        mouv = Mouvement.objects.create(
                            type_mouvement=TypeMouvement.ENTREE,
                            produit=ligne.produit,
                            quantite=nouveau,
                            entrepot_destination=entrepot,
                            utilisateur=request.user,
                            reference=f"BC-{bc.numero}",
                            note=f"BL {reference_bl}" if reference_bl else "",
                            prix_unitaire_snapshot=ligne.prix_unitaire_ht,
                        )
                        _appliquer_mouvement(mouv)
                toutes_recues = all(l.quantite_recue >= l.quantite_commandee for l in bc.lignes.all())
                bc.statut = StatutBonCommande.RECU_COMPLET if toutes_recues else StatutBonCommande.RECU_PARTIEL
                if toutes_recues:
                    bc.date_livraison_effective = timezone.now().date()
                    bc.utilisateur_validation = request.user
                bc.save()
        except ValidationError as e:
            messages.error(request, e.messages[0] if hasattr(e, 'messages') else str(e))
            return redirect('responsable_achat:boncommande_reception', pk=pk)
        # Le stock a augmenté : clôt les alertes de rupture / seuil bas devenues sans objet
        for ligne in bc.lignes.select_related('produit'):
            _verifier_seuil(ligne.produit, entrepot)
        messages.success(request, "Réception enregistrée.")
        return redirect('responsable_achat:boncommande_detail', pk=pk)
    return render(request, 'responsable_achat/boncommande_reception.html', {'bc': bc, 'entrepots': entrepots})

# ---------- Paramètres ----------
@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def settings_view(request):
    ent = _entreprise(request)
    prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Notifications
        notif_settings = {
            'relance_commande': request.POST.get('relance_commande') == 'on',
            'alerte_rupture': request.POST.get('alerte_rupture') == 'on',
            'rappel_delai_fournisseur': request.POST.get('rappel_delai_fournisseur') == 'on',
            'budget_depasse': request.POST.get('budget_depasse') == 'on',
        }
        prefs.notifications = notif_settings
        prefs.devise_defaut = request.POST.get('devise_defaut', 'EUR')
        entrepot_id = request.POST.get('entrepot_defaut')
        if entrepot_id:
            prefs.entrepot_defaut = Entrepot.objects.filter(pk=entrepot_id, entreprise=ent).first()
        else:
            prefs.entrepot_defaut = None
        try:
            prefs.seuil_alerte_jours = max(1, min(int(request.POST.get('seuil_alerte_jours') or 7), 90))
            budget = request.POST.get('budget_mensuel')
            prefs.budget_mensuel = Decimal(budget) if budget else None
        except (ValueError, InvalidOperation):
            messages.error(request, "Délai d'alerte ou budget invalide.")
            return redirect('responsable_achat:settings')
        prefs.save()
        messages.success(request, "Paramètres enregistrés.")
        return redirect('responsable_achat:settings')
    
    # Préparer la liste des notifications pour le template
    notif_labels = [
        ("Relance automatique des commandes en retard", "relance_commande"),
        ("Alerte lorsqu'un produit est proche de la rupture", "alerte_rupture"),
        ("Rappel des délais fournisseurs dépassés", "rappel_delai_fournisseur"),
        ("Alerte si le budget mensuel est dépassé", "budget_depasse"),
    ]
    notif_settings = [(label, name, prefs.notifications.get(name, False)) for label, name in notif_labels]
    
    context = {
        'prefs': prefs,
        'notif_settings': notif_settings,
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'responsable_achat/settings.html', context)

# ---------- Exports ----------
@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def exports_view(request):
    ent = _entreprise(request)
    export_type = request.GET.get('type')
    
    if export_type == 'bc_csv':
        date_debut = request.GET.get('date_debut')
        date_fin = request.GET.get('date_fin')
        statut = request.GET.get('statut')
        qs = BonCommande.objects.filter(entreprise=ent)
        if date_debut:
            qs = qs.filter(date_commande__gte=date_debut)
        if date_fin:
            qs = qs.filter(date_commande__lte=date_fin)
        if statut:
            qs = qs.filter(statut=statut)
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="bons_commande.csv"'
        writer = csv_safe.writer(response)
        writer.writerow(['Numéro', 'Fournisseur', 'Date commande', 'Statut', 'Total HT', 'Date livraison prévue', 'Entrepôt destination'])
        for bc in qs:
            writer.writerow([bc.numero, bc.fournisseur.nom, bc.date_commande, bc.get_statut_display(), bc.total_ht(), bc.date_livraison_prevue, bc.entrepot_destination.nom if bc.entrepot_destination else ''])
        
        ExportLog.objects.create(
            utilisateur=request.user,
            entreprise=ent,
            type_export='bc_csv',
            nom_fichier=f"bons_commande_{date_debut}_{date_fin}.csv",
            periode=f"{date_debut} - {date_fin}" if date_debut and date_fin else "Toute période",
            url="",  # si vous stockez le fichier, mettez l'URL
        )
        return response
    
    elif export_type == 'fournisseurs_csv':
        qs = Fournisseur.objects.filter(entreprise=ent, est_actif=True)
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="fournisseurs.csv"'
        writer = csv_safe.writer(response)
        writer.writerow(['Nom', 'Contact', 'Email', 'Téléphone', 'Pays', 'Délai moyen (jours)'])
        for f in qs:
            writer.writerow([f.nom, f.contact, f.email, f.telephone, f.pays, f.delai_moyen_jours])
        
        ExportLog.objects.create(
            utilisateur=request.user,
            entreprise=ent,
            type_export='fournisseurs_csv',
            nom_fichier="fournisseurs.csv",
            periode="Toute période",
            url="",  # si vous stockez le fichier, mettez l'URL
        )
        return response
    
    elif export_type == 'predictions_csv':
        predictions = PredictionStock.objects.filter(produit__entreprise=ent).select_related('produit')
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="predictions_ia.csv"'
        writer = csv_safe.writer(response)
        writer.writerow(['Produit', 'SKU', 'Date cible', 'Quantité prévue', 'Borne inf', 'Borne sup', 'Confiance', 'Modèle'])
        for p in predictions:
            writer.writerow([p.produit.nom, p.produit.sku, p.date_cible, p.quantite_prevue, p.borne_inferieure, p.borne_superieure, p.confiance, p.modele_utilise])
        
        ExportLog.objects.create(
            utilisateur=request.user,
            entreprise=ent,
            type_export='predictions_csv',
            nom_fichier="predictions_ia.csv",
            periode="Toute période",
            url="",  # si vous stockez le fichier, mettez l'URL
        )
        return response
    
    elif export_type == 'suggestions_csv':
        # Calcul des suggestions (même logique que suggestions_list)
        suggestions = _calculer_suggestions(ent)
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="suggestions_achat.csv"'
        writer = csv_safe.writer(response)
        writer.writerow(['Produit', 'Stock actuel', 'Jours avant rupture', 'Quantité suggérée', 'Urgence'])
        for s in suggestions:
            writer.writerow([s['produit'].nom, s['stock_actuel'], '' if s['jours_rupture'] is None else s['jours_rupture'], s['quantite_suggeree'], 'Urgent' if s['urgent'] else 'À planifier'])
        
        ExportLog.objects.create(
            utilisateur=request.user,
            entreprise=ent,
            type_export='suggestions_csv',
            nom_fichier="suggestions_achat.csv",
            periode="Toute période",
            url="",  # si vous stockez le fichier, mettez l'URL
        )
        return response
    
    
    exports_recents = ExportLog.objects.filter(entreprise=ent).select_related('utilisateur')[:10]  
    context = {
        'exports_recents': exports_recents,
        'entrepots': Entrepot.objects.filter(entreprise=ent),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'responsable_achat/exports.html', context)

# ---------- Prédictions IA ----------
@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def predictions_list(request):
    ent = _entreprise(request)
    
    # Traitement du lancement manuel de l'analyse
    if request.method == 'POST' and request.POST.get('action') == 'lancer':
        from apps.ia.tasks import lancer_toutes_predictions
        lancer_toutes_predictions.delay()
        messages.success(request, "Analyse IA déclenchée. Les résultats seront disponibles sous peu.")
        return redirect('responsable_achat:predictions_list')
    
    # Sous-requête : pour chaque produit, la prédiction la plus récente (par date_cible)
    latest_per_product = PredictionStock.objects.filter(
        produit=OuterRef('produit'),
        produit__entreprise=ent
    ).order_by('-created_at', '-date_cible').values('id')[:1]
    
    predictions = PredictionStock.objects.filter(
        id__in=Subquery(latest_per_product)
    ).select_related('produit').order_by('produit__nom')
    
    # Filtres (à appliquer après la sous-requête)
    q = request.GET.get('q')
    cat_id = request.GET.get('categorie')
    confiance = request.GET.get('confiance')
    risque = request.GET.get('risque')
    
    # Calcul des métriques pour chaque produit
    produits_data = []
    for pred in predictions:
        produit = pred.produit
        # Consommation prévue, rupture et quantité à commander : calcul commun (apps/stock/reappro.py)
        reappro = calculer_reappro(produit)
        conso_prevue = reappro['consommation_prevue']
        stock_prevu_j30 = reappro['stock_prevu_j30']
        # Bornes = totaux sur la période de la prédiction : demi-largeur ramenée aux 30 jours affichés
        horizon = max((pred.date_cible - timezone.localdate(pred.created_at)).days, 1)
        intervalle_confiance = ((pred.borne_superieure - pred.borne_inferieure) / 2 * 30 / horizon
                                if pred.borne_superieure is not None and pred.borne_inferieure is not None else 0)
        # Rupture affichée seulement si elle survient dans l'horizon des prédictions
        jours_avant_rupture = reappro['jours_rupture'] if stock_prevu_j30 < 0 else None
        qte_a_commander = reappro['quantite_suggeree']
        
        score_confiance = reappro['confiance'] if reappro['confiance'] is not None else 70
        
        # Filtres
        if q and q.lower() not in produit.nom.lower() and q.lower() not in produit.sku.lower():
            continue
        if cat_id and str(produit.categorie_id) != cat_id:
            continue
        if confiance == 'haute' and score_confiance < 80:
            continue
        if confiance == 'moyenne' and (score_confiance < 60 or score_confiance >= 80):
            continue
        if confiance == 'faible' and score_confiance >= 60:
            continue
        if risque == 'rupture' and jours_avant_rupture is None:
            continue
        if risque == 'excedent' and stock_prevu_j30 > produit.seuil_alerte * 2:
            continue
        
        produits_data.append({
            'produit': produit,
            'consommation_prevue': conso_prevue,
            'intervalle_confiance': intervalle_confiance,
            'stock_prevu_j30': stock_prevu_j30,
            'jours_avant_rupture': jours_avant_rupture,
            'quantite_a_commander': qte_a_commander,
            'modele_utilise': pred.modele_utilise,
            'score_confiance': score_confiance,
        })
    
    # Pagination
    paginator = Paginator(produits_data, 20)
    page = request.GET.get('page')
    produits_page = paginator.get_page(page)
    
    # Statistiques globales
    nb_predictions = len(produits_data)
    nb_risque_rupture = sum(1 for p in produits_data if p['jours_avant_rupture'] is not None and p['jours_avant_rupture'] <= 7)
    nb_excedents = sum(1 for p in produits_data if p['stock_prevu_j30'] > p['produit'].seuil_alerte * 2)
    confiance_moyenne = int(sum(p['score_confiance'] for p in produits_data) / nb_predictions) if nb_predictions else 0
    derniere_maj = PredictionStock.objects.filter(produit__entreprise=ent).order_by('-created_at').first()
    
    context = {
        'predictions': produits_page,
        'nb_predictions': nb_predictions,
        'nb_risque_rupture': nb_risque_rupture,
        'nb_excedents': nb_excedents,
        'confiance_moyenne': confiance_moyenne,
        'derniere_maj': derniere_maj.created_at if derniere_maj else None,
        'categories': Categorie.objects.filter(entreprise=ent),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'responsable_achat/predictions_list.html', context)

# ---------- Suggestions d'achat ----------
def _calculer_suggestions(entreprise):
    """
    Produits actifs à commander (quantité suggérée > 0), les plus proches de la rupture d'abord.
    Calcul : apps/stock/reappro.py (consommation prévue, délai de réappro, commandes en cours).
    """
    suggestions = [
        r for r in (calculer_reappro(p) for p in Produit.objects.filter(entreprise=entreprise, est_actif=True))
        if r['quantite_suggeree'] > 0
    ]
    suggestions.sort(key=lambda s: (s['jours_rupture'] is None, s['jours_rupture'] or 0))
    return suggestions

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def suggestions_list(request):
    ent = _entreprise(request)
    
    if request.method == 'POST' and request.POST.get('action') == 'relancer':
        from apps.ia.tasks import analyser_entreprise_immediate
        analyser_entreprise_immediate.delay(str(ent.id))
        messages.success(request, "Analyse IA relancée. Les suggestions seront actualisées sous peu.")
        return redirect('responsable_achat:suggestions_list')
    
    suggestions = _calculer_suggestions(ent)
    suggestions_urgentes = [s for s in suggestions if s['urgent']]
    suggestions_planifier = [s for s in suggestions if not s['urgent']]
    
    montant_estime = sum((Decimal(s['quantite_suggeree']) * s['produit'].prix_unitaire for s in suggestions), Decimal(0))
    
    context = {
        'suggestions_urgentes': suggestions_urgentes,
        'suggestions_planifier': suggestions_planifier,
        'nb_urgentes': len(suggestions_urgentes),
        'nb_a_planifier': len(suggestions_planifier),
        'nb_suggestions': len(suggestions),
        'montant_estime': montant_estime,
        'derniere_maj': timezone.now(),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'responsable_achat/suggestions_list.html', context)