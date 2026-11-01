"""
Tâches planifiées pilotées par les paramètres de chaque entreprise (voir config/celery.py) :
alertes d'expiration, suggestions d'achat IA par email, rapport hebdomadaire.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.db.models import F, Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.emails import lien_absolu
from apps.entreprises.models import Entreprise, ParametresEntreprise

from .notifications import destinataires, envoyer, notifier_alerte

logger = logging.getLogger("stockmaster.notifications")


def _entreprises_actives():
    return Entreprise.objects.filter(est_active=True)


@shared_task(name="apps.admin_entreprise.tasks.verifier_expirations")
def verifier_expirations():
    """
    Crée une alerte « proche de l'expiration » pour chaque lot reçu dont la date d'expiration tombe
    dans le délai réglé par l'entreprise, tant que le produit est encore en stock dans l'entrepôt.
    """
    from apps.stock.models import Alerte, Mouvement, PrioriteAlerte, Stock, TypeAlerte, TypeMouvement

    aujourd_hui = timezone.localdate()
    nb_creees = 0
    for entreprise in _entreprises_actives():
        delai = ParametresEntreprise.pour(entreprise).jours_alerte_expiration
        lots = (Mouvement.objects
                .filter(produit__entreprise=entreprise, type_mouvement=TypeMouvement.ENTREE,
                        date_expiration__isnull=False, date_expiration__lte=aujourd_hui + timedelta(days=delai),
                        entrepot_destination__isnull=False)
                .select_related('produit', 'entrepot_destination'))
        for lot in lots:
            en_stock = Stock.objects.filter(produit=lot.produit, entrepot=lot.entrepot_destination,
                                            quantite__gt=0).exists()
            if not en_stock:
                continue
            jours = (lot.date_expiration - aujourd_hui).days
            etat = "expiré depuis le" if jours < 0 else "expire le"
            alerte, creee = Alerte.objects.get_or_create(
                produit=lot.produit, entrepot=lot.entrepot_destination,
                type_alerte=TypeAlerte.EXPIRATION, lue=False,
                defaults={
                    'priorite': PrioriteAlerte.HAUTE if jours <= 7 else PrioriteAlerte.MOYENNE,
                    'message': (f"Lot {lot.lot_numero or 'sans numéro'} de « {lot.produit.nom} » "
                                f"{etat} {lot.date_expiration:%d/%m/%Y}."),
                },
            )
            if creee:
                nb_creees += 1
                notifier_alerte(alerte)
    logger.info("[Notifications] %s alerte(s) d'expiration créée(s)", nb_creees)
    return nb_creees


@shared_task(name="apps.admin_entreprise.tasks.envoyer_suggestions_ia")
def envoyer_suggestions_ia():
    """Email quotidien des produits à commander (suggestions IA) aux responsables achat."""
    from apps.responsable_achat.views import _calculer_suggestions

    nb_emails = 0
    for entreprise in _entreprises_actives():
        if not ParametresEntreprise.pour(entreprise).ia_email:
            continue
        suggestions = _calculer_suggestions(entreprise)
        if not suggestions:
            continue
        lignes = [
            f"- {s['produit'].nom} ({s['produit'].sku}) : commander {s['quantite_suggeree']:g}"
            + (f", rupture estimée dans {s['jours_rupture']} jour(s)" if s['jours_rupture'] is not None
               else ", sous le seuil d'alerte")
            for s in suggestions[:20]
        ]
        corps = (f"{len(suggestions)} produit(s) à commander pour {entreprise.nom} d'après les prédictions IA :\n\n"
                 + "\n".join(lignes)
                 + ("\n\n… et d'autres dans l'espace responsable achat." if len(suggestions) > 20 else "")
                 + "\n\nPour ne plus recevoir ces emails : Paramètres de l'espace admin entreprise.")
        emails = destinataires(entreprise, ['responsable_achat', 'admin_ent'])
        contexte = {
            'titre': f"{len(suggestions)} produit{'s' if len(suggestions) > 1 else ''} à commander",
            'intro': f"D'après les prévisions IA, voici ce qu'il faut commander pour {entreprise.nom}.",
            'liste': [l[2:] for l in lignes],
            'suite': "… et d'autres dans l'espace responsable achat." if len(suggestions) > 20 else '',
            'bouton_url': lien_absolu(reverse('responsable_achat:suggestions_list')), 'bouton_label': "Voir les suggestions d'achat",
        }
        envoyer(f"Suggestions d'achat du {timezone.localdate():%d/%m/%Y}", corps, emails, contexte)
        nb_emails += bool(emails)
    return nb_emails


@shared_task(name="apps.admin_entreprise.tasks.envoyer_rapports_hebdo")
def envoyer_rapports_hebdo():
    """Synthèse des 7 derniers jours, envoyée le lundi aux admins des entreprises qui l'ont activée."""
    from apps.stock.models import Alerte, BonCommande, Mouvement, Produit, Stock, TypeMouvement

    depuis = timezone.now() - timedelta(days=7)
    nb_emails = 0
    for entreprise in _entreprises_actives():
        if not ParametresEntreprise.pour(entreprise).rapport_hebdo:
            continue
        valeur = (Stock.objects.filter(entrepot__entreprise=entreprise)
                  .aggregate(v=Sum(F('quantite') * F('produit__prix_unitaire')))['v'] or Decimal(0))
        totaux = Produit.objects.filter(entreprise=entreprise, est_actif=True).annotate(total=Sum('stocks__quantite'))
        nb_ruptures = totaux.filter(total__lte=0).count() + totaux.filter(total__isnull=True).count()
        mouvements = Mouvement.objects.filter(produit__entreprise=entreprise, date_mouvement__gte=depuis)
        valeur_txt = f"{valeur:,.0f}".replace(',', ' ')
        chiffres = [
            ("Valeur du stock", f"{valeur_txt} FCFA"),
            ("Produits en rupture", nb_ruptures),
            ("Alertes non traitées", Alerte.objects.filter(produit__entreprise=entreprise, lue=False).count()),
            ("Entrées sur 7 jours", mouvements.filter(type_mouvement=TypeMouvement.ENTREE).count()),
            ("Sorties sur 7 jours", mouvements.filter(type_mouvement=TypeMouvement.SORTIE).count()),
            ("Commandes en attente",
             BonCommande.objects.filter(entreprise=entreprise, statut__in=['envoye', 'recu_partiel']).count()),
        ]
        corps = (
            f"Rapport hebdomadaire de {entreprise.nom} ({depuis:%d/%m} – {timezone.localdate():%d/%m/%Y})\n\n"
            + "".join(f"{libelle:<25}: {valeur_}\n" for libelle, valeur_ in chiffres)
            + "\nPour ne plus recevoir ce rapport : Paramètres de l'espace admin entreprise."
        )
        emails = destinataires(entreprise, ['admin_ent'])
        contexte = {
            'titre': 'Rapport hebdomadaire',
            'intro': f"Synthèse de {entreprise.nom} du {depuis:%d/%m} au {timezone.localdate():%d/%m/%Y}.",
            'lignes': chiffres,
            'bouton_url': lien_absolu(reverse('admin_entreprise:dashboard')), 'bouton_label': 'Ouvrir le tableau de bord',
        }
        envoyer("Rapport hebdomadaire", corps, emails, contexte)
        nb_emails += bool(emails)
    return nb_emails
