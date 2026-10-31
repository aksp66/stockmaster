"""
Valorisation du stock en inventaire permanent, à partir du journal des mouvements.

CUMP permanent : les mouvements d'un produit sont rejoués dans l'ordre chronologique.
- Entrée (achat) : au prix d'achat enregistré (snapshot), ce qui recalcule le coût moyen.
- Retour client, ajustement positif : réintégrés au coût moyen du moment.
- Sortie (vente), perte, retour fournisseur, ajustement négatif : sortent au coût moyen du moment.
- Transfert : sans effet sur la valeur (le stock change seulement d'entrepôt).
Le stock réel sans historique de mouvements (saisi hors application) est traité comme un stock
d'ouverture valorisé au prix du produit, pour que les quantités rejouées égalent toujours le stock réel.

Les valeurs de début, de fin et de chaque flux d'une période se réconcilient donc par construction :
fin = début + entrées + retours clients + ajustements(+) − sorties − pertes − retours fournisseurs − ajustements(−).
"""
import hashlib
from collections import defaultdict
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Count, Max, Sum

from apps.stock.models import Mouvement, Produit, Stock, TypeMouvement

# Flux d'une période (clé -> sens)
FLUX = {
    'entrees': +1,
    'retours_clients': +1,
    'ajustements_plus': +1,
    'sorties': -1,
    'pertes': -1,
    'retours_fournisseurs': -1,
    'ajustements_moins': -1,
}
ZERO = Decimal(0)


def _flux(type_m, vers_destination):
    """Classe un mouvement dans un flux (None pour un transfert ou un mouvement sans effet)."""
    if type_m == TypeMouvement.ENTREE:
        return 'entrees'
    if type_m == TypeMouvement.SORTIE:
        return 'sorties'
    if type_m == TypeMouvement.PERTE:
        return 'pertes'
    if type_m == TypeMouvement.RETOUR:
        return 'retours_clients' if vers_destination else 'retours_fournisseurs'
    if type_m == TypeMouvement.AJUSTEMENT:
        return 'ajustements_plus' if vers_destination else 'ajustements_moins'
    return None


def _a_un_effet(type_m, source_id, destination_id):
    if type_m in (TypeMouvement.ENTREE,):
        return bool(destination_id)
    if type_m in (TypeMouvement.SORTIE, TypeMouvement.PERTE):
        return bool(source_id)
    if type_m in (TypeMouvement.RETOUR, TypeMouvement.AJUSTEMENT):
        return bool(destination_id or source_id)
    return False


def rejouer(produit, mouvements, stock_reel, debut=None, fin=None):
    """
    Rejoue les mouvements d'un produit (tuples triés par date :
    (type, quantite, prix_snapshot, source_id, destination_id, date)).
    Retourne un dictionnaire : qte/valeur au début et à la fin de la période, valeur de chaque flux,
    quantités et chiffre d'affaires des ventes, CUMP final.
    """
    prix_defaut = produit.prix_unitaire or ZERO
    effectifs = [m for m in mouvements if _a_un_effet(m[0], m[3], m[4])]
    variation_totale = sum((m[1] if FLUX[_flux(m[0], bool(m[4]))] > 0 else -m[1]) for m in effectifs)
    ouverture = Decimal(stock_reel) - variation_totale

    qte, valeur = ouverture, max(ouverture, ZERO) * prix_defaut
    res = {cle: ZERO for cle in FLUX}
    res.update(qte_ventes=ZERO, qte_retours_clients=ZERO, ca=ZERO, qte_debut=None, valeur_debut=None)

    def cump():
        return valeur / qte if qte > 0 else prix_defaut

    for type_m, quantite, prix_snapshot, source_id, destination_id, date_m in effectifs:
        jour = date_m.date()
        if fin is not None and jour > fin:
            break
        if debut is not None and jour >= debut and res['qte_debut'] is None:
            res['qte_debut'], res['valeur_debut'] = qte, valeur
        flux = _flux(type_m, bool(destination_id))
        if flux == 'entrees':
            montant = quantite * (prix_snapshot if prix_snapshot is not None else prix_defaut)
        else:
            montant = quantite * cump()
        if FLUX[flux] > 0:
            qte, valeur = qte + quantite, valeur + montant
        else:
            qte, valeur = qte - quantite, valeur - montant
            if qte <= 0:
                valeur = ZERO  # plus de stock : plus de valeur résiduelle
        if debut is None or jour >= debut:
            res[flux] += montant
            if flux == 'sorties':
                res['qte_ventes'] += quantite
                if produit.prix_vente:
                    res['ca'] += quantite * produit.prix_vente
            elif flux == 'retours_clients':
                res['qte_retours_clients'] += quantite
                if produit.prix_vente:
                    res['ca'] -= quantite * produit.prix_vente  # un retour client annule une vente

    if res['qte_debut'] is None:  # aucun mouvement dans la période
        res['qte_debut'], res['valeur_debut'] = qte, valeur
    res.update(qte_fin=qte, valeur_fin=valeur, cump=cump())
    return res


CACHE_DUREE = 24 * 3600
# À incrémenter à chaque changement de la règle de calcul ou du contenu du résultat : sans cela,
# des résultats calculés par l'ancienne version du code resteraient servis depuis le cache.
VERSION_CALCUL = 2


def _version(ids):
    """
    Empreinte des données qui influencent la valorisation de ces produits : elle change dès qu'un
    mouvement est créé, modifié ou supprimé, qu'un stock change ou qu'un prix est modifié.
    Trois agrégats légers, au lieu de recharger tout l'historique.
    """
    mouvements = Mouvement.objects.filter(produit_id__in=ids).aggregate(n=Count('id'), maj=Max('updated_at'))
    stocks = Stock.objects.filter(produit_id__in=ids).aggregate(q=Sum('quantite'), maj=Max('updated_at'))
    prix = Produit.objects.filter(pk__in=ids).aggregate(maj=Max('updated_at'))
    return f"{mouvements['n']}|{mouvements['maj']}|{stocks['q']}|{stocks['maj']}|{prix['maj']}"


def valoriser_produits(produits, debut=None, fin=None):
    """
    Rejoue les mouvements de plusieurs produits en une seule requête. Retourne {produit_id: résultat}.
    Le résultat est mis en cache tant que les données sous-jacentes ne changent pas (voir _version).
    """
    produits = list(produits)
    ids = sorted(str(p.pk) for p in produits)
    empreinte = hashlib.md5(f"{','.join(ids)}|{debut}|{fin}|{_version(ids)}".encode()).hexdigest()
    cle = f"stockmaster:valorisation:v{VERSION_CALCUL}:{empreinte}"
    resultat = cache.get(cle)
    if resultat is None:
        resultat = _valoriser(produits, debut, fin)
        cache.set(cle, resultat, CACHE_DUREE)
    return resultat


def _valoriser(produits, debut, fin):
    ids = [p.pk for p in produits]
    lignes = defaultdict(list)
    for pid, *mouvement in (Mouvement.objects.filter(produit_id__in=ids)
                            .order_by('date_mouvement', 'created_at')
                            .values_list('produit_id', 'type_mouvement', 'quantite', 'prix_unitaire_snapshot',
                                         'entrepot_source_id', 'entrepot_destination_id', 'date_mouvement')):
        lignes[pid].append(tuple(mouvement))
    stocks = dict(Stock.objects.filter(produit_id__in=ids).values('produit')
                  .annotate(total=Sum('quantite')).values_list('produit', 'total'))
    return {p.pk: rejouer(p, lignes[p.pk], stocks.get(p.pk) or ZERO, debut, fin) for p in produits}


def cump_permanent(produit):
    """CUMP actuel du produit (rejeu complet de ses mouvements)."""
    return valoriser_produits([produit])[produit.pk]['cump']


def prix_fifo_produits(produits):
    """FIFO de plusieurs produits en une requête (seules les entrées sont lues). Retourne {produit_id: prix}."""
    produits = list(produits)
    entrees = defaultdict(list)
    for pid, quantite, prix in (Mouvement.objects
                                .filter(produit__in=produits, type_mouvement=TypeMouvement.ENTREE)
                                .order_by('-date_mouvement', '-created_at')
                                .values_list('produit_id', 'quantite', 'prix_unitaire_snapshot')):
        entrees[pid].append((quantite, prix))
    stocks = dict(Stock.objects.filter(produit__in=produits).values('produit')
                  .annotate(total=Sum('quantite')).values_list('produit', 'total'))
    return {p.pk: _fifo_unitaire(p, stocks.get(p.pk) or ZERO, entrees[p.pk]) for p in produits}


def prix_fifo(produit):
    """
    Coût unitaire du stock restant en FIFO : les plus anciennes entrées sortent en premier, le stock
    restant est donc valorisé aux prix des entrées les plus récentes.
    """
    return prix_fifo_produits([produit])[produit.pk]


def _fifo_unitaire(produit, restant, entrees_recentes_d_abord):
    restant = Decimal(restant)
    if restant <= 0:
        return produit.prix_unitaire or ZERO
    valeur, a_couvrir = ZERO, restant
    for quantite, prix in entrees_recentes_d_abord:
        pris = min(quantite, a_couvrir)
        valeur += pris * (prix if prix is not None else produit.prix_unitaire)
        a_couvrir -= pris
        if a_couvrir <= 0:
            break
    valeur += a_couvrir * (produit.prix_unitaire or ZERO)  # stock sans entrée connue
    return valeur / restant
