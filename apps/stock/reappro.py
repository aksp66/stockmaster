"""
Calcul du réapprovisionnement d'un produit, partagé par les suggestions d'achat, la liste des
prédictions IA et la fiche produit.

Besoin = consommation journalière × (délai de réappro + période de couverture)
         + seuil d'alerte (stock de sécurité) − stock actuel − quantités déjà commandées non reçues.
La quantité suggérée est ce besoin arrondi à l'unité supérieure, au moins égal à la quantité
minimale de commande du produit.
"""
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal

from django.db.models import F, Sum
from django.utils import timezone

COUVERTURE_JOURS = 30   # stock à couvrir après réception (horizon des prédictions IA)
FENETRE_HISTORIQUE = 28  # jours de sorties pour la moyenne de secours, sans prédiction IA


def consommation_journaliere(produit):
    """
    Consommation moyenne par jour et sa provenance :
    dernière prédiction IA encore valable si elle existe, sinon moyenne des sorties des 28 derniers jours.
    Retourne (conso_jour: Decimal, source: 'ia' | 'historique' | None, confiance: int | None, prediction).

    Une PredictionStock (apps/ia/tasks.py) porte la consommation TOTALE prévue entre la date du
    calcul et `date_cible` : on la ramène à un débit journalier.
    """
    from .models import TypeMouvement

    prediction = (produit.predictions.filter(date_cible__gte=timezone.localdate())
                  .order_by('-created_at', '-date_cible').first())
    if prediction:
        jours = max((prediction.date_cible - timezone.localdate(prediction.created_at)).days, 1)
        conso = Decimal(prediction.quantite_prevue) / jours
        confiance = prediction.confiance
        if confiance is not None:
            confiance = round(confiance * 100 if confiance <= 1 else confiance)  # 0-1 ou 0-100 selon la source
        return conso, 'ia', confiance, prediction
    sorties = produit.mouvements.filter(
        type_mouvement__in=[TypeMouvement.SORTIE, TypeMouvement.PERTE],
        date_mouvement__gte=timezone.now() - timedelta(days=FENETRE_HISTORIQUE),
    ).aggregate(total=Sum('quantite'))['total']
    if sorties:
        return sorties / FENETRE_HISTORIQUE, 'historique', None, None
    return Decimal(0), None, None, None


def quantite_en_commande(produit):
    """Quantités commandées (BC envoyés ou partiellement reçus) pas encore reçues."""
    from .models import LigneCommande

    reste = LigneCommande.objects.filter(
        produit=produit, bon_commande__statut__in=['envoye', 'recu_partiel'],
    ).aggregate(reste=Sum(F('quantite_commandee') - F('quantite_recue')))['reste']
    return max(reste or Decimal(0), Decimal(0))


def calculer_reappro(produit, stock_actuel=None):
    """Situation de réapprovisionnement d'un produit (dictionnaire utilisé tel quel par les templates)."""
    stock = Decimal(str(produit.quantite_totale() if stock_actuel is None else stock_actuel))
    conso_jour, source, confiance, prediction = consommation_journaliere(produit)
    en_commande = quantite_en_commande(produit)
    delai = produit.delai_reappro or 0

    if conso_jour > 0:
        jours_rupture = max(int(stock / conso_jour), 0)
        besoin = conso_jour * (delai + COUVERTURE_JOURS) + produit.seuil_alerte - stock - en_commande
    else:
        jours_rupture = 0 if stock <= 0 else None  # pas de consommation : pas de date de rupture
        besoin = produit.seuil_alerte - stock - en_commande

    quantite = Decimal(0)
    if besoin > 0:
        quantite = max(besoin.to_integral_value(rounding=ROUND_CEILING), Decimal(produit.qte_min_commande or 1))

    return {
        'produit': produit,
        'stock_actuel': stock,
        'conso_jour': conso_jour,
        'consommation_prevue': conso_jour * COUVERTURE_JOURS,
        'stock_prevu_j30': stock - conso_jour * COUVERTURE_JOURS,
        'en_commande': en_commande,
        'delai_reappro': delai,
        'jours_rupture': jours_rupture,
        # Urgent : la rupture arrive avant qu'une commande passée aujourd'hui soit livrée (ou sous 7 jours)
        'urgent': jours_rupture is not None and jours_rupture <= max(delai, 7),
        'quantite_suggeree': quantite,
        'source': source,
        'confiance': confiance,
        'prediction': prediction,
    }
