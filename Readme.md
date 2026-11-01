# 📦 STOCKMASTER – Guide complet de l’application

**StockMaster** est une solution web intelligente de gestion de stock destinée aux PME/ETI.  
Elle intègre un suivi multi‑entrepôts, des mouvements de stock, des alertes, des prédictions IA, plusieurs rôles utilisateurs, une API REST et une PWA mobile.

> **Démarrer** : `demarrage.bat` ([DEMARRAGE.md](DEMARRAGE.md)) · **Déployer** : [DEPLOIEMENT.md](DEPLOIEMENT.md) · **Avancement** : [TASKS.md](TASKS.md) · **Historique** : [HISTORY.md](HISTORY.md)

---

## 1. Architecture générale

- **Backend** : Django 6, PostgreSQL, Celery + Redis
- **Frontend** : Tailwind CSS, ShadCN, Font Awesome
- **Mobile** : PWA (Progressive Web App) + Service Worker
- **IA** : Prophet / RandomForest pour les prédictions de consommation
- **Production** : Caddy (HTTPS automatique) devant waitress (Windows) ou gunicorn (Linux), sans Docker

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
2. **Envoyé** : bouton « Envoyer » (ou « Enregistrer & envoyer » à la création) ; un BC sans ligne ne peut pas être envoyé. Le PDF du bon de commande est disponible à tout moment.
3. **Réception partielle** : saisie des quantités reçues (possible en plusieurs fois). À chaque réception, des mouvements d’entrée sont créés et le stock est mis à jour.
4. **Réception complète** : toutes les lignes sont reçues.
5. **Clôturé** : fin administrative.

Un BC peut être **annulé** tant qu'il est en brouillon ou envoyé (pas après réception).

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

```text
apps/
├── core/               # modèles abstraits, AuditLog, ExportLog
├── entreprises/        # Entreprise, TypeEntreprise
├── accounts/           # Utilisateur, rôles, authentification, invitations
├── stock/              # produits, mouvements, inventaires, alertes, bons de commande, prédictions
├── gestionnaire/       # espace gestionnaire de stock
├── responsable_achat/  # fournisseurs, bons de commande, prédictions et suggestions IA
├── magasinier/         # scan, mouvements rapides, inventaire terrain
├── auditeur/           # mouvements, écarts, logs, conformité
├── comptable/          # valorisation, marges, dépréciation
├── superadmin/         # gestion globale de la plateforme
├── admin_entreprise/   # utilisateurs, entrepôts, catégories de l'entreprise
├── ia/                 # tâches Celery de prédiction
├── api/                # API REST (JWT) utilisée par la PWA
└── pages/              # site public, avis clients
config/                 # settings (base / dev / prod / test), urls, wsgi, celery
deploy/                 # Caddyfile, services systemd (Linux)
templates/              # templates globaux (base, erreurs, emails)
static/                 # CSS, sons, PWA (sw.js, manifest, icônes)
scripts/                # super admin, données de démonstration
tests/                  # tests des points critiques
demarrage.bat / .ps1    # lancement en un clic (dev ou prod)
```

---

## 10. Démarrage rapide (Windows)

Prérequis : Python 3.13, PostgreSQL démarré avec une base `stockmaster`, Redis (facultatif, pour l'IA).

```bat
git clone https://github.com/aksp66/stockmaster.git && cd stockmaster
demarrage.bat
```

Le script crée l'environnement Python, installe les dépendances, génère `.env`, vérifie PostgreSQL et Redis, applique les migrations, lance Celery et ouvre http://127.0.0.1:8000. `Ctrl+C` arrête tout. Détail de chaque étape et dépannage : **[DEMARRAGE.md](DEMARRAGE.md)**.

Créer ensuite le super administrateur, puis (facultatif) charger les données de démonstration :

```bat
.venv\Scripts\python.exe manage.py runscript create_superadmin
.venv\Scripts\python.exe manage.py runscript seed
```

<details>
<summary>Démarrage manuel (sans le script, ou sous Linux / macOS)</summary>

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux / macOS : source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # puis renseigner SECRET_KEY, DB_PASSWORD…
python manage.py migrate
python manage.py runscript create_superadmin
python manage.py runserver

# Facultatif (IA) : Redis démarré, puis dans deux autres terminaux
celery -A config worker --pool=solo --loglevel=info
celery -A config beat --loglevel=info
```

</details>

---

### Interface : système de design et thèmes

Tous les espaces partagent une seule feuille, `static/css/stockmaster.css` : jetons de couleur, polices (Poppins pour les titres, Tahoma pour le texte), composants, grilles et animations. Les couleurs viennent de variables CSS : chaque entreprise choisit un thème (Orange, Océan, Forêt, Violet, Rubis, Ardoise) dans **Paramètres → Apparence**, appliqué à tous ses utilisateurs via `data-theme`. Pour ajouter un thème : une règle `:root[data-theme="…"]` dans la feuille et une ligne dans `THEMES` (`apps/entreprises/models.py`). Les statuts de stock et les catégories passent par les balises `apps/stock/templatetags/stock_ui.py` (`st_badge`, `cat_badge`…) : une seule palette partout. Les actions sensibles se confirment avec l'attribut `data-confirm` (`static/js/stockmaster.js`).

Incrémenter `APP_VERSION` dans `static/pwa/sw.js` après toute modification de `stockmaster.css` ou `stockmaster.js` : le Service Worker les sert depuis son cache.

### Styles (Tailwind CSS)

Le CSS Tailwind est **compilé** dans `static/css/output.css` (versionné, aucune dépendance à un CDN en production). Après avoir ajouté ou modifié des classes Tailwind dans un template :

```bash
npm install        # une seule fois (Tailwind 3.4.17)
npm run build      # régénère static/css/output.css
```

Puis incrémenter `APP_VERSION` dans `static/pwa/sw.js` : le Service Worker sert le CSS depuis son cache.

---

## 11. Tests

```bash
python manage.py test --settings=config.settings.test
```

Seul PostgreSQL est nécessaire : `config.settings.test` remplace Redis par un cache mémoire et exécute Celery de façon synchrone. Le dossier `tests/` couvre les points critiques : permissions par rôle, séparation entre entreprises, stock jamais négatif, workflow des bons de commande, inventaire, avis clients.

Trois tests génériques contrôlent automatiquement toute nouvelle route : `test_securite_generique.py` (matrice rôle × espace, et isolation entre entreprises sur chaque URL à identifiant), `test_robustesse.py` (robot de parcours : variables de gabarit en échec, POST vides sans erreur serveur, auditeur en lecture seule) et le contrôle des pages de chaque espace. Le journal d'audit (`apps.core.models.AuditLog`) enregistre les actions sensibles de tous les rôles.

La CI GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) lance à chaque push : `check`, détection de migrations manquantes, `check --deploy`, un audit des dépendances (`pip-audit`, sans bloquer) et les tests.

---

## 12. Déploiement (Caddy, sans Docker)

Caddy assure le HTTPS automatique et sert les fichiers statiques. Le serveur WSGI (waitress sous Windows, gunicorn sous Linux) n'écoute qu'en local.

```bat
demarrage.bat prod
```

Configuration, services Windows (NSSM) ou systemd, mises à jour et liste de vérification : **[DEPLOIEMENT.md](DEPLOIEMENT.md)**.

Variables d'environnement de production (`.env`, voir `.env.example`) :

| Variable | Rôle |
|---|---|
| `SECRET_KEY` | Clé secrète Django (obligatoire) |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL |
| `REDIS_URL` | Redis (Celery + cache) |
| `STOCKMASTER_DOMAINE` | Domaine servi par Caddy |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` | Domaine(s) autorisé(s), séparés par des virgules |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP (mot de passe d'application Gmail) |

---

## 13. Documentation du projet

| Document | Contenu |
|---|---|
| [DEMARRAGE.md](DEMARRAGE.md) | Étapes du script de démarrage, options, dépannage |
| [DEPLOIEMENT.md](DEPLOIEMENT.md) | Mise en production avec Caddy (Windows et Linux) |
| [HISTORY.md](HISTORY.md) | Historique du projet |
| [TASKS.md](TASKS.md) | Tâches faites et restantes, par priorité |
| `GUIDE_INSTALLATION_IA.txt` | Installation de Prophet / Celery / Redis |
| `GUIDE_API_PWA.txt` | API REST et PWA mobile |
| `StockMaster_Livrables_UML.html` | Livrables de conception UML |
| [SIGNATURE.md](SIGNATURE.md) | Paternité du projet |
