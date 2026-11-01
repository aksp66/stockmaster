# apps/gestionnaire/views.py
# ──────────────────────────────────────────────────────────────────────────────
# Toutes les vues du gestionnaire de stock
# ──────────────────────────────────────────────────────────────────────────────
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import Coalesce
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST, require_GET
import json, csv
from apps.core import csv_safe
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from apps.accounts.decorators import role_required
from apps.stock.models import (
    Produit, Categorie, Entrepot, Emplacement, Stock,
    Mouvement, TypeMouvement, InventaireSession, LigneInventaire,
    Alerte, TypeAlerte, PrioriteAlerte, ScanLog, Fournisseur
)
from apps.core.models import AuditLog, TypeAction
from apps.entreprises.models import ParametresEntreprise
from apps.stock.reappro import calculer_reappro
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

    # Compteurs du bandeau (sur tout le catalogue de l'entreprise, hors filtres)
    totaux = Produit.objects.filter(entreprise=ent).annotate(total=Coalesce(Sum('stocks__quantite'), Decimal(0)))
    nb_rupture = totaux.filter(total__lte=0).count()
    nb_alerte = totaux.filter(total__gt=0, total__lte=F('seuil_alerte')).count()
    filtre_stock = request.GET.get('stock', '')
    if filtre_stock == 'rupture':
        qs = qs.filter(pk__in=totaux.filter(total__lte=0).values('pk'))
    elif filtre_stock == 'alerte':
        qs = qs.filter(pk__in=totaux.filter(total__gt=0, total__lte=F('seuil_alerte')).values('pk'))
    elif filtre_stock == 'ok':
        qs = qs.filter(pk__in=totaux.filter(total__gt=F('seuil_alerte')).values('pk'))

    page = Paginator(qs.order_by('nom'), 20)
    produits = page.get_page(request.GET.get('page', 1))

    context = {
        'produits':    produits,
        'total_produits': page.count,
        'nb_rupture': nb_rupture,
        'nb_alerte': nb_alerte,
        'nb_ok': totaux.count() - nb_rupture - nb_alerte,
        'categories':  Categorie.objects.filter(entreprise=ent),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
        'q': q, 'cat_id': cat_id, 'statut': statut,
    }
    return render(request, 'gestionnaire/produit_list.html', context)


def _decimal_saisi(data, champ, erreurs, libelle, defaut=None, obligatoire=False):
    """Nombre décimal positif ou nul d'un formulaire. Ajoute un message à `erreurs` s'il est invalide."""
    brut = (data.get(champ) or '').strip().replace(',', '.').replace('\u00a0', '').replace(' ', '')
    if not brut:
        if obligatoire:
            erreurs.append(f"{libelle} : valeur obligatoire.")
        return defaut
    try:
        valeur = Decimal(brut)
    except InvalidOperation:
        erreurs.append(f"{libelle} : « {brut} » n'est pas un nombre.")
        return defaut
    if not valeur.is_finite() or valeur < 0 or valeur >= 10 ** 12:
        erreurs.append(f"{libelle} : valeur comprise entre 0 et 999 999 999 999 attendue.")
        return defaut
    return valeur


def _entier_saisi(data, champ, erreurs, libelle, defaut, minimum, maximum):
    brut = (data.get(champ) or '').strip()
    if not brut:
        return defaut
    try:
        valeur = int(brut)
    except ValueError:
        erreurs.append(f"{libelle} : « {brut} » n'est pas un nombre entier.")
        return defaut
    if not minimum <= valeur <= maximum:
        erreurs.append(f"{libelle} : valeur comprise entre {minimum} et {maximum} attendue.")
        return defaut
    return valeur


def _valider_produit(data, ent, produit=None):
    """Champs d'un formulaire produit : (valeurs prêtes à enregistrer, liste d'erreurs)."""
    erreurs = []
    nom = (data.get('nom') or '').strip()
    if not nom:
        erreurs.append("Le nom du produit est obligatoire.")
    elif len(nom) > 200:
        erreurs.append("Le nom du produit est limité à 200 caractères.")
    code_barres = (data.get('code_barres') or '').strip()
    if len(code_barres) > 100:
        erreurs.append("Le code-barres est limité à 100 caractères.")
    elif code_barres and Produit.objects.filter(entreprise=ent, code_barres=code_barres).exclude(
            pk=getattr(produit, 'pk', None)).exists():
        erreurs.append("Ce code-barres est déjà utilisé par un autre produit.")
    unite = data.get('unite', 'unite')
    if unite not in {c for c, _ in Produit._meta.get_field('unite_mesure').choices}:
        erreurs.append("Unité de mesure inconnue.")
    valeurs = {
        'nom': nom,
        'code_barres': code_barres,
        'unite_mesure': unite,
        'seuil_alerte': _decimal_saisi(data, 'seuil_alerte', erreurs, "Seuil d'alerte", Decimal(0)),
        'prix_unitaire': _decimal_saisi(data, 'prix_unitaire', erreurs, "Prix d'achat", Decimal(0)),
        'prix_vente': _decimal_saisi(data, 'prix_vente', erreurs, "Prix de vente", None),
        'description': (data.get('description') or '').strip(),
        'delai_reappro': _entier_saisi(data, 'delai_reappro', erreurs, "Délai de réapprovisionnement", 7, 0, 365),
        'qte_min_commande': _entier_saisi(data, 'qte_min_commande', erreurs, "Quantité minimale de commande", 1, 1, 1_000_000),
    }
    return valeurs, erreurs


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
        valeurs, erreurs = _valider_produit(data, ent, produit)
        sku = (data.get('sku') or '').strip()
        if not produit:
            if not sku:
                erreurs.append("La référence (SKU) est obligatoire.")
            elif len(sku) > 100:
                erreurs.append("La référence (SKU) est limitée à 100 caractères.")
            elif Produit.objects.filter(sku=sku, entreprise=ent).exists():
                erreurs.append("Ce SKU existe déjà.")
        try:
            categorie = categories.filter(pk=data.get('categorie') or None).first()
            fournisseur = fournisseurs.filter(pk=data.get('fournisseur') or None).first()
        except (ValueError, ValidationError):
            categorie = fournisseur = None
            erreurs.append("Catégorie ou fournisseur invalide.")
        if erreurs:
            for erreur in erreurs:
                messages.error(request, erreur)
            return redirect('gestionnaire:produit_edit', pk=produit.pk) if produit else redirect('gestionnaire:produit_ajouter')
        valeurs.update(categorie=categorie, fournisseur_principal=fournisseur)
        if produit:
            # Modification (le SKU n'est pas modifiable)
            for champ, valeur in valeurs.items():
                setattr(produit, champ, valeur)
            produit.est_actif = data.get('est_actif') == 'on'
            produit.save()
            messages.success(request, f"Produit « {produit.nom} » mis à jour.")
        else:
            # Création
            produit = Produit.objects.create(entreprise=ent, sku=sku, est_actif=True, **valeurs)
            # Stock initial
            stock_initial = _prix_saisi(data.get('stock_initial')) or Decimal(0)
            entrepot_id = data.get('entrepot_initial')
            if stock_initial > 0 and entrepot_id:
                entrepot = Entrepot.objects.filter(pk=entrepot_id, entreprise=ent).first()
                if entrepot:
                    with transaction.atomic():
                        mouv = Mouvement.objects.create(
                            type_mouvement=TypeMouvement.ENTREE,
                            produit=produit,
                            quantite=stock_initial,
                            entrepot_destination=entrepot,
                            utilisateur=request.user,
                            reference=f"INIT-{produit.sku}",
                            note="Stock initial lors de la création du produit",
                            prix_unitaire_snapshot=produit.prix_unitaire,
                        )
                        _appliquer_mouvement(mouv)
            _verifier_seuil(produit, Entrepot.objects.filter(pk=entrepot_id or None, entreprise=ent).first())
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
        'seuil_defaut': ParametresEntreprise.pour(ent).seuil_alerte_defaut,
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
    total_actuel = Decimal(str(produit.quantite_totale()))

    # Stock total après chaque mouvement : on remonte l'historique depuis le stock actuel
    historique = list(produit.mouvements.order_by('-date_mouvement', '-created_at')
                      .values_list('pk', 'type_mouvement', 'quantite', 'entrepot_destination_id', 'date_mouvement'))
    stock_apres, courant = {}, total_actuel
    for mpk, type_m, qte, dest, date_m in historique:
        stock_apres[mpk] = courant
        courant -= _variation_stock_total(type_m, qte, dest)

    filtre = request.GET.get('filtre')
    qs = produit.mouvements.select_related('entrepot_source', 'entrepot_destination', 'utilisateur') \
        .order_by('-date_mouvement', '-created_at')
    if filtre == 'entree':
        qs = qs.filter(type_mouvement=TypeMouvement.ENTREE)
    elif filtre == 'sortie':
        qs = qs.filter(type_mouvement__in=[TypeMouvement.SORTIE, TypeMouvement.PERTE])
    page = Paginator(qs, 15)
    mouvements = page.get_page(request.GET.get('page', 1))
    for m in mouvements:
        m.stock_apres = stock_apres.get(m.pk)

    # Graphique : 30 derniers jours (entrées, sorties et stock en fin de journée)
    aujourd_hui = timezone.localdate()
    jours = [aujourd_hui - timedelta(days=i) for i in range(29, -1, -1)]
    entrees = {j: Decimal(0) for j in jours}
    sorties = {j: Decimal(0) for j in jours}
    variation_jour = {j: Decimal(0) for j in jours}
    for _, type_m, qte, dest, date_m in historique:
        jour = timezone.localdate(date_m)
        if jour not in entrees:
            continue
        if type_m == TypeMouvement.ENTREE:
            entrees[jour] += qte
        elif type_m in (TypeMouvement.SORTIE, TypeMouvement.PERTE):
            sorties[jour] += qte
        variation_jour[jour] += _variation_stock_total(type_m, qte, dest)
    stock_fin_jour, courant = [], total_actuel
    for j in reversed(jours):
        stock_fin_jour.append(courant)
        courant -= variation_jour[j]
    stock_fin_jour.reverse()

    depuis_30j = timezone.now() - timedelta(days=30)
    recents = produit.mouvements.filter(date_mouvement__gte=depuis_30j)

    return render(request, 'gestionnaire/produit_detail.html', {
        'produit': produit, 'mouvements': mouvements, 'total_mouvements': page.count,
        'stocks_par_entrepot': produit.stocks.select_related('entrepot', 'emplacement').order_by('entrepot__nom'),
        'alertes': produit.alertes.filter(lue=False)[:5],
        'valeur_stock': produit.valeur_stock_total(),
        'nb_entrees_30j': recents.filter(type_mouvement=TypeMouvement.ENTREE).count(),
        'nb_sorties_30j': recents.filter(type_mouvement__in=[TypeMouvement.SORTIE, TypeMouvement.PERTE]).count(),
        'labels_stock': json.dumps([j.strftime('%d/%m') for j in jours]),
        'data_entrees': json.dumps([float(entrees[j]) for j in jours]),
        'data_sorties': json.dumps([float(sorties[j]) for j in jours]),
        'data_stock': json.dumps([float(v) for v in stock_fin_jour]),
        'fiche_produit': [
            ("Catégorie", produit.categorie.nom if produit.categorie else None, 'fas fa-tag'),
            ("Fournisseur", produit.fournisseur_principal.nom if produit.fournisseur_principal else None, 'fas fa-truck'),
            ("Unité", produit.get_unite_mesure_display(), 'fas fa-ruler'),
            ("Code-barres", produit.code_barres, 'fas fa-barcode'),
            ("Prix d'achat", f"{produit.prix_unitaire:,.2f} FCFA".replace(',', ' '), 'fas fa-coins'),
            ("Prix de vente", f"{produit.prix_vente:,.2f} FCFA".replace(',', ' ') if produit.prix_vente else None, 'fas fa-money-bill'),
            ("Seuil d'alerte", produit.seuil_alerte, 'fas fa-bell'),
            ("Délai de réappro.", f"{produit.delai_reappro} j", 'fas fa-clock'),
            ("Créé le", produit.created_at.strftime('%d/%m/%Y'), 'fas fa-calendar'),
        ],
        'prediction': _resume_prediction(produit, total_actuel),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    })


def _variation_stock_total(type_m, quantite, entrepot_destination_id):
    """Effet d'un mouvement sur le stock total du produit (mêmes règles que _appliquer_mouvement)."""
    if type_m == TypeMouvement.ENTREE:
        return quantite
    if type_m in (TypeMouvement.SORTIE, TypeMouvement.PERTE):
        return -quantite
    if type_m in (TypeMouvement.AJUSTEMENT, TypeMouvement.RETOUR):
        return quantite if entrepot_destination_id else -quantite
    return Decimal(0)  # transfert : total inchangé


def _resume_prediction(produit, stock_actuel):
    """Synthèse des prédictions IA pour la fiche produit (None s'il n'y en a pas). Calcul : apps/stock/reappro.py."""
    reappro = calculer_reappro(produit, stock_actuel)
    if reappro['source'] != 'ia':
        return None
    return {
        'modele_utilise': reappro['prediction'].modele_utilise,
        'score_confiance': reappro['confiance'] or 70,
        'consommation_prevue': reappro['consommation_prevue'],
        'stock_prevu_j30': reappro['stock_prevu_j30'],
        'quantite_a_commander': reappro['quantite_suggeree'],
        'date_calcul': reappro['prediction'].created_at,
    }

@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def produit_import(request):
    """Import CSV de produits (options du formulaire : séparateur et gestion des doublons)."""
    ent = get_entreprise(request)
    if request.method == 'POST' and request.FILES.get('fichier'):
        import io
        if request.FILES['fichier'].size > 5 * 1024 * 1024:
            messages.error(request, "Fichier trop volumineux (5 Mo maximum) : découpez-le en plusieurs fichiers.")
            return redirect('gestionnaire:produit_import')
        try:
            decoded = request.FILES['fichier'].read().decode('utf-8-sig')
        except UnicodeDecodeError:
            messages.error(request, "Le fichier doit être encodé en UTF-8 (CSV UTF-8 dans Excel).")
            return redirect('gestionnaire:produit_import')
        separateur = {'tab': '\t', ';': ';', ',': ','}.get(request.POST.get('separateur'), ',')
        doublon = request.POST.get('doublon', 'ignorer')
        reader = csv.DictReader(io.StringIO(decoded), delimiter=separateur)
        if not reader.fieldnames or not {'sku', 'nom'} <= {c.strip() for c in reader.fieldnames}:
            messages.error(request, "Colonnes « sku » et « nom » introuvables : vérifiez le séparateur choisi.")
            return redirect('gestionnaire:produit_import')

        unites = {code for code, _ in Produit._meta.get_field('unite_mesure').choices}
        categories = {c.nom.lower(): c for c in Categorie.objects.filter(entreprise=ent)}
        fournisseurs = {f.nom.lower(): f for f in Fournisseur.objects.filter(entreprise=ent)}
        crees = maj = ignores = 0
        erreurs = []
        try:
            with transaction.atomic():
                for i, brute in enumerate(reader, 2):  # ligne 1 = en-têtes
                    row = {(k or '').strip(): (v or '').strip() for k, v in brute.items()}
                    if not row.get('sku') or not row.get('nom'):
                        erreurs.append(f"Ligne {i} : sku et nom sont obligatoires")
                        continue
                    unite = row.get('unite_mesure') or 'unite'
                    if unite not in unites:
                        erreurs.append(f"Ligne {i} : unité « {unite} » inconnue")
                        continue
                    try:
                        valeurs = {
                            'nom': row['nom'],
                            'code_barres': row.get('code_barres', ''),
                            'prix_unitaire': Decimal(row.get('prix_unitaire') or 0),
                            'seuil_alerte': Decimal(row.get('seuil_alerte') or 0),
                            'unite_mesure': unite,
                            'description': row.get('description', ''),
                            'categorie': categories.get(row.get('categorie', '').lower()),
                            'fournisseur_principal': fournisseurs.get(row.get('fournisseur_principal', '').lower()),
                        }
                    except ArithmeticError:
                        erreurs.append(f"Ligne {i} : prix ou seuil non numérique")
                        continue
                    existant = Produit.objects.filter(sku=row['sku'], entreprise=ent).first()
                    if existant is None:
                        Produit.objects.create(sku=row['sku'], entreprise=ent, **valeurs)
                        crees += 1
                    elif doublon == 'mettre_a_jour':
                        for champ, valeur in valeurs.items():
                            if valeur not in ('', None):
                                setattr(existant, champ, valeur)
                        existant.save()
                        maj += 1
                    elif doublon == 'erreur':
                        erreurs.append(f"Ligne {i} : le SKU {row['sku']} existe déjà")
                    else:
                        ignores += 1
                if doublon == 'erreur' and erreurs:
                    raise ValueError  # mode « bloquer » : rien n'est importé s'il y a une erreur
        except ValueError:
            messages.error(request, f"Import annulé : {len(erreurs)} erreur(s). " + " | ".join(erreurs[:5]))
            return redirect('gestionnaire:produit_import')
        messages.success(request, f"{crees} produit(s) créé(s), {maj} mis à jour, {ignores} ignoré(s) (déjà existants).")
        if erreurs:
            messages.warning(request, f"{len(erreurs)} ligne(s) rejetée(s) : " + " | ".join(erreurs[:5]))
        return redirect('gestionnaire:produits')
    return render(request, 'gestionnaire/produit_import.html', {
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count()
    })

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
    entrepot_id = request.GET.get('entrepot', '')
    if entrepot_id:
        qs = qs.filter(Q(entrepot_source_id=entrepot_id) | Q(entrepot_destination_id=entrepot_id))
    produit_id = request.GET.get('produit', '')
    if produit_id:
        qs = qs.filter(produit_id=produit_id)

    resume = {r['type_mouvement']: r for r in qs.order_by().values('type_mouvement')
              .annotate(total=Sum('quantite'), nb_ops=Count('id', distinct=True))}
    resume_types = [
        {'label': label, 'couleur': couleur,
         'total': resume.get(code, {}).get('total') or 0, 'nb_ops': resume.get(code, {}).get('nb_ops', 0)}
        for code, label, couleur in [
            ('entree', 'Entrées', 'var(--green)'), ('sortie', 'Sorties', 'var(--red)'),
            ('transfert', 'Transferts', 'var(--blue)'), ('ajustement', 'Ajustements', 'var(--or)'),
        ]
    ]

    page = Paginator(qs.order_by('-date_mouvement'), 25)
    mouvements = page.get_page(request.GET.get('page', 1))
    return render(request, 'gestionnaire/mouvement_list.html', {
        'mouvements': mouvements,
        'total_mouvements': page.count,
        'resume_types': resume_types,
        'entrepots': Entrepot.objects.filter(entreprise=ent),
        'types': TypeMouvement.choices,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
        'q': q, 'type_m': type_m,
    })


def _appliquer_mouvement(mouv):
    """
    Met à jour la table Stock selon le type de mouvement.

    Verrouille la ligne Stock concernée (select_for_update) et lève
    ValidationError si le stock source deviendrait négatif. Doit toujours être
    appelée à l'intérieur du même transaction.atomic() que la création du
    Mouvement, afin que la création soit annulée si la mise à jour échoue
    (sinon on se retrouve avec un Mouvement « fantôme » jamais appliqué).
    """
    def maj_stock(produit, entrepot, emplacement, delta):
        if not entrepot:
            return
        stock, _ = Stock.objects.select_for_update().get_or_create(
            produit=produit, entrepot=entrepot, emplacement=emplacement,
            defaults={'quantite': 0}
        )
        nouvelle_quantite = Decimal(str(stock.quantite)) + Decimal(str(delta))
        if nouvelle_quantite < 0:
            raise ValidationError(
                f"Stock insuffisant pour « {produit.nom} » dans « {entrepot.nom} » "
                f"(disponible : {stock.quantite}, demandé : {abs(delta)})."
            )
        stock.quantite = nouvelle_quantite
        stock.save(update_fields=['quantite', 'updated_at'])

    p, q = mouv.produit, Decimal(str(mouv.quantite))
    with transaction.atomic():
        if mouv.type_mouvement == TypeMouvement.ENTREE:
            maj_stock(p, mouv.entrepot_destination, mouv.emplacement_destination, q)
        elif mouv.type_mouvement in [TypeMouvement.SORTIE, TypeMouvement.PERTE]:
            maj_stock(p, mouv.entrepot_source, mouv.emplacement_source, -q)
        elif mouv.type_mouvement == TypeMouvement.TRANSFERT:
            maj_stock(p, mouv.entrepot_source,      mouv.emplacement_source,      -q)
            maj_stock(p, mouv.entrepot_destination, mouv.emplacement_destination, +q)
        elif mouv.type_mouvement in (TypeMouvement.AJUSTEMENT, TypeMouvement.RETOUR):
            # Le signe dépend de l'entrepôt renseigné : destination = surplus / retour client (+),
            # source = manque / retour fournisseur (-). `quantite` est toujours une magnitude positive.
            if mouv.entrepot_destination:
                maj_stock(p, mouv.entrepot_destination, mouv.emplacement_destination, q)
            elif mouv.entrepot_source:
                maj_stock(p, mouv.entrepot_source, mouv.emplacement_source, -q)


def _verifier_seuil(produit, entrepot):
    """
    À appeler après toute variation du stock d'un produit (mouvement, réception, inventaire) :
    crée une alerte si le stock total est sous le seuil, et clôt les alertes de stock bas
    devenues sans objet (stock remonté).
    """
    total = produit.quantite_totale()
    ouvertes = Alerte.objects.filter(produit=produit, lue=False)
    if total > produit.seuil_alerte:
        ouvertes.filter(type_alerte__in=[TypeAlerte.RUPTURE, TypeAlerte.SEUIL_BAS])             .update(lue=True, date_lecture=timezone.now())
        return
    if total > 0:
        ouvertes.filter(type_alerte=TypeAlerte.RUPTURE).update(lue=True, date_lecture=timezone.now())
    if not entrepot:
        return
    type_a = TypeAlerte.RUPTURE if total <= 0 else TypeAlerte.SEUIL_BAS
    prio   = PrioriteAlerte.CRITIQUE if total <= 0 else PrioriteAlerte.HAUTE
    alerte, creee = Alerte.objects.get_or_create(
        produit=produit, entrepot=entrepot, type_alerte=type_a, lue=False,
        defaults={
            'priorite': prio,
            'message': f"Stock de « {produit.nom} » : {total} {produit.unite_mesure} (seuil : {produit.seuil_alerte})"
        }
    )
    if creee:
        from apps.admin_entreprise.notifications import notifier_alerte
        notifier_alerte(alerte)

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
@role_required('gestionnaire', 'admin_ent', 'magasinier', 'super_admin')
@require_POST
def api_scan(request):
    """API AJAX pour la résolution d'un code-barres."""
    ent  = request.user.entreprise
    try:
        data = json.loads(request.body)
        code = str(data.get('code') or '').strip()
    except (ValueError, AttributeError):
        return JsonResponse({'found': False, 'message': 'Requête invalide'}, status=400)
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
    nb_sessions = sessions.count()
    nb_en_cours = sessions.filter(statut='en_cours').count()
    statut = request.GET.get('statut')
    if statut:
        sessions = sessions.filter(statut=statut)
    return render(request, 'gestionnaire/inventaire_session_list.html', {
        'sessions': sessions,
        'nb_sessions': nb_sessions,
        'nb_en_cours': nb_en_cours,
        'statuts_filter': [('', 'Toutes', 'gy'), ('en_cours', 'En cours', 'or'),
                           ('valide', 'Validées', 'gr'), ('annule', 'Annulées', 're')],
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    })


@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def inventaire_creer(request):
    ent = get_entreprise(request)
    if request.method == 'POST':
        entrepot = get_object_or_404(Entrepot, pk=request.POST.get('entrepot') or None, entreprise=ent)
        note = '\n'.join(t for t in (request.POST.get('nom', '').strip(), request.POST.get('commentaire', '').strip()) if t)
        session  = InventaireSession.objects.create(
            entrepot=entrepot,
            utilisateur_demarrage=request.user,
            note=note,
            masquer_stock=request.POST.get('masquer_stock') == 'on',
            ajustement_auto=request.POST.get('ajustement_auto') == 'on',
        )
        # Pré-remplir les lignes avec le stock théorique actuel (éventuellement limité à une catégorie)
        stocks = Stock.objects.filter(entrepot=entrepot).select_related('produit', 'emplacement')
        categorie_id = request.POST.get('categorie')
        if categorie_id:
            stocks = stocks.filter(produit__categorie_id=categorie_id, produit__categorie__entreprise=ent)
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
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True)
            .annotate(nb_produits=Count('stocks__produit', distinct=True)),
        'categories': Categorie.objects.filter(entreprise=ent).order_by('nom'),
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
                ligne.quantite_comptee = Decimal(val)
            ligne.note = request.POST.get(f'cmt_{ligne.pk}', ligne.note).strip()[:255]
            ligne.save(update_fields=['quantite_comptee', 'note', 'updated_at'])
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
        'ajustement_auto': session.ajustement_auto,
        'masquer_stock': session.masquer_stock,
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'gestionnaire/inventaire_session_detail.html', context)

@login_required
@role_required('gestionnaire', 'admin_ent', 'super_admin')
def inventaire_valider(request, pk):
    ent = get_entreprise(request)
    session = get_object_or_404(InventaireSession, pk=pk, entrepot__entreprise=ent, statut='en_cours')
    if request.method == 'POST':
        try:
            with transaction.atomic():
                session.statut = 'valide'
                session.date_fin = timezone.now()
                session.utilisateur_validation = request.user
                session.save()
                # Appliquer les écarts
                for ligne in session.lignes.filter(quantite_comptee__isnull=False):
                    ecart = ligne.ecart()  # utilise la méthode du modèle
                    if ecart != 0 and session.ajustement_auto:
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
        except ValidationError as e:
            messages.error(request, e.messages[0] if hasattr(e, 'messages') else str(e))
            return redirect('gestionnaire:inventaire_saisie', pk=pk)
        if session.ajustement_auto:
            for ligne in session.lignes.filter(quantite_comptee__isnull=False).select_related('produit'):
                if ligne.ecart() != 0:
                    _verifier_seuil(ligne.produit, session.entrepot)
        AuditLog.log(request, TypeAction.VALIDATION_INVENTAIRE,
                     f"Inventaire validé : {session.entrepot.nom}"
                     + ("" if session.ajustement_auto else " (sans ajustement du stock)"), objet=session)
        if session.ajustement_auto:
            messages.success(request, "Inventaire validé. Les ajustements ont été appliqués.")
        else:
            messages.success(request, "Inventaire validé. Le stock n'a pas été modifié : les écarts restent consultables.")
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
    from decimal import Decimal, InvalidOperation
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
        produit = get_object_or_404(Produit, pk=data.get('produit') or None, entreprise=ent)
        src     = get_object_or_404(Entrepot, pk=data.get('entrepot_source') or None, entreprise=ent)
        dst     = get_object_or_404(Entrepot, pk=data.get('entrepot_destination') or None, entreprise=ent)
        try:
            quantite = Decimal(data.get('quantite') or 0)
        except ArithmeticError:
            quantite = Decimal(0)
        if quantite <= 0 or src == dst:
            messages.error(request, "Indiquez une quantité positive et deux entrepôts différents.")
            return redirect('gestionnaire:transfert')

        try:
            with transaction.atomic():
                mouv = Mouvement.objects.create(
                    type_mouvement=TypeMouvement.TRANSFERT,
                    produit=produit, quantite=quantite,
                    entrepot_source=src, entrepot_destination=dst,
                    utilisateur=request.user, note=data.get('note', ''),
                )
                _appliquer_mouvement(mouv)
        except ValidationError as e:
            messages.error(request, e.messages[0] if hasattr(e, 'messages') else str(e))
            return redirect('gestionnaire:transfert')
        messages.success(request, f"Transfert de {quantite} {produit.unite_mesure} effectué.")
        return redirect('gestionnaire:mouvements')


    context = {
        'produits': Produit.objects.filter(entreprise=ent, est_actif=True),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
    }
    return render(request, 'gestionnaire/transfert.html', context)


# ── RAPPORTS ───────────────────────────────────────────────────────────────────

def export_stock_csv(entreprise):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="stock.csv"'
    response.write('\ufeff')  # BOM pour UTF-8
    writer = csv_safe.writer(response)
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
    writer = csv_safe.writer(response)
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
    writer = csv_safe.writer(response)
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
    writer = csv_safe.writer(response)
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
    writer = csv_safe.writer(response)
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
        AuditLog.log(request, TypeAction.SUPPRESSION_PRODUIT, f"Produit « {produit.nom} » ({produit.sku}) archivé", produit)
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
        'prix_vente': float(p.prix_vente) if p.prix_vente is not None else None,
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
        except (ValueError, ValidationError, Produit.DoesNotExist):
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
        except (ValueError, ValidationError, Produit.DoesNotExist):
            messages.error(request, "Produit invalide.")
            return redirect('gestionnaire:mouvement_form')
        
        type_m = data.get('type_mouvement')
        if type_m not in TypeMouvement.values:
            messages.error(request, "Type de mouvement invalide.")
            return redirect('gestionnaire:mouvement_form')
        try:
            quantite = float(data.get('quantite', 0))
        except ValueError:
            quantite = 0
        if quantite <= 0:
            messages.error(request, "La quantité doit être strictement positive.")
            return redirect('gestionnaire:mouvement_form')

        # Gestion des entrepôts selon le type
        ent_src = None
        ent_dst = None
        if type_m == 'transfert':
            ent_src = Entrepot.objects.filter(pk=data.get('entrepot') or None, entreprise=ent).first()
            ent_dst = Entrepot.objects.filter(pk=data.get('entrepot_destination') or None, entreprise=ent).first()
        elif type_m in ('ajustement', 'retour'):
            # Surplus / retour client = ajout dans l'entrepôt (destination) ;
            # manque / retour fournisseur = retrait (source)
            entrepot_ajuste = Entrepot.objects.filter(pk=data.get('entrepot') or None, entreprise=ent).first()
            if data.get('sens_ajustement') == 'surplus' or data.get('sens_retour') == 'client':
                ent_dst = entrepot_ajuste
            else:
                ent_src = entrepot_ajuste
        elif type_m in ('sortie', 'perte'):
            ent_src = Entrepot.objects.filter(pk=data.get('entrepot') or None, entreprise=ent).first()
        elif type_m == 'entree':
            ent_dst = Entrepot.objects.filter(pk=data.get('entrepot') or None, entreprise=ent).first()

        # Sans entrepôt valide, le mouvement serait enregistré sans aucun effet sur le stock
        if type_m in ('entree', 'sortie', 'perte', 'ajustement', 'retour') and not (ent_src or ent_dst):
            messages.error(request, "Choisissez un entrepôt.")
            return redirect('gestionnaire:mouvement_form')
        if type_m == 'transfert' and (not ent_src or not ent_dst or ent_src == ent_dst):
            messages.error(request, "Un transfert demande deux entrepôts différents (source et destination).")
            return redirect('gestionnaire:mouvement_form')

        try:
            with transaction.atomic():
                mouv = Mouvement.objects.create(
                    type_mouvement=type_m,
                    produit=produit,
                    quantite=quantite,
                    entrepot_source=ent_src,
                    entrepot_destination=ent_dst,
                    utilisateur=request.user,
                    reference=data.get('reference_document', ''),
                    note=data.get('motif', ''),
                    date_mouvement=_date_saisie(data.get('date_mouvement')),
                    prix_unitaire_snapshot=_prix_saisi(data.get('prix_unitaire_achat')) if type_m == 'entree' else None,
                    # Vente ou retour client : prix pratiqué (à défaut, le modèle reprend le prix de vente du produit)
                    prix_vente_snapshot=(_prix_saisi(data.get('prix_vente_unitaire'))
                                         if type_m == 'sortie' or (type_m == 'retour' and ent_dst) else None),
                )
                _appliquer_mouvement(mouv)
        except ValidationError as e:
            messages.error(request, e.messages[0] if hasattr(e, 'messages') else str(e))
            return redirect('gestionnaire:mouvement_form')
        _verifier_seuil(produit, ent_dst or ent_src)
        messages.success(request, "Mouvement enregistré avec succès.")
        return redirect('gestionnaire:mouvements')

    # GET : affichage du formulaire
    context = {
        'types_mouvement': types_mouvement,
        'produits': Produit.objects.filter(entreprise=ent, est_actif=True),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
        'nb_alertes_actives': Alerte.objects.filter(produit__entreprise=ent, lue=False).count(),
        'produit_preselect': produit_initial,
        'now': timezone.localtime(),
    }
    return render(request, 'gestionnaire/mouvement_form.html', context)

def _date_saisie(valeur):
    """Date d'un champ datetime-local ; maintenant si vide ou invalide."""
    from django.utils.dateparse import parse_datetime
    date_m = parse_datetime(valeur or '')
    if date_m is None:
        return timezone.now()
    return timezone.make_aware(date_m) if timezone.is_naive(date_m) else date_m


def _prix_saisi(valeur):
    """Prix saisi (Decimal >= 0) ou None : le modèle reprend alors le prix du produit."""
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        prix = Decimal(str(valeur).strip())
    except (ArithmeticError, ValueError):
        return None
    return prix if prix.is_finite() and 0 <= prix < 10 ** 12 else None


def _prix_vente_json(data):
    """
    Prix de vente optionnel d'une requête JSON : (prix ou None, erreur ou None).
    Absent ou vide : None, le modèle reprend le prix de vente du produit.
    """
    brut = data.get('prix_vente')
    if brut in (None, ''):
        return None, None
    prix = _prix_saisi(brut)
    return (prix, None) if prix is not None else (None, "Prix de vente invalide.")


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