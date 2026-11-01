"""Envoi des emails de l'application : tous partagent le gabarit emails/_base_email.html (HTML + version texte)."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def lien_absolu(chemin):
    """URL complète d'un chemin du site, pour les emails envoyés hors requête (tâches planifiées)."""
    return settings.SITE_URL.rstrip('/') + chemin


def envoyer_email(sujet, destinataires, texte, template, contexte=None, fail_silently=True):
    """
    Email HTML (gabarit commun) avec sa version texte. Retourne le nombre d'emails envoyés (0 sans destinataire).
    `template` étend emails/_base_email.html ; `contexte` alimente le gabarit (`sujet` est ajouté automatiquement).
    """
    destinataires = list(destinataires)
    if not destinataires:
        return 0
    html = render_to_string(template, {**(contexte or {}), 'sujet': sujet})
    message = EmailMultiAlternatives(sujet, texte, settings.DEFAULT_FROM_EMAIL, destinataires)
    message.attach_alternative(html, 'text/html')
    return message.send(fail_silently=fail_silently)
