# 📦 STOCKMASTER – Guide complet de l’application

**StockMaster** est une solution web intelligente de gestion de stock destinée aux PME/ETI.  
Elle intègre un suivi multi‑entrepôts, des mouvements de stock, des alertes, des prédictions IA, plusieurs rôles utilisateurs, une API REST et une PWA mobile.

---

## 1. Architecture générale

- **Backend** : Django 5, PostgreSQL, Celery + Redis
- **Frontend** : Tailwind CSS, ShadCN, Font Awesome
- **Mobile** : PWA (Progressive Web App) + Service Worker
- **IA** : Prophet / RandomForest pour les prédictions de consommation

---

## 2. Rôles utilisateurs et leurs actions

### 2.1 Super Admin (gestionnaire global)

- Créer / activer / désactiver des entreprises
- Gérer tous les utilisateurs (toutes entreprises)
- Changer le rôle d’un utilisateur
- Consulter les logs d’audit
- Voir le dashboard global (stats, dernières entreprises, utilisateurs)
- Lancer des analyses IA pour toutes les entreprises (si besoin)

### 2.2 Admin Entreprise

- Gérer ses propres utilisateurs (invitation, désactivation, suppression, modification de rôle)
- Gérer les entrepôts de son entreprise (CRUD)
- Gérer les catégories de produits
- Voir les alertes de stock
- Consulter les rapports et exports (CSV)
- Lancer l’analyse IA pour ses produits
- Modifier les informations de son entreprise

### 2.3 Gestionnaire de stock

- CRUD complet des produits (créer, modifier, désactiver, importer/exporter CSV)
- Enregistrer des mouvements de stock (entrée, sortie, transfert, ajustement)
- Créer et valider des inventaires physiques (sessions de comptage)
- Acquitter des alertes
- Consulter l’historique des mouvements
- Gérer les emplacements dans les entrepôts
- Scanner des codes‑barres (recherche rapide)
- Voir la valorisation du stock (simple)

### 2.4 Responsable achat

- Gérer les fournisseurs (CRUD)
- Créer des bons de commande (BC) avec workflow :
  - Brouillon → Envoyé → Réception partielle → Réception complète → Clôturé
- Réceptionner des commandes (saisie partielle, génération automatique de mouvements d’entrée)
- Voir les suggestions d’achat basées sur l’IA
- Consulter les prédictions de consommation (graphiques, score de confiance)
- Exporter les commandes et fournisseurs en CSV

### 2.5 Magasinier (mobile / terrain)

- Scanner des codes‑barres pour :
  - Rechercher un produit
  - Enregistrer une entrée ou sortie rapide (avec choix de l’entrepôt)
- Consulter le stock actuel par produit/entrepôt
- Participer aux inventaires (saisir les quantités comptées sans valider)
- Voir l’historique de ses scans (session)
- Mode hors ligne : les mouvements sont stockés et synchronisés à la reconnexion

### 2.6 Auditeur (lecture seule)

- Consulter tous les mouvements de stock (filtres, exports)
- Voir les écarts d’inventaire
- Consulter les logs d’audit (actions de tous les utilisateurs)
- Rapports de valorisation
- Indicateurs de conformité (taux de référence documentée, …)

### 2.7 Comptable

- Valorisation du stock (méthodes CUMP et FIFO)
- Suivi des marges (si prix de vente renseigné)
- Historique des prix d’achat (à partir des mouvements et BC)
- Dépréciation des stocks inactifs (taux progressif)
- Exports comptables (CSV, PDF)
- Rapports périodiques (stock début, entrées, sorties, stock fin)

---

## 3. Gestion du stock – Flux métier

### 3.1 Produits

- Chaque produit a un SKU unique, une unité de mesure, un seuil d’alerte, un prix unitaire, un code‑barres optionnel.
- Il est rattaché à une catégorie et à une entreprise (multi‑tenant).

### 3.2 Entrepôts et emplacements

- Une entreprise peut avoir plusieurs entrepôts.
- Dans chaque entrepôt, on peut définir des emplacements (allées, racks, casiers) pour un stockage fin.

### 3.3 Stock physique (table `Stock`)

- Un enregistrement `Stock` lie un **produit**, un **entrepôt** (et éventuellement un **emplacement**) à une **quantité actuelle**.
- Cette table est mise à jour automatiquement à chaque mouvement.

### 3.4 Mouvements de stock (table `Mouvement`)

- **Type de mouvement** : entrée, sortie, transfert, ajustement, retour, perte.
- Chaque mouvement enregistre : produit, quantité, entrepôt source/destination, utilisateur, référence, note, date, prix unitaire instantané (snapshot).
- Les mouvements ne sont jamais supprimés (journal d’audit).

#### 3.4.1 Entrée

- **Déclencheurs** : création manuelle par gestionnaire, réception de bon de commande (responsable achat), scan par magasinier.
- **Effet** : augmente la quantité du produit dans l’entrepôt destination (et éventuellement l’emplacement).

#### 3.4.2 Sortie

- **Déclencheurs** : ventes, consommation interne, perte, ajustement négatif.
- **Vérification** : le stock source doit être suffisant. Si insuffisant, un message d’erreur est renvoyé.
- **Effet** : diminue la quantité dans l’entrepôt source.

#### 3.4.3 Transfert

- Nécessite un entrepôt source et un entrepôt destination.
- Crée deux mouvements logiques (sortie de source, entrée dans destination) mais un seul enregistrement avec les deux références.
- **Vérification** : stock source suffisant.

#### 3.4.4 Ajustement

- Utilisé lors des inventaires validés (écart entre théorique et réel).
- Peut être positif (ajout) ou négatif (retrait).

### 3.5 Alertes de stock

- Créées automatiquement lorsqu’un mouvement amène le stock total d’un produit sous son seuil d’alerte.
- Types : `rupture` (stock = 0), `seuil_bas` (stock ≤ seuil), `predictive` (prédiction IA), `expiration` (date approchante).
- Priorités : critique, haute, moyenne, basse.
- Les alertes peuvent être acquittées par le gestionnaire ou le responsable achat.

### 3.6 Inventaires physiques

- **Création** : choisir un entrepôt → le système pré‑remplit une session avec tous les produits de l’entrepôt et leur stock théorique.
- **Saisie** : les magasiniers (ou gestionnaires) renseignent les quantités comptées pour chaque produit.
- **Validation** : un gestionnaire valide la session. Les écarts sont transformés en mouvements d’ajustement ; le stock réel est mis à jour.

---

## 4. Bons de commande et réception

### 4.1 Workflow

1. **Brouillon** : création par responsable achat (sélection des produits, quantités, prix).
2. **Envoyé** : basculement manuel après envoi au fournisseur.
3. **Réception partielle** : saisie des quantités reçues (possible en plusieurs fois). À chaque réception, des mouvements d’entrée sont créés et le stock est mis à jour.
4. **Réception complète** : toutes les lignes sont reçues.
5. **Clôturé** : fin administrative.

### 4.2 Lien avec le stock

- À chaque réception (partielle ou totale), le mouvement d’entrée est créé automatiquement avec référence au BC.
- Le prix unitaire saisi dans la ligne de commande est reporté dans le mouvement (snapshot pour le CUMP/FIFO).

---

## 5. Module IA (prédictions)

### 5.1 Objectif

- À partir de l’historique des sorties (consommation), prédire la consommation future sur 30 jours.
- Suggérer des quantités à commander pour éviter les ruptures.

### 5.2 Modèles

- **Prophet** (priorité) : gère saisonnalité hebdomadaire et annuelle.
- **RandomForest** (fallback) : si Prophet indisponible.
- **Fallback simple** : moyenne mobile sur 28 jours.

### 5.3 Déclenchement

- Automatique chaque nuit (Celery Beat) ou manuel via l’interface (admin entreprise ou responsable achat).
- Pour chaque produit actif, `predire_produit.delay()` est appelée. La tâche :
  - Récupère l’historique des sorties sur 2 ans.
  - Applique le modèle choisi (Prophet/RF).
  - Sauvegarde le résultat dans `PredictionStock` (quantité prévue, bornes, confiance).
  - Génère une suggestion d’achat si le stock prévu devient inférieur au seuil.

### 5.4 Affichage

- Tableau des prédictions avec :
  - Consommation prévue
  - Stock prévu à J+30
  - Intervalle de confiance
  - Score de confiance (en %)
  - Quantité recommandée (badge vert)
- Graphiques d’évolution (dans certaines vues).

---

## 6. API REST et PWA mobile

### 6.1 API (authentification JWT)

- Endpoints pour :
  - Login / logout / refresh token
  - Dashboard mobile (agrégats)
  - Produits (CRUD, scan par code‑barres, stats)
  - Mouvements (liste, création rapide)
  - Alertes (liste, marquer lue, compteur)
  - Référentiels (catégories, entrepôts, fournisseurs)

### 6.2 PWA (magasinier)

- Installable sur smartphone (Android / iOS).
- Service Worker : cache statique, mode hors ligne, synchronisation différée des mouvements.
- Scanner intégré (BarcodeDetector ou QuaggaJS).
- Sons de feedback (bip OK / erreur).

---

## 7. Sécurité et permissions

- **Décorateurs `role_required`** : chaque vue est protégée par les rôles autorisés.
- **Super‑admin** a tous les droits (y compris d’administration Django).
- **Admin entreprise** ne peut voir que ses propres données (multi‑tenant).
- **Gestionnaire** peut tout faire sauf gestion des fournisseurs et commandes.
- **Magasinier** : accès restreint au scan et aux stocks lecture seule + création de mouvements.
- **Auditeur / Comptable** : lecture seule (sauf exports).
- Les mots de passe sont hashés (PBKDF2).

---

## 8. Synthèse des flux utilisateurs

### 8.1 Inscription d’une nouvelle entreprise

- Visiteur remplit un wizard en 3 étapes (type entreprise, infos entreprise, compte admin).
- Email de confirmation envoyé.
- Admin entreprise active son compte → peut inviter ses collègues.

### 8.2 Mise en place initiale

- Admin entreprise crée des catégories, des entrepôts, des fournisseurs.
- Gestionnaire importe ou crée les produits.
- Gestionnaire enregistre les mouvements initiaux (stock de départ).

### 8.3 Cycle de vie quotidien

- **Magasinier** : scan des entrées/sorties (réceptions, ventes).
- **Gestionnaire** : supervise les alertes, lance des inventaires.
- **Responsable achat** : consulte les prédictions IA, crée des BC, réceptionne.
- **Comptable** : vérifie la valorisation et exporte pour la compta.
- **Auditeur** : audite les mouvements et logs.

### 8.4 Maintenance

- Super Admin surveille la plateforme, peut désactiver une entreprise ou un utilisateur.
- Celery / Redis tournent en arrière‑plan pour les prédictions.

---

## 9. Principaux fichiers et dossiers du projet

``` bash

  apps/
  ├── core/ # modèles abstraits, AuditLog, ExportLog
  ├── entreprises/ # modèles Entreprise, TypeEntreprise
  ├── accounts/ # Utilisateur, rôles, authentification
  ├── stock/ # produits, mouvements, inventaires, alertes, prédictions
  ├── gestionnaire/ # vues/gestionnaire
  ├── responsable_achat/ # fournisseurs, commandes
  ├── magasinier/ # scan, inventaire terrain
  ├── auditeur/ # rapports, logs
  ├── comptable/ # valorisation, marges
  ├── superadmin/ # gestion globale
  ├── admin_entreprise/ # gestion entreprise
  ├── api/ # API REST + PWA
  ├── pages/ # pages publiques
  config/ # settings, urls, wsgi
  templates/ # templates globaux
  static/ # CSS, JS, PWA (sw.js, manifest, icônes)
  scripts/ # scripts de seeding

```

## 10. Démarrage rapide (environnement de développement)

```bash
# 1. Cloner le projet
git clone ... && cd Stock_project

# 2. Créer virtualenv et installer dépendances
python -m venv env
source env/bin/activate  # ou env\Scripts\activate
pip install -r requirements.txt

# 3. Configurer PostgreSQL (ou SQLite) et settings

# 4. Migrations
python manage.py migrate

# 5. Créer un super admin (via script ou commande)
python manage.py shell < create_superadmin.py

# 6. Lancer le serveur
python manage.py runserver

# 7. (Optionnel) Démarrer Celery worker et beat (pour IA)
celery -A config worker --pool=solo --loglevel=info
celery -A config beat --loglevel=info 

#redis
redis-server.exe redis.windows.conf
```

## 11. Variables d’environnement importantes (production)

``` bash
DJANGO_SETTINGS_MODULE = config.settings.prod

SECRET_KEY

DATABASE_URL

REDIS_URL

EMAIL_HOST_USER, EMAIL_HOST_PASSWORD

NGROK_URL (pour CSRF_TRUSTED_ORIGINS)
```
