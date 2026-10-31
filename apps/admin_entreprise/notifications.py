"""
Emails envoyés selon les paramètres de l'entreprise (page Paramètres de l'admin entreprise).
Les envois n'interrompent jamais l'action en cours : une erreur SMTP est ignorée (fail_silently).
"""
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from apps.accounts.models import Utilisateur
from apps.entreprises.models import ParametresEntreprise


def destinataires(entreprise, roles):
    """Emails des utilisateurs actifs de l'entreprise ayant l'un des rôles donnés."""
    return list(
        Utilisateur.objects.filter(entreprise=entreprise, role__in=roles, is_active=True, est_actif=True)
        .exclude(email='').values_list('email', flat=True)
    )


def envoyer(sujet, corps, emails):
    if emails:
        send_mail(f"[StockMaster] {sujet}", corps, settings.DEFAULT_FROM_EMAIL, emails, fail_silently=True)


def notifier_alerte(alerte):
    """Email aux admins et gestionnaires pour une nouvelle alerte, si l'entreprise l'a activé."""
    entreprise = alerte.produit.entreprise
    if not ParametresEntreprise.pour(entreprise).alertes_email:
        return
    emails = destinataires(entreprise, ['admin_ent', 'gestionnaire'])
    sujet = f"{alerte.get_type_alerte_display()} : {alerte.produit.nom}"
    corps = (
        f"Nouvelle alerte de stock pour {entreprise.nom}.\n\n"
        f"Produit   : {alerte.produit.nom} ({alerte.produit.sku})\n"
        f"Entrepôt  : {alerte.entrepot.nom if alerte.entrepot else '—'}\n"
        f"Priorité  : {alerte.get_priorite_display()}\n\n"
        f"{alerte.message}\n\n"
        "Pour ne plus recevoir ces emails : Paramètres de l'espace admin entreprise."
    )
    # Après validation de la transaction : pas d'email pour une alerte annulée par un rollback
    transaction.on_commit(lambda: envoyer(sujet, corps, emails))
