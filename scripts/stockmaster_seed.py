import os
import django
import random
import uuid
from datetime import datetime, timedelta, date
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

from apps.entreprises.models import Entreprise, TypeEntreprise
from apps.accounts.models import Utilisateur, RoleUtilisateur
from apps.stock.models import (
    Categorie, Produit, UniteMesure,
    Entrepot, Emplacement, Stock,
    Mouvement, TypeMouvement,
    Fournisseur, BonCommande, StatutBonCommande, LigneCommande,
    Alerte, TypeAlerte, PrioriteAlerte,
    PredictionStock
)
from apps.core.models import AuditLog, TypeAction

User = get_user_model()

# ============================================================================
# DONNÉES DE RÉFÉRENCE (inchangées)
# ============================================================================

CATEGORIES_DATA = [
    {"nom": "Électronique & Informatique",  "parent": None},
    {"nom": "Fournitures de Bureau",         "parent": None},
    {"nom": "Matériel Industriel",           "parent": None},
    {"nom": "Consommables & Papeterie",      "parent": None},
    {"nom": "Mobilier & Aménagement",        "parent": None},
    {"nom": "Hygiène & Entretien",           "parent": None},
]

FOURNISSEURS_DATA = [
    {"nom": "TechDistrib Afrique",      "pays": "Togo",      "delai_moyen_jours": 5},
    {"nom": "Bureau Plus Togo",         "pays": "Togo",      "delai_moyen_jours": 3},
    {"nom": "Industria West Africa",    "pays": "Bénin",     "delai_moyen_jours": 7},
    {"nom": "ConsomPro Sénégal",        "pays": "Sénégal",   "delai_moyen_jours": 10},
    {"nom": "MeubleForm CI",            "pays": "Côte d'Ivoire", "delai_moyen_jours": 14},
    {"nom": "ProHygiène Ghana",         "pays": "Ghana",     "delai_moyen_jours": 8},
    {"nom": "GlobalStock Import",       "pays": "France",    "delai_moyen_jours": 21},
    {"nom": "AsiaConnect Trading",      "pays": "Hong Kong", "delai_moyen_jours": 30},
]

ENTREPOTS_DATA = [
    {"nom": "Entrepôt Principal Lomé",  "ville": "Lomé", "pays": "Togo", "est_actif": True},
    {"nom": "Entrepôt Secondaire Nord", "ville": "Lomé", "pays": "Togo", "est_actif": True},
    {"nom": "Magasin Central Bureau",   "ville": "Lomé", "pays": "Togo", "est_actif": True},
]

PRODUITS_DATA = {
    "Électronique & Informatique": [
        ("Ordinateur portable 15\" i5",   "unite", 350000, 480000, 5,  20),
        ("Ordinateur portable 15\" i7",   "unite", 480000, 650000, 3,  15),
        ("Écran LCD 24 pouces",           "unite", 85000,  130000, 5,  25),
        ("Imprimante laser A4",           "unite", 95000,  140000, 3,  12),
        ("Clavier sans fil",              "unite", 8500,   15000,  10, 50),
        ("Souris optique sans fil",       "unite", 5500,   12000,  10, 60),
        ("Disque dur externe 1To",        "unite", 35000,  55000,  5,  30),
        ("Clé USB 64 Go",                 "unite", 5000,   10000,  20, 100),
        ("Routeur Wi-Fi",                 "unite", 25000,  45000,  3,  15),
        ("Webcam HD 1080p",               "unite", 18000,  35000,  5,  25),
    ],
    "Fournitures de Bureau": [
        ("Stylo bille bleu (boîte 50)",   "boite", 3500,   6500,   10, 50),
        ("Stylo bille noir (boîte 50)",   "boite", 3500,   6500,   10, 50),
        ("Marqueur permanent noir",       "unite", 500,    1200,   30, 150),
        ("Agrafeuse de bureau",           "unite", 5500,   12000,  5,  25),
        ("Calculatrice scientifique",     "unite", 8500,   18000,  5,  25),
        ("Bloc-notes A5 (lot 5)",         "lot",   3500,   7000,   10, 50),
        ("Classeur à levier A4",          "unite", 2500,   5000,   15, 80),
        ("Scotch transparent (lot 6)",    "lot",   2500,   5000,   10, 60),
        ("Ciseaux de bureau",             "unite", 2000,   4500,   8,  35),
    ],
    "Matériel Industriel": [
        ("Tournevis cruciforme set 6",    "set",   8500,   18000,  5,  25),
        ("Perceuse électrique 750W",      "unite", 55000,  90000,  2,  10),
        ("Casque de protection",          "unite", 8000,   18000,  5,  30),
        ("Gants de travail (paire)",      "paire", 2500,   6000,   20, 100),
        ("Extincteur 6kg ABC",            "unite", 45000,  75000,  3,  15),
        ("Palette bois 80x120cm",         "unite", 6500,   12000,  10, 60),
        ("Transpalette manuel 2T",        "unite", 185000, 280000, 1,  4),
    ],
    "Consommables & Papeterie": [
        ("Ramette papier A4 80g",         "ramette", 3500, 5500, 30, 200),
        ("Cartouche encre HP noir",       "unite", 18000, 28000, 8,  40),
        ("Toner laser Brother noir",      "unite", 28000, 45000, 5,  25),
        ("Enveloppe C4 (boîte 250)",      "boite", 9500,  16000, 5,  30),
        ("Post-it 76x76 (lot 12)",        "lot",   4500,  8500,  10, 50),
        ("Pile AA (lot 24)",              "lot",   5500,  10000, 10, 60),
    ],
    "Mobilier & Aménagement": [
        ("Bureau manager 160x80cm",       "unite", 185000, 280000, 1,  6),
        ("Chaise de direction",           "unite", 125000, 200000, 2,  10),
        ("Armoire métallique 2 portes",   "unite", 145000, 220000, 1,  6),
        ("Tableau blanc 120x90cm",        "unite", 45000,  80000,  2,  10),
        ("Caisson mobile 3 tiroirs",      "unite", 75000,  120000, 2,  10),
    ],
    "Hygiène & Entretien": [
        ("Savon désinfectant 5L",         "bidon", 8500,  15000, 10, 60),
        ("Gel hydroalcoolique 1L",        "unite", 5500,  10000, 15, 80),
        ("Papier toilette (lot 48)",      "lot",   12000, 20000, 5,  30),
        ("Sac poubelle 50L (lot 50)",     "lot",   6500,  12000, 10, 60),
        ("Détergent sol 5L",              "bidon", 9500,  17000, 8,  40),
        ("Balai frange + seau",           "set",   12000, 22000, 3,  15),
    ],
}

for cat in PRODUITS_DATA:
    original = PRODUITS_DATA[cat]
    extended = []
    for _ in range(2):       
        extended.extend(original)
    PRODUITS_DATA[cat] = extended

UTILISATEURS_DATA = [
    {"email": "admin@stockmaster.tg",     "role": RoleUtilisateur.ADMIN_ENT,    "first_name": "Kofi",    "last_name": "MENSAH",    "password": "StockMaster2024!"},
    {"email": "gestionnaire@stockmaster.tg", "role": RoleUtilisateur.GESTIONNAIRE, "first_name": "Akosua",  "last_name": "KOFFI",     "password": "StockMaster2024!"},
    {"email": "achat@stockmaster.tg",     "role": RoleUtilisateur.RESPONSABLE_ACHAT, "first_name": "Ama",     "last_name": "DOSSOU",    "password": "StockMaster2024!"},
    {"email": "magasinier@stockmaster.tg","role": RoleUtilisateur.MAGASINIER,   "first_name": "Etonam",  "last_name": "FIAMOR",    "password": "StockMaster2024!"},
    {"email": "auditeur@stockmaster.tg",  "role": RoleUtilisateur.AUDITEUR,     "first_name": "Afua",    "last_name": "GBEKU",     "password": "StockMaster2024!"},
    {"email": "comptable@stockmaster.tg", "role": RoleUtilisateur.COMPTABLE,    "first_name": "Koffi",   "last_name": "ABALO",     "password": "StockMaster2024!"},
]
 
# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def rand_date(start_days_ago, end_days_ago=0):
    start = timezone.now() - timedelta(days=start_days_ago)
    end = timezone.now() - timedelta(days=end_days_ago)
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))

def get_or_create_entreprise():
    entreprise, created = Entreprise.objects.get_or_create(
        nom="StockMaster Démo",
        defaults={
            "type_entreprise": TypeEntreprise.COMMERCE_DETAIL,
            "pays": "Togo",
            "ville": "Lomé",
            "taille": "10-50",
            "nb_entrepots": 3,
            "est_active": True,
        }
    )
    if created:
        print("   ✅ Entreprise de démonstration créée")
    else:
        print("   ⏭️ Entreprise déjà existante")
    return entreprise

# ============================================================================
# CRÉATEURS
# ============================================================================

@transaction.atomic
def creer_utilisateurs(entreprise):
    print("\n👤 Création des utilisateurs...")
    users = {}
    for data in UTILISATEURS_DATA:
        user, created = Utilisateur.objects.get_or_create(
            email=data["email"],
            defaults={
                "username": data["email"],
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "role": data["role"],
                "entreprise": entreprise,
                "est_actif": True,
                "is_active": True,
            }
        )
        if created:
            user.set_password(data["password"])
            user.save()
            print(f"   ✅ {user.email} ({user.get_role_display()})")
        else:
            print(f"   ⏭️ {user.email} existe déjà")
        users[data["role"]] = user
    return users

@transaction.atomic
def creer_categories(entreprise):
    print("\n📦 Création des catégories...")
    cats = {}
    for data in CATEGORIES_DATA:
        cat, created = Categorie.objects.get_or_create(
            nom=data["nom"],
            entreprise=entreprise,   # ← CORRECTION OBLIGATOIRE
            defaults={"description": f"Catégorie {data['nom']}"}
        )
        cats[data["nom"]] = cat
        print(f"   {'✅' if created else '⏭️'} {cat.nom}")
    return cats

@transaction.atomic
def creer_fournisseurs(entreprise):
    print("\n🏭 Création des fournisseurs...")
    fournisseurs = []
    for data in FOURNISSEURS_DATA:
        f, created = Fournisseur.objects.get_or_create(
            nom=data["nom"],
            entreprise=entreprise,
            defaults={
                "pays": data["pays"],
                "delai_moyen_jours": data["delai_moyen_jours"],
                "est_actif": True,
            }
        )
        fournisseurs.append(f)
        print(f"   {'✅' if created else '⏭️'} {f.nom}")
    return fournisseurs

@transaction.atomic
def creer_entrepots(entreprise):
    print("\n🏗️ Création des entrepôts...")
    entrepots = []
    for data in ENTREPOTS_DATA:
        e, created = Entrepot.objects.get_or_create(
            nom=data["nom"],
            entreprise=entreprise,
            defaults={
                "ville": data["ville"],
                "pays": data["pays"],
                "est_actif": data["est_actif"],
            }
        )
        entrepots.append(e)
        print(f"   {'✅' if created else '⏭️'} {e.nom}")
    return entrepots

@transaction.atomic
def creer_produits(categories, fournisseurs, entreprise):
    print("\n📊 Création des produits...")
    produits = []
    fournisseur_map = {cat: fournisseurs[:] for cat in categories.values()}
    
    # Consommation moyenne mensuelle estimée par catégorie (en unités)
    conso_moyenne_par_categorie = {
        "Électronique & Informatique": 15,
        "Fournitures de Bureau": 30,
        "Matériel Industriel": 10,
        "Consommables & Papeterie": 50,
        "Mobilier & Aménagement": 5,
        "Hygiène & Entretien": 25,
    }
    
    for cat_name, items in PRODUITS_DATA.items():
        cat = categories.get(cat_name)
        if not cat:
            continue
        conso_moyenne = conso_moyenne_par_categorie.get(cat_name, 20)
        fours = fournisseur_map.get(cat, fournisseurs)
        for (nom, unite, prix_min, prix_max, _, _) in items:
            sku = f"{cat_name[:3].upper()}-{random.randint(1000, 9999)}"
            prix_unitaire = Decimal(random.randint(prix_min, prix_max))
            # Seuil d'alerte = entre 30% et 70% de la consommation mensuelle (au moins 5)
            seuil_alerte = max(5, int(conso_moyenne * random.uniform(0.3, 0.7)))
            produit, created = Produit.objects.get_or_create(
                sku=sku,
                entreprise=entreprise,
                defaults={
                    "nom": nom,
                    "unite_mesure": unite,
                    "prix_unitaire": prix_unitaire,
                    "seuil_alerte": seuil_alerte,
                    "categorie": cat,
                    "fournisseur_principal": random.choice(fours) if fours else None,
                    "est_actif": True,
                }
            )
            produits.append(produit)
    print(f"   ✅ {len(produits)} produits créés")
    return produits

def _mettre_a_jour_stock(produit, entrepot, delta):
    """Met à jour la table Stock pour un produit dans un entrepôt."""
    stock, _ = Stock.objects.get_or_create(
        produit=produit,
        entrepot=entrepot,
        defaults={"quantite": Decimal(0)}
    )
    stock.quantite = max(Decimal(0), stock.quantite + delta)
    stock.save()
    return stock.quantite

@transaction.atomic
def creer_mouvements_historiques(produits, entrepots, users, entreprise):
    print("\n📈 Génération des mouvements historiques (36 mois, dense, prix variants)...")
    types_entree = [TypeMouvement.ENTREE, TypeMouvement.RETOUR]
    types_sortie = [TypeMouvement.SORTIE, TypeMouvement.PERTE]
    utilisateurs = list(users.values())
    total_mvts = 0
    today = date.today()
    
    # Saisonnalité
    saisonnalite = [1.2, 1.0, 1.0, 1.0, 0.9, 0.7, 0.6, 0.7, 0.8, 1.0, 1.1, 1.3]

    for produit in produits:
        entrepot = random.choice(entrepots)
        stock_actuel = Decimal(0)
        
        # Consommation journalière moyenne selon catégorie
        if produit.categorie:
            if "Bureau" in produit.categorie.nom:
                conso_moyenne = random.randint(20, 40)
            elif "Électronique" in produit.categorie.nom:
                conso_moyenne = random.randint(10, 20)
            elif "Hygiène" in produit.categorie.nom:
                conso_moyenne = random.randint(15, 30)
            else:
                conso_moyenne = random.randint(5, 25)
        else:
            conso_moyenne = random.randint(5, 25)
            
        variation = random.uniform(0.2, 0.4)
        trend = random.uniform(0.96, 1.04)
        prix_achat_base = float(produit.prix_unitaire)

        for mois in range(36, 0, -1):
            mois_date = today.replace(day=1) - timedelta(days=mois * 30)
            mois_idx = mois_date.month - 1
            coeff_saison = saisonnalite[mois_idx]
            
            conso_base = conso_moyenne * 30 * coeff_saison * trend
            conso_reelle = max(10, int(conso_base * random.gauss(1.0, variation)))
            
            reste = conso_reelle
            jours_mois = (mois_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            nb_jours = jours_mois.day
            
            for jour in range(1, nb_jours+1):
                if reste <= 0:
                    break
                qte_jour = min(reste, max(1, int(conso_reelle / nb_jours * random.uniform(0.5, 1.5))))
                reste -= qte_jour
                if qte_jour == 0:
                    continue
                
                # Réapprovisionnement si le stock ne suffit pas
                if stock_actuel < qte_jour:
                    besoin = max(qte_jour * 2, conso_reelle // 2)
                    variation_prix = random.uniform(0.90, 1.10)
                    prix_snapshot = Decimal(prix_achat_base * variation_prix)
                    mvt_date = mois_date + timedelta(days=jour-1, hours=8, minutes=random.randint(0,59))
                    Mouvement.objects.create(
                        type_mouvement=random.choice(types_entree),
                        produit=produit,
                        quantite=Decimal(besoin),
                        entrepot_destination=entrepot,
                        utilisateur=random.choice(utilisateurs),
                        reference=f"AUTO-ENTREE-{random.randint(1000,9999)}",
                        date_mouvement=timezone.make_aware(datetime.combine(mvt_date, datetime.min.time())),
                        prix_unitaire_snapshot=prix_snapshot,
                    )
                    stock_actuel += Decimal(besoin)
                    total_mvts += 1
                
                # Sortie
                if stock_actuel >= qte_jour:
                    mvt_date = mois_date + timedelta(days=jour-1, hours=random.randint(7,18), minutes=random.randint(0,59))
                    Mouvement.objects.create(
                        type_mouvement=random.choice(types_sortie),
                        produit=produit,
                        quantite=Decimal(qte_jour),
                        entrepot_source=entrepot,
                        utilisateur=random.choice(utilisateurs),
                        reference=f"AUTO-SORTIE-{random.randint(1000,9999)}",
                        date_mouvement=timezone.make_aware(datetime.combine(mvt_date, datetime.min.time())),
                    )
                    stock_actuel -= Decimal(qte_jour)
                    total_mvts += 1
            
            # Fin de mois : réapprovisionnement si stock faible
            if stock_actuel < conso_moyenne * 15:
                besoin = conso_moyenne * 30
                variation_prix = random.uniform(0.95, 1.05)
                prix_snapshot = Decimal(prix_achat_base * variation_prix)
                mvt_date = mois_date + timedelta(days=nb_jours, hours=23, minutes=59)
                Mouvement.objects.create(
                    type_mouvement=random.choice(types_entree),
                    produit=produit,
                    quantite=Decimal(besoin),
                    entrepot_destination=entrepot,
                    utilisateur=random.choice(utilisateurs),
                    reference=f"AUTO-ENTREE-FINMOIS-{random.randint(1000,9999)}",
                    date_mouvement=timezone.make_aware(datetime.combine(mvt_date, datetime.min.time())),
                    prix_unitaire_snapshot=prix_snapshot,
                )
                stock_actuel += Decimal(besoin)
                total_mvts += 1

            # Évolution des prix et tendance
            prix_achat_base *= random.uniform(0.98, 1.02)
            trend *= 1.0 + (random.random() - 0.5) * 0.05
        
        # Enregistrement du stock final
        stock_obj, _ = Stock.objects.get_or_create(produit=produit, entrepot=entrepot, defaults={"quantite": Decimal(0)})
        stock_obj.quantite = max(Decimal(0), stock_actuel)
        stock_obj.save()
    
    print(f"   ✅ {total_mvts} mouvements générés")
    return total_mvts

@transaction.atomic
def creer_bons_commande(produits, fournisseurs, users, entreprise):
    print("\n🛒 Génération des bons de commande...")
    statuts = [StatutBonCommande.ENVOYE, StatutBonCommande.RECU_PARTIEL, StatutBonCommande.RECU_COMPLET, StatutBonCommande.CLOTURE]
    utilisateur = list(users.values())[0] if users else None
    nb_bc = 0

    for i in range(200):
        fournisseur = random.choice(fournisseurs)
        date_commande = rand_date(540, 1)
        statut = random.choice(statuts)
        entrepot = random.choice(Entrepot.objects.filter(entreprise=entreprise))

        bc = BonCommande.objects.create(
            fournisseur=fournisseur,
            statut=statut,
            date_commande=date_commande,
            utilisateur_createur=utilisateur,
            entrepot_destination=entrepot,
            entreprise=entreprise,
        )
        nb_lignes = random.randint(1, 5)
        lignes_produits = random.sample(produits, min(nb_lignes, len(produits)))
        for p in lignes_produits:
            qte = random.randint(5, 50)
            pu = p.prix_unitaire * Decimal(str(round(random.uniform(0.95, 1.05), 2)))
            LigneCommande.objects.create(
                bon_commande=bc,
                produit=p,
                quantite_commandee=Decimal(qte),
                prix_unitaire_ht=pu,
            )
        nb_bc += 1

    print(f"   ✅ {nb_bc} bons de commande créés")
    return nb_bc

@transaction.atomic
def creer_alertes(produits, entreprise):
    print("\n🔔 Génération des alertes...")
    nb_alertes = 0
    for produit in produits:
        stock_total = sum(s.quantite for s in produit.stocks.all())
        if stock_total <= produit.seuil_alerte:
            type_alerte = TypeAlerte.RUPTURE if stock_total == 0 else TypeAlerte.SEUIL_BAS
            priorite = PrioriteAlerte.CRITIQUE if stock_total == 0 else PrioriteAlerte.HAUTE
            Alerte.objects.get_or_create(
                produit=produit,
                type_alerte=type_alerte,
                defaults={
                    "message": f"Stock de {produit.nom} : {stock_total} {produit.unite_mesure} (seuil {produit.seuil_alerte})",
                    "priorite": priorite,
                    "lue": False,
                }
            )
            nb_alertes += 1
    print(f"   ✅ {nb_alertes} alertes créées")
    return nb_alertes

# ============================================================================
# MAIN
# ============================================================================

def run():
    print("=" * 60)
    print("  STOCKMASTER — SEEDER V2.0")
    print("=" * 60)
    random.seed(42)

    entreprise = get_or_create_entreprise()
    users = creer_utilisateurs(entreprise)
    categories = creer_categories(entreprise)   # ← CORRECTION : passe l'entreprise
    fournisseurs = creer_fournisseurs(entreprise)
    entrepots = creer_entrepots(entreprise)
    produits = creer_produits(categories, fournisseurs, entreprise)
    creer_mouvements_historiques(produits, entrepots, users, entreprise)
    creer_bons_commande(produits, fournisseurs, users, entreprise)
    creer_alertes(produits, entreprise)

    print("\n" + "=" * 60)
    print("  ✅ SEEDER TERMINÉ")
    print("=" * 60)
    print(f"""
  Résumé :
  - Entreprise : {entreprise.nom}
  - Utilisateurs : {len(UTILISATEURS_DATA)}
  - Catégories : {len(CATEGORIES_DATA)}
  - Fournisseurs : {len(FOURNISSEURS_DATA)}
  - Entrepôts : {len(ENTREPOTS_DATA)}
  - Produits : {len(produits)}
  - Mouvements : ~ générés
  - Bons de commande : 200
  - Alertes : ~ générées
  """)

if __name__ == "__main__":
    run()