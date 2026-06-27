#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed pour entreprise GROS DISTRIBUTION - Alimentation générale
5 ans d'activité, 100 produits, toutes tables remplies.
Commande : python manage.py runscript seed
"""

import os
import django
import random
from datetime import datetime, timedelta, date
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.entreprises.models import Entreprise, TypeEntreprise
from apps.accounts.models import Utilisateur, RoleUtilisateur
from apps.stock.models import (
    Categorie, Produit, Entrepot, Stock, Mouvement, TypeMouvement,
    Fournisseur, BonCommande, StatutBonCommande, LigneCommande,
    Alerte, TypeAlerte, PrioriteAlerte, PredictionStock,
    Emplacement, InventaireSession, LigneInventaire, ScanLog
)
from apps.core.models import AuditLog, TypeAction, Notification, ExportLog

User = get_user_model()

# ============================================================================
# CONFIGURATION
# ============================================================================
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
DATE_FIN = date.today()
DATE_DEBUT = DATE_FIN - timedelta(days=5*365)

# ============================================================================
# CATÉGORIES (alimentation générale)
# ============================================================================
CATEGORIES_DATA = [
    {"nom": "Produits de base (riz, pâtes, farine)", "conso_mensuelle_moyenne": 200, "unite": "kg"},
    {"nom": "Conserves & sauces", "conso_mensuelle_moyenne": 150, "unite": "boîte"},
    {"nom": "Boissons (eau, jus, soda)", "conso_mensuelle_moyenne": 300, "unite": "litre"},
    {"nom": "Snacks & biscuits", "conso_mensuelle_moyenne": 180, "unite": "paquet"},
    {"nom": "Produits laitiers & œufs", "conso_mensuelle_moyenne": 120, "unite": "unité"},
    {"nom": "Huiles & condiments", "conso_mensuelle_moyenne": 90, "unite": "litre"},
    {"nom": "Surgelés", "conso_mensuelle_moyenne": 80, "unite": "kg"},
    {"nom": "Épicerie sucrée", "conso_mensuelle_moyenne": 110, "unite": "unité"},
    {"nom": "Hygiène & entretien (alimentaire)", "conso_mensuelle_moyenne": 60, "unite": "unité"},
]

# ============================================================================
# FOURNISSEURS (spécialisés alimentation)
# ============================================================================
FOURNISSEURS_DATA = [
    {"nom": "Nestlé Togo", "pays": "Togo", "delai_jours": 5, "contact": "Kofi A.",
     "email": "commandes@nestle.tg", "telephone": "+228 90 00 00 01"},
    {"nom": "SAB Miller (boissons)", "pays": "Ghana", "delai_jours": 7, "contact": "John D.",
     "email": "sales@sabmiller.gh", "telephone": "+233 20 00 00 10"},
    {"nom": "Panasonic (surgelés)", "pays": "Bénin", "delai_jours": 4, "contact": "Ablo P.",
     "email": "contact@panasonic.bj", "telephone": "+229 90 00 00 20"},
    {"nom": "SAO (huiles)", "pays": "Côte d'Ivoire", "delai_jours": 8, "contact": "Kouadio L.",
     "email": "ventes@sao.ci", "telephone": "+225 05 00 00 30"},
    {"nom": "Belle France (conserverie)", "pays": "France", "delai_jours": 15, "contact": "Michèle R.",
     "email": "export@bellefrance.fr", "telephone": "+33 1 23 45 67"},
    {"nom": "Togo Riz", "pays": "Togo", "delai_jours": 3, "contact": "Esso G.",
     "email": "ventes@togoriz.tg", "telephone": "+228 90 00 00 40"},
    {"nom": "Coca-Cola Bénin", "pays": "Bénin", "delai_jours": 6, "contact": "Sylvain K.",
     "email": "commande@cocacola.bj", "telephone": "+229 90 00 00 50"},
]

# ============================================================================
# PRODUITS (100 items réalistes alimentation générale)
# ============================================================================
PRODUITS_PAR_CATEGORIE = {
    "Produits de base (riz, pâtes, farine)": [
        ("Riz parfumé 5kg", "kg", 2500, 3500, 50, 150),
        ("Riz brisé 25kg", "kg", 12000, 15000, 20, 60),
        ("Pâtes alimentaires 500g", "unité", 350, 500, 200, 500),
        ("Farine de blé 1kg", "kg", 800, 1200, 100, 300),
        ("Sucre en poudre 1kg", "kg", 850, 1100, 80, 200),
        ("Sel fin 1kg", "kg", 300, 450, 100, 250),
        ("Maïs grain 25kg", "kg", 8000, 11000, 30, 80),
        ("Haricot sec 1kg", "kg", 1200, 1800, 40, 120),
    ],
    "Conserves & sauces": [
        ("Sauce tomate 400g", "boîte", 500, 750, 200, 500),
        ("Thon à l'huile 1 boîte", "boîte", 1200, 1800, 80, 200),
        ("Sardines à l'huile", "boîte", 800, 1200, 100, 250),
        ("Petit pois carottes", "boîte", 450, 650, 150, 300),
        ("Mayonnaise 500ml", "bouteille", 900, 1300, 60, 150),
        ("Ketchup 500ml", "bouteille", 800, 1200, 70, 180),
    ],
    "Boissons (eau, jus, soda)": [
        ("Eau minérale 1.5L", "bouteille", 250, 400, 500, 1000),
        ("Jus d'orange 1L", "bouteille", 1000, 1500, 200, 500),
        ("Coca-Cola 33cl", "canette", 350, 500, 400, 800),
        ("Energy drink 250ml", "canette", 600, 900, 100, 300),
        ("Lait en poudre 500g", "paquet", 1800, 2500, 50, 150),
        ("Sirop de menthe 70cl", "bouteille", 1200, 1700, 40, 100),
    ],
    "Snacks & biscuits": [
        ("Biscuits secs 200g", "paquet", 300, 500, 200, 600),
        ("Cacahuètes grillées 100g", "sachet", 150, 250, 300, 800),
        ("Chocolat noir 100g", "tablette", 600, 900, 100, 300),
        ("Bonbons assortis 500g", "sachet", 1000, 1500, 80, 200),
        ("Gâteaux moelleux 150g", "paquet", 400, 600, 150, 400),
    ],
    "Produits laitiers & œufs": [
        ("Œufs frais (boîte 30)", "boîte", 1800, 2500, 50, 150),
        ("Beurre 250g", "plaquette", 800, 1200, 60, 180),
        ("Fromage râpé 200g", "sachet", 1000, 1500, 40, 120),
        ("Yaourt nature 12x125g", "pack", 2400, 3200, 30, 90),
        ("Crème fraîche 20cl", "bouteille", 600, 900, 50, 150),
    ],
    "Huiles & condiments": [
        ("Huile de palme 1L", "litre", 900, 1300, 100, 250),
        ("Huile d'olive 500ml", "bouteille", 2500, 3500, 30, 80),
        ("Vinaigre balsamique 250ml", "bouteille", 800, 1200, 40, 100),
        ("Poivre noir moulu 50g", "pot", 300, 500, 80, 200),
        ("Ail semoule 100g", "pot", 250, 400, 60, 150),
    ],
    "Surgelés": [
        ("Poisson pangasius 1kg", "kg", 3500, 5000, 40, 100),
        ("Frites surgelées 2kg", "kg", 2500, 3500, 50, 120),
        ("Petits pois surgelés 500g", "sachet", 800, 1200, 60, 150),
        ("Glace vanille 1L", "bac", 2000, 3000, 30, 80),
        ("Légumes variés 1kg", "kg", 1800, 2600, 50, 120),
    ],
    "Épicerie sucrée": [
        ("Confiture fraise 350g", "pot", 900, 1300, 50, 150),
        ("Miel liquide 500g", "pot", 2000, 2800, 30, 80),
        ("Nutella 350g", "pot", 3000, 4000, 40, 100),
        ("Crème de marrons", "pot", 1500, 2200, 20, 60),
        ("Flocons d'avoine 500g", "paquet", 500, 800, 60, 150),
    ],
    "Hygiène & entretien (alimentaire)": [
        ("Café moulu 250g", "paquet", 1500, 2200, 50, 150),
        ("Thé en sachets 50x2g", "boîte", 800, 1200, 60, 180),
        ("Chocolat en poudre 400g", "pot", 1200, 1700, 40, 120),
        ("Infusion camomille 20s", "boîte", 700, 1100, 30, 90),
    ],
}

# ============================================================================
# UTILITAIRES (emails basés sur le rôle)
# ============================================================================
UTILISATEURS_ROLES = [
    ("adminent", RoleUtilisateur.ADMIN_ENT, "Admin", "Ent"),
    ("gest", RoleUtilisateur.GESTIONNAIRE, "Gestion", "Stock"),
    ("respa", RoleUtilisateur.RESPONSABLE_ACHAT, "Achat", "Principal"),
    ("maga", RoleUtilisateur.MAGASINIER, "Mike", "Mag"),
    ("audit", RoleUtilisateur.AUDITEUR, "Audit", "Checker"),
    ("comp", RoleUtilisateur.COMPTABLE, "Compta", "Fin"),
]

def get_or_create_entreprise():
    entreprise, created = Entreprise.objects.get_or_create(
        nom="StockMaster Démo",
        defaults={
            "type_entreprise": TypeEntreprise.GROS_DISTRIBUTION,
            "pays": "Togo",
            "ville": "Lomé",
            "taille": "50-100",
            "nb_entrepots": 3,
            "est_active": True,
        }
    )
    if created:
        print("✅ Entreprise StockMaster Démo créée")
    else:
        print("⏭️ Entreprise déjà existante")
    return entreprise

def clear_company_data(entreprise):
    print("\n🧹 Nettoyage des anciennes données...")
    ScanLog.objects.filter(utilisateur__entreprise=entreprise).delete()
    LigneInventaire.objects.filter(produit__entreprise=entreprise).delete()
    InventaireSession.objects.filter(entrepot__entreprise=entreprise).delete()
    PredictionStock.objects.filter(produit__entreprise=entreprise).delete()
    Alerte.objects.filter(produit__entreprise=entreprise).delete()
    LigneCommande.objects.filter(bon_commande__entreprise=entreprise).delete()
    BonCommande.objects.filter(entreprise=entreprise).delete()
    Mouvement.objects.filter(produit__entreprise=entreprise).delete()
    Stock.objects.filter(entrepot__entreprise=entreprise).delete()
    Produit.objects.filter(entreprise=entreprise).delete()
    Emplacement.objects.filter(entrepot__entreprise=entreprise).delete()
    Entrepot.objects.filter(entreprise=entreprise).delete()
    Fournisseur.objects.filter(entreprise=entreprise).delete()
    Categorie.objects.filter(entreprise=entreprise).delete()
    Notification.objects.filter(destinataire__entreprise=entreprise).delete()
    ExportLog.objects.filter(entreprise=entreprise).delete()
    AuditLog.objects.filter(entreprise=entreprise).delete()
    print("   ✅ Nettoyage terminé.")

def random_date_between(start_date, end_date):
    delta = end_date - start_date
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return start_date + timedelta(seconds=random_seconds)

@transaction.atomic
def creer_categories(entreprise):
    print("\n📦 Création des catégories...")
    cats = {}
    for data in CATEGORIES_DATA:
        cat, _ = Categorie.objects.get_or_create(
            nom=data["nom"],
            entreprise=entreprise,
            defaults={"description": f"Catégorie {data['nom']} - Alimentation"}
        )
        cats[data["nom"]] = cat
        print(f"   ✅ {cat.nom}")
    return cats

@transaction.atomic
def creer_fournisseurs(entreprise):
    print("\n🏭 Création des fournisseurs...")
    fournisseurs = []
    for data in FOURNISSEURS_DATA:
        f, _ = Fournisseur.objects.get_or_create(
            nom=data["nom"],
            entreprise=entreprise,
            defaults={
                "pays": data["pays"],
                "delai_moyen_jours": data["delai_jours"],
                "est_actif": True,
                "contact": data.get("contact", ""),
                "email": data.get("email", ""),
                "telephone": data.get("telephone", ""),
                "adresse": f"Zone industrielle, {data['pays']}"
            }
        )
        fournisseurs.append(f)
        print(f"   ✅ {f.nom}")
    return fournisseurs

@transaction.atomic
def creer_entrepots_emplacements(entreprise):
    print("\n🏗️ Création de 3 entrepôts avec emplacements...")
    entrepots = []
    for i in range(1, 4):
        nom = f"Entrepôt {['Nord', 'Sud', 'Centre'][i-1]} Lomé"
        e, _ = Entrepot.objects.get_or_create(
            nom=nom,
            entreprise=entreprise,
            defaults={
                "adresse": f"Zone franche, Lomé",
                "ville": "Lomé",
                "pays": "Togo",
                "est_actif": True,
                "telephone": f"+228 90 00 00 {i+10}",
            }
        )
        # 4 à 6 emplacements par entrepôt
        for j in range(1, random.randint(4, 7)):
            Emplacement.objects.get_or_create(
                code=f"{nom[:2].upper()}-{j:02d}",
                entrepot=e,
                defaults={"description": f"Allée {chr(64+j)}"}
            )
        entrepots.append(e)
        print(f"   ✅ {e.nom}")
    return entrepots

@transaction.atomic
def creer_utilisateurs(entreprise):
    print("\n👤 Création des utilisateurs (emails dynamiques)...")
    users = {}
    default_pwd = "StockMaster2024!"
    for prefix, role, first, last in UTILISATEURS_ROLES:
        email = f"{prefix}@stockmaster.tg"
        user, created = Utilisateur.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": first,
                "last_name": last,
                "role": role,
                "entreprise": entreprise,
                "est_actif": True,
                "is_active": True,
            }
        )
        if created:
            user.set_password(default_pwd)
            user.save()
            print(f"   ✅ {email} ({role})")
        else:
            print(f"   ⏭️ {email} existe déjà")
        users[role] = user
    return users

@transaction.atomic
def creer_produits(categories, fournisseurs, entreprise):
    """Crée exactement 100 produits (variantes si besoin)"""
    print("\n📦 Création des produits (alimentation)...")
    produits = []
    fournisseurs_list = fournisseurs

    for cat_name, items in PRODUITS_PAR_CATEGORIE.items():
        cat = categories.get(cat_name)
        if not cat:
            continue
        for nom, unite, prix_min, prix_max, seuil_min, seuil_max in items:
            sku = f"{cat_name[:3].upper()}-{random.randint(1000, 9999)}"
            prix_achat = Decimal(random.randint(prix_min, prix_max))
            seuil = random.randint(seuil_min, seuil_max)
            code_barres = f"629{random.randint(1000000000, 9999999999)}"
            description = f"{nom} - Produit d'alimentation générale, conditionné par {unite}."
            produit = Produit.objects.create(
                entreprise=entreprise,
                nom=nom,
                sku=sku,
                code_barres=code_barres,
                description=description,
                unite_mesure=unite,
                seuil_alerte=seuil,
                prix_unitaire=prix_achat,
                prix_vente=prix_achat * Decimal(random.uniform(1.25, 1.6)),
                categorie=cat,
                fournisseur_principal=random.choice(fournisseurs_list),
                est_actif=True,
            )
            produits.append(produit)
            print(f"   ✅ {produit.nom} (SKU: {sku})")
    
    # Compléter pour atteindre 100 produits
    if len(produits) < 100:
        besoin = 100 - len(produits)
        print(f"   ⚠️ Ajout de {besoin} variantes...")
        base = produits[:]
        for i in range(besoin):
            p = random.choice(base)
            sku = f"{p.categorie.nom[:3].upper()}-{random.randint(1000, 9999)}"
            nouveau = Produit.objects.create(
                entreprise=entreprise,
                nom=f"{p.nom} (var{i+1})",
                sku=sku,
                code_barres=f"629{random.randint(1000000000, 9999999999)}",
                description=f"Variante de {p.nom}",
                unite_mesure=p.unite_mesure,
                seuil_alerte=p.seuil_alerte,
                prix_unitaire=p.prix_unitaire,
                prix_vente=p.prix_vente,
                categorie=p.categorie,
                fournisseur_principal=p.fournisseur_principal,
                est_actif=True,
            )
            produits.append(nouveau)
            print(f"   ✅ Variante : {nouveau.nom}")
    
    print(f"   ✅ Total : {len(produits)} produits")
    return produits

@transaction.atomic
def creer_mouvements_et_stock(produits, entrepots, users):
    """Simule 5 ans d'activité avec des consommations réalistes"""
    print("\n📈 Génération des mouvements sur 5 ans...")
    types_entree = [TypeMouvement.ENTREE, TypeMouvement.RETOUR]
    types_sortie = [TypeMouvement.SORTIE, TypeMouvement.PERTE]
    utilisateurs = list(users.values())
    total_mouvements = 0

    conso_map = {cat["nom"]: cat["conso_mensuelle_moyenne"] for cat in CATEGORIES_DATA}

    for produit in produits:
        entrepot = random.choice(entrepots)
        conso_base = conso_map.get(produit.categorie.nom, 100)
        stock_actuel = Decimal(random.randint(int(conso_base)*2, int(conso_base)*5))
        
        # Stock initial
        date_init = timezone.make_aware(datetime(DATE_DEBUT.year, DATE_DEBUT.month, 1, 8, 0))
        Mouvement.objects.create(
            type_mouvement=TypeMouvement.ENTREE,
            produit=produit,
            quantite=stock_actuel,
            entrepot_destination=entrepot,
            utilisateur=random.choice(utilisateurs),
            reference=f"INIT-{produit.sku}",
            date_mouvement=date_init,
            prix_unitaire_snapshot=produit.prix_unitaire,
            note="Stock initial"
        )
        total_mouvements += 1
        
        current_date = DATE_DEBUT
        while current_date <= DATE_FIN:
            annee, mois = current_date.year, current_date.month
            nb_jours = (date(annee, mois+1, 1) - date(annee, mois, 1)).days if mois < 12 else 31
            conso_mois = int(conso_base * random.uniform(0.6, 1.8))
            if conso_mois < 1:
                conso_mois = 1
            
            jours = list(range(1, nb_jours+1))
            random.shuffle(jours)
            reste = conso_mois
            for jour in jours:
                if reste <= 0:
                    break
                qte_sortie = random.randint(1, min(reste, max(1, conso_mois//4)))
                if stock_actuel >= qte_sortie:
                    date_mvt = datetime(annee, mois, jour, random.randint(9, 17), random.randint(0,59))
                    Mouvement.objects.create(
                        type_mouvement=random.choice(types_sortie),
                        produit=produit,
                        quantite=Decimal(qte_sortie),
                        entrepot_source=entrepot,
                        utilisateur=random.choice(utilisateurs),
                        reference=f"SORT-{produit.sku}-{date_mvt.strftime('%Y%m%d')}",
                        date_mouvement=timezone.make_aware(date_mvt),
                    )
                    stock_actuel -= qte_sortie
                    total_mouvements += 1
                    reste -= qte_sortie
                else:
                    # Réapprovisionnement
                    besoin = conso_mois * random.randint(2, 4)
                    prix = produit.prix_unitaire * Decimal(random.uniform(0.94, 1.08))
                    date_entree = datetime(annee, mois, jour, 8, random.randint(0,59))
                    Mouvement.objects.create(
                        type_mouvement=random.choice(types_entree),
                        produit=produit,
                        quantite=Decimal(besoin),
                        entrepot_destination=entrepot,
                        utilisateur=random.choice(utilisateurs),
                        reference=f"REAP-{produit.sku}-{date_entree.strftime('%Y%m%d')}",
                        date_mouvement=timezone.make_aware(date_entree),
                        prix_unitaire_snapshot=prix,
                    )
                    stock_actuel += besoin
                    total_mouvements += 1
                    # Tenter à nouveau la sortie
                    if stock_actuel >= qte_sortie:
                        date_mvt = datetime(annee, mois, jour, random.randint(14, 17), random.randint(0,59))
                        Mouvement.objects.create(
                            type_mouvement=random.choice(types_sortie),
                            produit=produit,
                            quantite=Decimal(qte_sortie),
                            entrepot_source=entrepot,
                            utilisateur=random.choice(utilisateurs),
                            reference=f"SORT-{produit.sku}-{date_mvt.strftime('%Y%m%d')}",
                            date_mouvement=timezone.make_aware(date_mvt),
                        )
                        stock_actuel -= qte_sortie
                        total_mouvements += 1
                        reste -= qte_sortie
            
            # Fin de mois: réappro si stock bas
            if stock_actuel < conso_base * 1.5:
                besoin = conso_base * random.randint(3, 6)
                prix = produit.prix_unitaire * Decimal(random.uniform(0.96, 1.04))
                dernier_jour = datetime(annee, mois, nb_jours, 23, 59)
                Mouvement.objects.create(
                    type_mouvement=TypeMouvement.ENTREE,
                    produit=produit,
                    quantite=Decimal(besoin),
                    entrepot_destination=entrepot,
                    utilisateur=random.choice(utilisateurs),
                    reference=f"FINMOIS-{produit.sku}-{dernier_jour.strftime('%Y%m%d')}",
                    date_mouvement=timezone.make_aware(dernier_jour),
                    prix_unitaire_snapshot=prix,
                )
                stock_actuel += besoin
                total_mouvements += 1
            
            # Mois suivant
            if mois == 12:
                current_date = date(annee+1, 1, 1)
            else:
                current_date = date(annee, mois+1, 1)
        
        # Stock final
        stock_final = max(Decimal(0), stock_actuel)
        stock_obj, _ = Stock.objects.get_or_create(
            produit=produit,
            entrepot=entrepot,
            defaults={"quantite": Decimal(0)}
        )
        stock_obj.quantite = stock_final
        stock_obj.save()
    
    print(f"   ✅ {total_mouvements} mouvements générés")

@transaction.atomic
def creer_alertes(produits):
    print("\n🔔 Génération des alertes basées sur stock réel...")
    nb = 0
    for p in produits:
        qte = p.quantite_totale()
        seuil = p.seuil_alerte
        if qte == 0:
            Alerte.objects.create(
                produit=p,
                type_alerte=TypeAlerte.RUPTURE,
                priorite=PrioriteAlerte.CRITIQUE,
                message=f"Rupture totale de {p.nom} (stock=0)",
                lue=False,
            )
            nb += 1
        elif qte <= seuil and seuil > 0:
            Alerte.objects.create(
                produit=p,
                type_alerte=TypeAlerte.SEUIL_BAS,
                priorite=PrioriteAlerte.HAUTE,
                message=f"Stock faible: {p.quantite_totale()} ≤ seuil {seuil}",
                lue=False,
            )
            nb += 1
    print(f"   ✅ {nb} alertes actives")

@transaction.atomic
def creer_bons_commande(produits, fournisseurs, users, entreprise):
    print("\n🛒 Création de 200 bons de commande...")
    utilisateur = users.get(RoleUtilisateur.RESPONSABLE_ACHAT) or list(users.values())[0]
    nb_bc = 0
    for _ in range(200):
        fournisseur = random.choice(fournisseurs)
        date_comm = random_date_between(DATE_DEBUT, DATE_FIN)
        statut = random.choice([StatutBonCommande.ENVOYE, StatutBonCommande.RECU_COMPLET, StatutBonCommande.CLOTURE])
        entrepot = random.choice(Entrepot.objects.filter(entreprise=entreprise))
        bc = BonCommande.objects.create(
            fournisseur=fournisseur,
            statut=statut,
            date_commande=timezone.make_aware(datetime.combine(date_comm, datetime.min.time())),
            utilisateur_createur=utilisateur,
            entrepot_destination=entrepot,
            entreprise=entreprise,
            note="Commande alimentaire"
        )
        nb_lignes = random.randint(1, 8)
        for p in random.sample(produits, min(nb_lignes, len(produits))):
            qte = random.randint(10, 200)
            pu = p.prix_unitaire * Decimal(random.uniform(0.92, 1.08))
            LigneCommande.objects.create(
                bon_commande=bc,
                produit=p,
                quantite_commandee=Decimal(qte),
                prix_unitaire_ht=pu,
            )
        nb_bc += 1
    print(f"   ✅ {nb_bc} bons de commande")

@transaction.atomic
def creer_inventaires_et_scans(produits, users, entrepots):
    print("\n📷 Création de sessions d'inventaire et logs de scan...")
    utilisateur = users.get(RoleUtilisateur.MAGASINIER) or list(users.values())[0]
    # Scans
    for _ in range(300):
        produit = random.choice(produits)
        ScanLog.objects.create(
            utilisateur=utilisateur,
            produit=produit,
            code_barre_scanne=produit.code_barres or "0000000000",
            action_attendue=random.choice(["entree", "sortie", "inventaire"]),
            succes=True,
        )
    print("   ✅ 300 scans créés")
    
    # Une session d'inventaire par entrepôt
    for entrepot in entrepots:
        session = InventaireSession.objects.create(
            entrepot=entrepot,
            utilisateur_demarrage=utilisateur,
            date_debut=timezone.now() - timedelta(days=random.randint(1, 60)),
            note="Inventaire annuel"
        )
        stocks = Stock.objects.filter(entrepot=entrepot).select_related('produit', 'emplacement')
        for s in stocks:
            ecart = Decimal(random.uniform(-0.15, 0.15)) * s.quantite
            qte_comptee = max(Decimal(0), s.quantite + ecart)
            LigneInventaire.objects.create(
                session=session,
                produit=s.produit,
                emplacement=s.emplacement,
                quantite_theorique=s.quantite,
                quantite_comptee=qte_comptee,
            )
        session.date_fin = timezone.now()
        session.statut = random.choice(["valide", "en_cours"])
        session.save()
    print("   ✅ Sessions d'inventaire créées")

@transaction.atomic
def creer_predictions_ia(produits):
    print("\n🤖 Génération de prédictions IA...")
    nb = 0
    for p in random.sample(produits, min(50, len(produits))):
        for delta in [7, 30, 60]:
            date_cible = DATE_FIN + timedelta(days=delta)
            qte_actuelle = p.quantite_totale()
            qte_prevue = max(Decimal(0), qte_actuelle * Decimal(random.uniform(0.7, 1.3)))
            PredictionStock.objects.create(
                produit=p,
                date_cible=date_cible,
                quantite_prevue=qte_prevue,
                borne_inferieure=qte_prevue * Decimal(0.8),
                borne_superieure=qte_prevue * Decimal(1.2),
                confiance=round(random.uniform(0.65, 0.95), 2),
                modele_utilise="prophet",
                quantite_recommandee_commande=max(Decimal(0), (qte_prevue - qte_actuelle) * Decimal(1.2))
            )
            nb += 1
    print(f"   ✅ {nb} prédictions générées")

@transaction.atomic
def creer_auditlogs_notifications(users, entreprise):
    print("\n📝 Création de logs d'audit et notifications...")
    
    # Logs d'audit (sans request)
    for _ in range(500):
        user = random.choice(list(users.values()))
        type_action = random.choice([t for t in TypeAction if t not in [TypeAction.AUTRE]])
        # Création directe sans utiliser .log()
        AuditLog.objects.create(
            utilisateur=user,
            entreprise=entreprise,
            type_action=type_action,
            description=f"Action {type_action} simulée",
            ip_address='127.0.0.1',       # IP fictive
            user_agent='seed-script',
            objet_type='',
            objet_id='',
            donnees_avant=None,
            donnees_apres=None,
            created_at=timezone.now() - timedelta(days=random.randint(0, 365))
        )
    print("   ✅ 500 logs d'audit")
    
    # Notifications (inchangé)
    for user in users.values():
        for _ in range(random.randint(1, 5)):
            Notification.objects.create(
                destinataire=user,
                type_notif=random.choice([t[0] for t in Notification.TypeNotif.choices]),
                titre=f"Notification {random.choice(['stock', 'commande', 'IA'])}",
                message="Ceci est une notification automatique.",
                lue=random.choice([True, False]),
                lien="/gestionnaire/"
            )
    print("   ✅ Notifications créées")

# ============================================================================
# MAIN
# ============================================================================
def run():
    print("=" * 70)
    print("  SEED GROS DISTRIBUTION - ALIMENTATION GÉNÉRALE (100 produits, 5 ans)")
    print("=" * 70)
    
    entreprise = get_or_create_entreprise()
    clear_company_data(entreprise)
    
    categories = creer_categories(entreprise)
    fournisseurs = creer_fournisseurs(entreprise)
    entrepots = creer_entrepots_emplacements(entreprise)
    users = creer_utilisateurs(entreprise)
    produits = creer_produits(categories, fournisseurs, entreprise)
    
    creer_mouvements_et_stock(produits, entrepots, users)
    creer_alertes(produits)
    creer_bons_commande(produits, fournisseurs, users, entreprise)
    creer_inventaires_et_scans(produits, users, entrepots)
    creer_predictions_ia(produits)
    creer_auditlogs_notifications(users, entreprise)
    
    print("\n" + "=" * 70)
    print("  ✅ SEED TERMINÉ AVEC SUCCÈS")
    print("=" * 70)
    print(f"""
  Résumé :
  - Entreprise : {entreprise.nom} ({entreprise.get_type_entreprise_display()})
  - Utilisateurs : {len(UTILISATEURS_ROLES)}
  - Catégories : {len(CATEGORIES_DATA)}
  - Fournisseurs : {len(FOURNISSEURS_DATA)}
  - Entrepôts : 3 avec emplacements
  - Produits : {len(produits)} (100)
  - Mouvements : sur 60 mois (stock final cohérent)
  - Alertes : basées sur stock réel
  - Bons de commande : 200
  - Scans : 300
  - Inventaires : 3 sessions
  - Prédictions IA : 150
  - Logs audit : 500
  - Notifications : ~20
  """)
    print("  Vous pouvez vous connecter avec :")
    for prefix, role, _, _ in UTILISATEURS_ROLES:
        print(f"   {prefix}@stockmaster.tg / StockMaster2024! ({role})")

if __name__ == "__main__":
    run()