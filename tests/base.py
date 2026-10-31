"""Fabriques de données partagées par les tests des points critiques."""
import itertools
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Utilisateur
from apps.entreprises.models import Entreprise, TypeEntreprise
from apps.stock.models import Entrepot, Fournisseur, Produit, Stock

_seq = itertools.count(1)


def creer_entreprise(nom=None, active=True):
    return Entreprise.objects.create(
        nom=nom or f"Entreprise {next(_seq)}",
        type_entreprise=TypeEntreprise.GROS_DISTRIBUTION,
        est_active=active,
    )


def creer_utilisateur(role, entreprise=None):
    n = next(_seq)
    return Utilisateur.objects.create_user(
        username=f"user{n}", email=f"user{n}@test.local", password="MotDePasse-Test-123",
        first_name="Test", last_name=role, role=role, entreprise=entreprise, est_actif=True,
    )


def creer_entrepot(entreprise, nom="Entrepôt principal"):
    return Entrepot.objects.create(nom=nom, entreprise=entreprise)


def creer_produit(entreprise, nom="Riz 25 kg", prix="1000", seuil="5"):
    return Produit.objects.create(
        nom=nom, sku=f"SKU-{next(_seq)}", entreprise=entreprise,
        prix_unitaire=Decimal(prix), seuil_alerte=Decimal(seuil),
    )


def creer_fournisseur(entreprise, nom="Fournisseur SA"):
    return Fournisseur.objects.create(nom=nom, entreprise=entreprise)


def mettre_en_stock(produit, entrepot, quantite):
    return Stock.objects.create(produit=produit, entrepot=entrepot, quantite=Decimal(str(quantite)))


def quantite_en_stock(produit, entrepot):
    stock = Stock.objects.filter(produit=produit, entrepot=entrepot).first()
    return stock.quantite if stock else Decimal(0)


class EntrepriseTestCase(TestCase):
    """Une entreprise avec un entrepôt, un produit (10 en stock) et un utilisateur par rôle."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = creer_entreprise("Entreprise A")
        cls.entrepot = creer_entrepot(cls.ent)
        cls.produit = creer_produit(cls.ent)
        cls.fournisseur = creer_fournisseur(cls.ent)
        mettre_en_stock(cls.produit, cls.entrepot, 10)
        cls.users = {
            role: creer_utilisateur(role, cls.ent)
            for role in ('admin_ent', 'gestionnaire', 'responsable_achat', 'magasinier', 'auditeur', 'comptable')
        }

    def connecter(self, role):
        self.client.force_login(self.users[role])
        return self.users[role]
