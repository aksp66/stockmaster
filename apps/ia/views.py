

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Avg, Sum, Count, Q

from apps.stock.models import PredictionStock
from apps.ia.models import SuggestionAchat
from apps.stock.models import Produit, Categorie
from apps.ia.tasks import lancer_analyse_manuelle, lancer_toutes_predictions


# ─────────────────────────────────────────────────────────────────────────────
#  DÉCORATEUR : Vérification des rôles autorisés
# ─────────────────────────────────────────────────────────────────────────────

def role_requis(*roles):
    """Décorateur qui vérifie que l'utilisateur a l'un des rôles requis."""
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            role = getattr(request.user, "role", None)
            if role not in roles:
                messages.error(request, "Accès refusé. Rôle insuffisant.")
                return redirect("dashboard")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
#  VUE PRINCIPALE : Tableau de bord IA
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_requis("admin_entreprise", "responsable_achat", "gestionnaire")
def predictions_dashboard(request):
    """
    Tableau de bord principal des prédictions IA.
    Accessible depuis admin_entreprise et responsable_achat.
    """
    # Dernières prédictions (7 jours)
    predictions_recentes = (
        PredictionStock.objects
        .filter(date_prediction__gte=timezone.now().date() - timezone.timedelta(days=7))
        .select_related("produit", "produit__categorie")
        .order_by("-date_prediction", "consommation_prevue")
    )

    # Produits en risque de rupture (stock prévu < seuil)
    produits_risque = (
        PredictionStock.objects
        .filter(
            date_prediction=timezone.now().date(),
            stock_prevu_fin__lte=0,
        )
        .select_related("produit")
        .order_by("stock_prevu_fin")[:20]
    )

    # Suggestions d'achat non validées
    suggestions_en_attente = (
        SuggestionAchat.objects
        .filter(validee=False)
        .select_related("produit", "produit__fournisseur_principal")
        .order_by("-priorite", "date_suggestion")[:50]
    )

    # Statistiques résumées
    stats = {
        "nb_predictions":       PredictionStock.objects.filter(
                                    date_prediction=timezone.now().date()
                                ).count(),
        "nb_risques_rupture":   produits_risque.count(),
        "nb_suggestions":       suggestions_en_attente.count(),
        "confiance_moyenne":    PredictionStock.objects
                                    .filter(date_prediction=timezone.now().date())
                                    .aggregate(moy=Avg("confiance"))["moy"] or 0,
        "derniere_analyse":     PredictionStock.objects
                                    .order_by("-date_prediction")
                                    .values_list("date_prediction", flat=True)
                                    .first(),
    }

    # Données graphique : consommation prévue vs réelle par catégorie
    categories = Categorie.objects.all()
    graphique_data = _preparer_donnees_graphique(categories)

    context = {
        "predictions_recentes":  predictions_recentes[:30],
        "produits_risque":       produits_risque,
        "suggestions":           suggestions_en_attente,
        "stats":                 stats,
        "graphique_data":        json.dumps(graphique_data),
        "page_title":            "Prédictions IA",
    }
    return render(request, "ia/predictions_dashboard.html", context)


# ─────────────────────────────────────────────────────────────────────────────
#  VUE : Lancer une analyse IA
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_requis("admin_entreprise", "responsable_achat")
def lancer_analyse(request):
    """
    Vue pour déclencher manuellement une analyse IA.
    GET  → Formulaire de paramétrage
    POST → Lance la tâche Celery et redirige
    """
    if request.method == "GET":
        produits = Produit.objects.filter(actif=True).select_related("categorie")
        categories = Categorie.objects.all()
        context = {
            "produits":   produits,
            "categories": categories,
            "page_title": "Lancer une analyse IA",
        }
        return render(request, "ia/lancer_analyse.html", context)

    # ── POST : Lancer la tâche ────────────────────────────────────────────────
    modele       = request.POST.get("modele", "prophet")
    horizon      = int(request.POST.get("horizon_jours", 30))
    produit_ids  = request.POST.getlist("produit_ids")  # Vide = tous les produits
    mode         = request.POST.get("mode", "tous")     # "tous" | "selection"

    if mode == "selection" and not produit_ids:
        messages.warning(request, "Veuillez sélectionner au moins un produit.")
        return redirect("ia:lancer_analyse")

    try:
        if mode == "tous":
            # Lance la tâche globale
            task = lancer_toutes_predictions.delay(modele=modele, horizon_jours=horizon)
            messages.success(
                request,
                f"✅ Analyse complète lancée en arrière-plan (tâche #{task.id[:8]}). "
                f"Résultats disponibles dans quelques minutes."
            )
        else:
            # Lance uniquement pour les produits sélectionnés
            ids = [int(pid) for pid in produit_ids]
            task = lancer_analyse_manuelle.delay(produit_ids=ids, modele=modele)
            messages.success(
                request,
                f"✅ Analyse lancée pour {len(ids)} produit(s) (tâche #{task.id[:8]})."
            )

        # Enregistrer l'action dans les logs
        _log_action(request.user, "lancer_analyse_ia", {
            "modele":  modele,
            "horizon": horizon,
            "mode":    mode,
            "nb":      len(produit_ids) if produit_ids else "tous",
        })

    except Exception as e:
        messages.error(request, f"❌ Erreur lors du lancement : {str(e)}")

    return redirect("ia:predictions_dashboard")


# ─────────────────────────────────────────────────────────────────────────────
#  VUE : Statut d'une tâche Celery (AJAX)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def statut_tache(request, task_id: str):
    """
    Retourne le statut d'une tâche Celery en JSON.
    Utilisé par le polling JavaScript de l'interface.
    """
    try:
        from celery.result import AsyncResult
        result = AsyncResult(task_id)

        reponse = {
            "task_id": task_id,
            "statut":  result.status,  # PENDING, STARTED, SUCCESS, FAILURE
            "pret":    result.ready(),
        }

        if result.successful():
            reponse["resultat"] = result.result
        elif result.failed():
            reponse["erreur"] = str(result.result)

        return JsonResponse(reponse)

    except Exception as e:
        return JsonResponse({"erreur": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
#  VUE : Détail d'une prédiction produit
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_requis("admin_entreprise", "responsable_achat", "gestionnaire", "auditeur")
def prediction_detail(request, produit_id: int):
    """Affiche les prédictions détaillées pour un produit."""
    produit = get_object_or_404(Produit, pk=produit_id)

    predictions = (
        PredictionStock.objects
        .filter(produit=produit)
        .order_by("-date_prediction")[:12]
    )

    # Historique de consommation pour le graphique
    from apps.stock.models import MouvementStock
    from django.db.models.functions import TruncMonth

    historique = (
        MouvementStock.objects
        .filter(
            produit=produit,
            type_mouvement__in=["vente", "consommation"],
            date_mouvement__date__gte=timezone.now().date() - timezone.timedelta(days=365),
        )
        .annotate(mois=TruncMonth("date_mouvement"))
        .values("mois")
        .annotate(total=Sum("quantite"))
        .order_by("mois")
    )

    context = {
        "produit":    produit,
        "predictions": predictions,
        "historique":  list(historique),
        "page_title": f"Prédictions — {produit.nom}",
    }
    return render(request, "ia/prediction_detail.html", context)


# ─────────────────────────────────────────────────────────────────────────────
#  VUE : Valider une suggestion d'achat
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_requis("responsable_achat")
@require_POST
def valider_suggestion(request, suggestion_id: int):
    """Marque une suggestion d'achat comme validée et crée un bon de commande."""
    suggestion = get_object_or_404(SuggestionAchat, pk=suggestion_id)

    try:
        # Créer un bon de commande automatiquement
        from apps.stock.models import BonCommande, LigneBonCommande
        from apps.stock.views import _generer_reference_bc

        bc = BonCommande.objects.create(
            reference=_generer_reference_bc(),
            fournisseur=suggestion.produit.fournisseur_principal,
            statut="brouillon",
            date_commande=timezone.now(),
            utilisateur=request.user,
            commentaire=f"Généré automatiquement depuis suggestion IA #{suggestion.pk}",
        )
        LigneBonCommande.objects.create(
            bon_commande=bc,
            produit=suggestion.produit,
            quantite_commandee=suggestion.quantite_recommandee,
            prix_unitaire=suggestion.produit.prix_achat,
            montant_total=suggestion.produit.prix_achat * suggestion.quantite_recommandee,
        )

        # Marquer la suggestion comme validée
        suggestion.validee = True
        suggestion.validee_par = request.user
        suggestion.date_validation = timezone.now()
        suggestion.bon_commande = bc
        suggestion.save()

        messages.success(
            request,
            f"✅ Suggestion validée — Bon de commande {bc.reference} créé."
        )

    except Exception as e:
        messages.error(request, f"❌ Erreur : {str(e)}")

    return redirect("ia:predictions_dashboard")


# ─────────────────────────────────────────────────────────────────────────────
#  API JSON : Données pour les graphiques (Chart.js)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def api_graphique_predictions(request):
    """
    Endpoint JSON pour les graphiques Chart.js du tableau de bord IA.
    Retourne : prédictions des 7 prochains jours par catégorie.
    """
    categories = Categorie.objects.all()
    data = _preparer_donnees_graphique(categories)
    return JsonResponse(data)


# ─────────────────────────────────────────────────────────────────────────────
#  FONCTIONS UTILITAIRES PRIVÉES
# ─────────────────────────────────────────────────────────────────────────────

def _preparer_donnees_graphique(categories) -> dict:
    """Prépare les données de graphique par catégorie."""
    labels = []
    data_consommation = []
    data_risques      = []

    for cat in categories:
        labels.append(cat.nom)

        # Consommation prévue totale pour cette catégorie
        conso = (
            PredictionStock.objects
            .filter(
                produit__categorie=cat,
                date_prediction=timezone.now().date(),
            )
            .aggregate(total=Sum("consommation_prevue"))["total"] or 0
        )

        # Nombre de produits en risque de rupture
        risques = (
            PredictionStock.objects
            .filter(
                produit__categorie=cat,
                date_prediction=timezone.now().date(),
                stock_prevu_fin__lte=0,
            )
            .count()
        )

        data_consommation.append(round(float(conso), 1))
        data_risques.append(risques)

    return {
        "labels":            labels,
        "consommation":      data_consommation,
        "risques_rupture":   data_risques,
    }


def _log_action(utilisateur, action: str, details: dict):
    """Enregistre une action dans les logs d'audit."""
    try:
        from apps.auditeur.models import LogAudit
        LogAudit.objects.create(
            utilisateur=utilisateur,
            action=action,
            details=json.dumps(details),
            date=timezone.now(),
        )
    except Exception:
        pass  # Le logging ne doit pas faire échouer l'action principale
