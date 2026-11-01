"""Filtres de gabarit communs."""
import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe

register = template.Library()

# Caractères qui permettraient de sortir d'un <script> ou de casser un littéral JavaScript, remplacés par leur
# échappement « \uXXXX » (l'antislash est écrit explicitement : ce sont bien des séquences de six caractères)
_ANTISLASH = chr(92)
_ECHAPPEMENTS = {
    ord('<'): _ANTISLASH + 'u003C',
    ord('>'): _ANTISLASH + 'u003E',
    ord('&'): _ANTISLASH + 'u0026',
    0x2028: _ANTISLASH + 'u2028',
    0x2029: _ANTISLASH + 'u2029',
}


@register.filter
def json_js(valeur):
    """
    Valeur Python (liste, dict, nombre, texte) en littéral JSON utilisable dans un <script>.
    Contrairement à |safe, « < », « > » et « & » sont échappés : un nom de catégorie ou de produit
    contenant « </script> » ne peut pas sortir du script. Une chaîne qui est déjà du JSON est normalisée.
    """
    if isinstance(valeur, str):
        try:
            valeur = json.loads(valeur)
        except ValueError:
            pass
    return mark_safe(json.dumps(valeur, cls=DjangoJSONEncoder, ensure_ascii=False).translate(_ECHAPPEMENTS))
