from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.accounts.decorators import role_required
from apps.gestionnaire.views import _appliquer_mouvement
from apps.stock.models import (
    Fournisseur, BonCommande, LigneCommande, StatutBonCommande,
    Produit, Entrepot, Mouvement, TypeMouvement, Alerte
)
from apps.stock.models import PredictionStock, Categorie, Mouvement, TypeMouvement
from .models import UserPreferences
import csv
from datetime import timedelta, date
from django.core.paginator import Paginator
from django.db.models import Sum, Q, F, FloatField, Avg
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.db.models import OuterRef, Subquery
from apps.core.models import ExportLog

def _entreprise(request):
    return request.user.entreprise

# ---------- Dashboard ----------
@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def dashboard(request):
    ent = _entreprise(request)
    commandes_en_cours = BonCommande.objects.filter(
        entreprise=ent, statut__in=['envoye', 'recu_partiel']
    ).select_related('fournisseur')[:5]
    suggestions = []  # à remplacer par de vraies suggestions IA
    fournisseurs = Fournisseur.objects.filter(entreprise=ent, est_actif=True)
    context = {
        'commandes_en_cours': commandes_en_cours,
        'nb_commandes': BonCommande.objects.filter(entreprise=ent, statut__in=['envoye','recu_partiel']).count(),
        'nb_fournisseurs': fournisseurs.count(),
        'suggestions': suggestions,
        'fournisseurs_actifs': fournisseurs[:5],
        'total_bc': BonCommande.objects.filter(entreprise=ent).count(),
    }
    return render(request, 'responsable_achat/dashboard.html', context)

# ---------- Fournisseurs ----------
@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def fournisseur_list(request):
    ent = _entreprise(request)
    qs = Fournisseur.objects.filter(entreprise=ent)
    q = request.GET.get('q')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs.order_by('nom'), 20)
    fournisseurs = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'responsable_achat/fournisseur_list.html', {
        'fournisseurs': fournisseurs,
        'q': q or '',
    })

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def fournisseur_create(request):
    if request.method == 'POST':
        d = request.POST
        Fournisseur.objects.create(
            entreprise=_entreprise(request),
            nom=d['nom'],
            contact=d.get('contact', ''),
            email=d.get('email', ''),
            telephone=d.get('telephone', ''),
            adresse=d.get('adresse', ''),
            pays=d.get('pays', ''),
            delai_moyen_jours=int(d.get('delai_moyen_jours', 7)),
            notes=d.get('notes', ''),
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
        four.nom = d['nom']
        four.contact = d.get('contact', '')
        four.email = d.get('email', '')
        four.telephone = d.get('telephone', '')
        four.adresse = d.get('adresse', '')
        four.pays = d.get('pays', '')
        four.delai_moyen_jours = int(d.get('delai_moyen_jours', 7))
        four.notes = d.get('notes', '')
        four.save()
        messages.success(request, "Fournisseur mis à jour.")
        return redirect('responsable_achat:fournisseur_list')
    return render(request, 'responsable_achat/fournisseur_form.html', {'fournisseur': four})

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def fournisseur_delete(request, pk):
    ent = _entreprise(request)
    four = get_object_or_404(Fournisseur, pk=pk, entreprise=ent)
    if request.method == 'POST':
        four.est_actif = False
        four.save()
        messages.success(request, "Fournisseur désactivé.")
        return redirect('responsable_achat:fournisseur_list')
    return render(request, 'responsable_achat/fournisseur_confirm_delete.html', {'fournisseur': four})

# ---------- Bons de commande ----------
@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_list(request):
    ent = _entreprise(request)
    qs = BonCommande.objects.filter(entreprise=ent).select_related('fournisseur', 'utilisateur_createur')
    statut = request.GET.get('statut')
    if statut:
        qs = qs.filter(statut=statut)
    paginator = Paginator(qs.order_by('-date_commande'), 20)
    bons = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'responsable_achat/boncommande_list.html', {
        'bons': bons,
        'statuts': StatutBonCommande.choices,
        'statut_sel': statut,
    })

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_create(request):
    ent = _entreprise(request)
    if request.method == 'POST':
        d = request.POST
        four = get_object_or_404(Fournisseur, pk=d.get('fournisseur'), entreprise=ent)
        entrepot_dst = Entrepot.objects.filter(pk=d.get('entrepot_destination'), entreprise=ent).first()
        bc = BonCommande.objects.create(
            entreprise=ent,
            fournisseur=four,
            utilisateur_createur=request.user,
            date_livraison_prevue=d.get('date_livraison_prevue') or None,
            note=d.get('note', ''),
            entrepot_destination=entrepot_dst,
        )
        # Lignes
        produit_ids = d.getlist('produit_id')
        quantites = d.getlist('quantite')
        prix_unitaires = d.getlist('prix_unitaire')
        for pid, qte, pu in zip(produit_ids, quantites, prix_unitaires):
            if pid and qte and float(qte) > 0:
                prod = Produit.objects.filter(pk=pid, entreprise=ent).first()
                if prod:
                    LigneCommande.objects.create(
                        bon_commande=bc,
                        produit=prod,
                        quantite_commandee=float(qte),
                        prix_unitaire_ht=float(pu or 0)
                    )
        messages.success(request, f"Bon de commande {bc.numero} créé.")
        return redirect('responsable_achat:boncommande_detail', pk=bc.pk)
    context = {
        'fournisseurs': Fournisseur.objects.filter(entreprise=ent, est_actif=True),
        'produits': Produit.objects.filter(entreprise=ent, est_actif=True),
        'entrepots': Entrepot.objects.filter(entreprise=ent, est_actif=True),
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
        bc.fournisseur = get_object_or_404(Fournisseur, pk=d.get('fournisseur'), entreprise=ent)
        bc.date_livraison_prevue = d.get('date_livraison_prevue') or None
        bc.note = d.get('note', '')
        bc.entrepot_destination = Entrepot.objects.filter(pk=d.get('entrepot_destination'), entreprise=ent).first()
        bc.save()
        # Supprimer les anciennes lignes et recréer
        bc.lignes.all().delete()
        produit_ids = d.getlist('produit_id')
        quantites = d.getlist('quantite')
        prix_unitaires = d.getlist('prix_unitaire')
        for pid, qte, pu in zip(produit_ids, quantites, prix_unitaires):
            if pid and qte and float(qte) > 0:
                prod = Produit.objects.filter(pk=pid, entreprise=ent).first()
                if prod:
                    LigneCommande.objects.create(
                        bon_commande=bc,
                        produit=prod,
                        quantite_commandee=float(qte),
                        prix_unitaire_ht=float(pu or 0)
                    )
        messages.success(request, "Bon de commande modifié.")
        return redirect('responsable_achat:boncommande_detail', pk=pk)
    context = {
        'bc': bc,
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
    return render(request, 'responsable_achat/boncommande_detail.html', {'bc': bc})

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_changer_statut(request, pk, statut):
    ent = _entreprise(request)
    bc = get_object_or_404(BonCommande, pk=pk, entreprise=ent)
    transitions = {
        'brouillon': ['envoye', 'annule'],
        'envoye': ['recu_partiel', 'recu_complet', 'annule'],
        'recu_partiel': ['recu_complet', 'cloture'],
        'recu_complet': ['cloture'],
    }
    if statut in transitions.get(bc.statut, []):
        bc.statut = statut
        if statut in ['recu_complet', 'cloture']:
            bc.utilisateur_validation = request.user
            bc.date_livraison_effective = timezone.now().date()
        bc.save()
        messages.success(request, f"Statut mis à jour : {bc.get_statut_display()}")
    else:
        messages.error(request, "Transition de statut non autorisée.")
    return redirect('responsable_achat:boncommande_detail', pk=pk)

@login_required
@role_required('responsable_achat', 'admin_ent', 'super_admin')
def boncommande_reception(request, pk):
    ent = _entreprise(request)
    bc = get_object_or_404(BonCommande, pk=pk, entreprise=ent, statut__in=['envoye', 'recu_partiel'])
    if request.method == 'POST':
        try:
            with transaction.atomic():
                for ligne in bc.lignes.all():
                    recu = request.POST.get(f'recu_{ligne.pk}')
                    if recu and float(recu) > 0:
                        nouveau = min(float(recu), float(ligne.quantite_commandee) - float(ligne.quantite_recue))
                        if nouveau > 0:
                            ligne.quantite_recue = float(ligne.quantite_recue) + nouveau
                            ligne.save()
                            # Créer le mouvement d'entrée ET l'appliquer au stock réel
                            if bc.entrepot_destination:
                                mouv = Mouvement.objects.create(
                                    type_mouvement=TypeMouvement.ENTREE,
                                    produit=ligne.produit,
                                    quantite=nouveau,
                                    entrepot_destination=bc.entrepot_destination,
                                    utilisateur=request.user,
                                    reference=f"BC-{bc.numero}",
                                    prix_unitaire_snapshot=ligne.prix_unitaire_ht,
                                )
                                _appliquer_mouvement(mouv)
                toutes_recues = all(l.quantite_recue >= l.quantite_commandee for l in bc.lignes.all())
                bc.statut = StatutBonCommande.RECU_COMPLET if toutes_recues else StatutBonCommande.RECU_PARTIEL
                bc.save()
        except ValidationError as e:
            messages.error(request, e.messages[0] if hasattr(e, 'messages') else str(e))
            return redirect('responsable_achat:boncommande_reception', pk=pk)
        messages.success(request, "Réception enregistrée.")
        return redirect('responsable_achat:boncommande_detail', pk=pk)
    return render(request, 'responsable_achat/boncommande_reception.html', {'bc': bc})

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
        prefs.seuil_alerte_jours = int(request.POST.get('seuil_alerte_jours', 7))
        prefs.budget_mensuel = request.POST.get('budget_mensuel') or None
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
        writer = csv.writer(response)
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
        writer = csv.writer(response)
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
        writer = csv.writer(response)
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
        writer = csv.writer(response)
        writer.writerow(['Produit', 'Stock actuel', 'Jours avant rupture', 'Quantité suggérée', 'Urgence'])
        for s in suggestions:
            writer.writerow([s['produit'].nom, s['stock_actuel'], s['jours_rupture'], s['quantite_suggeree'], 'Urgent' if s['jours_rupture'] <= 7 else 'À planifier'])
        
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
    ).order_by('-date_cible').values('id')[:1]
    
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
        stock_actuel = produit.quantite_totale()
        
        # Consommation prévue sur 30 jours (somme des prédictions futures pour ce produit)
        futures = PredictionStock.objects.filter(
            produit=produit,
            date_cible__gte=timezone.now().date()
        ).order_by('date_cible')[:30]
        conso_prevue = sum(p.quantite_prevue for p in futures)
        intervalle_confiance = (pred.borne_superieure - pred.borne_inferieure) if pred.borne_superieure else 0
        
        stock_prevu_j30 = stock_actuel - conso_prevue
        if stock_prevu_j30 < 0 and conso_prevue > 0:
            jours_avant_rupture = int(stock_actuel / (conso_prevue / 30))
        else:
            jours_avant_rupture = None
        
        # Quantité à commander (recommandation)
        qte_a_commander = 0
        if stock_prevu_j30 < 0:
            qte_a_commander = abs(stock_prevu_j30) + produit.seuil_alerte
        elif stock_prevu_j30 < produit.seuil_alerte:
            qte_a_commander = produit.seuil_alerte - stock_prevu_j30
        
        score_confiance = pred.confiance if pred.confiance else 70
        
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
    """Retourne une liste de suggestions (dict) basée sur les prédictions et les seuils."""
    suggestions = []
    produits = Produit.objects.filter(entreprise=entreprise, est_actif=True)
    for produit in produits:
        stock_actuel = produit.quantite_totale()
        # Récupérer la prédiction la plus récente pour ce produit
        pred = PredictionStock.objects.filter(produit=produit, date_cible__gte=date.today()).order_by('date_cible').first()
        if not pred:
            # Si pas de prédiction, utiliser une estimation basée sur l'historique des sorties
            # (simplifié : on ignore)
            continue
        # Consommation prévue sur 30 jours
        futures = PredictionStock.objects.filter(produit=produit, date_cible__gte=date.today()).order_by('date_cible')[:30]
        conso_prevue = sum(p.quantite_prevue for p in futures)
        if conso_prevue <= 0:
            continue
        jours_rupture = int(stock_actuel / (conso_prevue / 30)) if stock_actuel > 0 else 0
        if jours_rupture <= 30:  # Seuil pour suggérer
            quantite_suggeree = max(produit.seuil_alerte * 2 - stock_actuel, 0) if jours_rupture <= 7 else max(produit.seuil_alerte - stock_actuel, 0)
            if quantite_suggeree > 0:
                suggestions.append({
                    'produit': produit,
                    'stock_actuel': stock_actuel,
                    'jours_rupture': jours_rupture,
                    'quantite_suggeree': quantite_suggeree,
                    'confiance': pred.confiance if pred.confiance else 70,
                })
    # Trier par urgence (jours_rupture croissant)
    suggestions.sort(key=lambda x: x['jours_rupture'])
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
    suggestions_urgentes = [s for s in suggestions if s['jours_rupture'] <= 7]
    suggestions_planifier = [s for s in suggestions if 7 < s['jours_rupture'] <= 30]
    
    montant_estime = sum(s['quantite_suggeree'] * float(s['produit'].prix_unitaire) for s in suggestions)
    
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