"""
Emails envoyés selon les paramètres de l'entreprise (page Paramètres de l'admin entreprise).
Les envois n'interrompent jamais l'action en cours : une erreur SMTP est ignorée (fail_silently).
"""
from django.db import transaction
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.core.emails import envoyer_email, lien_absolu
from apps.entreprises.models import ParametresEntreprise


def destinataires(entreprise, roles):
    """Emails des utilisateurs actifs de l'entreprise ayant l'un des rôles donnés."""
    return list(
        Utilisateur.objects.filter(entreprise=entreprise, role__in=roles, is_active=True, est_actif=True)
        .exclude(email='').values_list('email', flat=True)
    )


def envoyer(sujet, corps, emails, contexte=None):
    """Email (gabarit commun HTML + texte) ; `contexte` alimente emails/notification.html."""
    if emails:
        envoyer_email(f"[StockMaster] {sujet}", emails, corps, 'emails/notification.html',
                      {'pied': "Pour ne plus recevoir ces emails : Paramètres de l'espace admin entreprise.", **(contexte or {})})


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
    contexte = {
        'titre': f"{alerte.get_type_alerte_display()} : {alerte.produit.nom}",
        'intro': f"Nouvelle alerte de stock pour {entreprise.nom}.",
        'lignes': [('Produit', f"{alerte.produit.nom} ({alerte.produit.sku})"),
                   ('Entrepôt', alerte.entrepot.nom if alerte.entrepot else '—'),
                   ('Priorité', alerte.get_priorite_display())],
        'suite': alerte.message,
        'bouton_url': lien_absolu(reverse('gestionnaire:alertes')), 'bouton_label': 'Voir les alertes',
    }
    transaction.on_commit(lambda: envoyer(sujet, corps, emails, contexte))
