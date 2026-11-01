from django.core.cache import cache

from .models import THEME_PAR_DEFAUT, THEMES, ParametresEntreprise, cle_theme

CODES_THEMES = {code for code, *_ in THEMES}


def theme(request):
    """Thème de couleurs de l'entreprise de l'utilisateur connecté (en cache, invalidé à l'enregistrement)."""
    user = getattr(request, 'user', None)
    entreprise_id = getattr(user, 'entreprise_id', None) if user is not None and user.is_authenticated else None
    if not entreprise_id:
        return {'theme_entreprise': THEME_PAR_DEFAUT}
    code = cache.get(cle_theme(entreprise_id))
    if code is None:
        code = (ParametresEntreprise.objects.filter(entreprise_id=entreprise_id)
                .values_list('theme', flat=True).first() or THEME_PAR_DEFAUT)
        cache.set(cle_theme(entreprise_id), code, 3600)
    return {'theme_entreprise': code if code in CODES_THEMES else THEME_PAR_DEFAUT}
