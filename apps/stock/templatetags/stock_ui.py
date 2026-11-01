"""Balises d'affichage communes à tous les espaces : une seule règle et une seule palette pour les statuts de stock
et les catégories (couleurs définies dans static/css/stockmaster.css)."""
import zlib

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

STATUTS = {
    'rupture': 'Rupture',
    'critique': 'Alerte',
    'faible': 'Faible',
    'ok': 'OK',
}


def _champ(produit, nom):
    """Valeur d'un champ d'un produit (objet ou dictionnaire) ; appelée s'il s'agit d'une méthode."""
    valeur = produit.get(nom) if isinstance(produit, dict) else getattr(produit, nom, None)
    return valeur() if callable(valeur) else valeur


def code_statut(produit):
    """rupture (0) ; critique (au seuil ou en dessous) ; faible (jusqu'à 2 × le seuil) ; ok."""
    quantite, seuil = _champ(produit, 'quantite_totale') or 0, _champ(produit, 'seuil_alerte') or 0
    if quantite <= 0:
        return 'rupture'
    if quantite <= seuil:
        return 'critique'
    if quantite <= seuil * 2:
        return 'faible'
    return 'ok'


@register.filter
def statut_stock(produit):
    """Code du statut de stock d'un produit (rupture, critique, faible, ok)."""
    return code_statut(produit)


@register.simple_tag
def st_badge(produit, libelle=None):
    """Pastille du statut de stock d'un produit."""
    code = code_statut(produit)
    return format_html('<span class="st st-{}">{}</span>', code, libelle or STATUTS[code])


@register.simple_tag
def st_color(produit):
    """Couleur CSS du statut de stock (pour un chiffre ou une icône)."""
    return f'var(--st-{code_statut(produit)})'


@register.simple_tag
def st_dim(produit):
    """Teinte claire du statut de stock (fond d'icône)."""
    return f'var(--st-{code_statut(produit)}-dim)'


@register.filter
def cat_index(nom):
    """Numéro de couleur (0 à 7) d'une catégorie : toujours le même pour un même nom."""
    return zlib.crc32(str(nom or '').strip().lower().encode()) % 8


@register.simple_tag
def cat_badge(categorie, petit=False):
    """Pastille colorée d'une catégorie (tiret si elle n'existe pas)."""
    if not categorie:
        return mark_safe('<span style="color:var(--text-m);font-size:12px;">—</span>')
    style = 'font-size:10px;' if petit else ''
    return format_html('<span class="cat cat-{}" style="{}">{}</span>', cat_index(categorie.nom), style, categorie.nom)
