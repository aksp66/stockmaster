"""
Écriture CSV protégée contre l'injection de formules.

Un tableur (Excel, LibreOffice) exécute comme une formule toute cellule qui commence par « = », « + », « - » ou « @ ».
Un nom de produit ou de fournisseur saisi par un utilisateur et exporté tel quel pourrait donc piéger la personne qui
ouvre le fichier. Les textes de ce type sont précédés d'une apostrophe ; les nombres (même négatifs) restent intacts.
"""
import csv
import re

DEBUTS_DANGEREUX = ('=', '+', '-', '@', '\t', '\r')
NOMBRE = re.compile(r'^[+-]?[\d\s\u202f\u00a0.,]+(%|\s?[A-Za-z€]{0,5})?$')


def proteger(cellule):
    if isinstance(cellule, str) and cellule.startswith(DEBUTS_DANGEREUX) and not NOMBRE.match(cellule):
        return "'" + cellule
    return cellule


class _EcrivainSur:
    def __init__(self, ecrivain):
        self._ecrivain = ecrivain
        self.dialect = ecrivain.dialect

    def writerow(self, ligne):
        return self._ecrivain.writerow([proteger(c) for c in ligne])

    def writerows(self, lignes):
        for ligne in lignes:
            self.writerow(ligne)


def writer(fichier, **options):
    """Équivalent de csv.writer avec protection contre l'injection de formules."""
    return _EcrivainSur(csv.writer(fichier, **options))
