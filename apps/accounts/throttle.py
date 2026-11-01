"""
Limitation des tentatives de connexion (force brute et bourrage d'identifiants).

Compteur par couple (adresse IP, identifiant) et par adresse IP seule, dans le cache : au-delà du seuil, la connexion
est refusée pendant la durée de blocage, même avec le bon mot de passe. Une connexion réussie remet le compteur de
l'identifiant à zéro. Si le cache est indisponible, la limitation est désactivée (le service reste utilisable).
"""
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import cache
from django.dispatch import receiver

ESSAIS_PAR_IDENTIFIANT = getattr(settings, 'LOGIN_MAX_ESSAIS', 5)
ESSAIS_PAR_IP = getattr(settings, 'LOGIN_MAX_ESSAIS_IP', 30)
DUREE_BLOCAGE = getattr(settings, 'LOGIN_DUREE_BLOCAGE', 15 * 60)


def adresse_ip(request):
    """Adresse du client. X-Forwarded-For n'est lu que derrière notre proxy (Caddy), qui la renseigne lui-même."""
    if getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[-1].strip()  # dernière entrée : ajoutée par notre proxy, non falsifiable par le client
    return request.META.get('REMOTE_ADDR', '')


def _cles(request, identifiant):
    ip = adresse_ip(request)
    return f'stockmaster:login:id:{ip}:{(identifiant or "").strip().lower()[:150]}', f'stockmaster:login:ip:{ip}'


def est_bloque(request, identifiant):
    cle_id, cle_ip = _cles(request, identifiant)
    return (cache.get(cle_id, 0) >= ESSAIS_PAR_IDENTIFIANT) or (cache.get(cle_ip, 0) >= ESSAIS_PAR_IP)


def _incrementer(cle):
    if cache.add(cle, 1, DUREE_BLOCAGE):
        return
    try:
        cache.incr(cle)
    except ValueError:  # expirée entre-temps
        cache.set(cle, 1, DUREE_BLOCAGE)


@receiver(user_login_failed)
def echec_connexion(sender, credentials=None, request=None, **kwargs):
    if request is None:
        return
    cle_id, cle_ip = _cles(request, (credentials or {}).get('username') or (credentials or {}).get('email'))
    _incrementer(cle_id)
    _incrementer(cle_ip)


@receiver(user_logged_in)
def succes_connexion(sender, request=None, user=None, **kwargs):
    if request is None or user is None:
        return
    cache.delete(_cles(request, getattr(user, 'email', '') or user.get_username())[0])
    cache.delete(_cles(request, user.get_username())[0])
