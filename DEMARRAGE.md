# Démarrer StockMaster — `demarrage.bat` / `demarrage.ps1`

Ce document décrit ce que fait le script de démarrage, étape par étape, et comment réagir si une étape échoue.

## Les deux fichiers

| Fichier | Rôle |
|---|---|
| `demarrage.bat` | Point d'entrée : double-clic dans l'explorateur ou appel depuis `cmd`. Il ne contient aucune logique : il lance `demarrage.ps1` avec `-ExecutionPolicy Bypass` (pour cette exécution uniquement, la configuration de la machine n'est pas modifiée) et lui transmet toutes les options. Si le démarrage échoue, la fenêtre reste ouverte (`pause`) pour que vous puissiez lire l'erreur. |
| `demarrage.ps1` | Fait tout le travail décrit ci-dessous. Utilisable directement depuis PowerShell : `.\demarrage.ps1`. |

Une seule source de vérité : modifier le comportement = modifier `demarrage.ps1`.

## Utilisation

```bat
demarrage.bat                         :: développement (http://127.0.0.1:8000)
demarrage.bat prod                    :: production : waitress + Caddy (HTTPS)
demarrage.bat dev -SansCelery         :: sans Celery (pas d'analyses IA)
demarrage.bat prod -Caddy C:\caddy\caddy.exe -Port 8001
```

```powershell
.\demarrage.ps1 -Mode dev
.\demarrage.ps1 -Mode prod -SansNavigateur
Get-Help .\demarrage.ps1 -Detailed     # aide intégrée
```

| Option | Effet |
|---|---|
| `dev` / `prod` (`-Mode`) | Mode de lancement. Défaut : `dev`. |
| `-Port 8000` | Port local de Django (dev) ou de waitress (prod). |
| `-SansCelery` | Ne lance ni le worker ni le beat Celery. |
| `-Installer` | Force `pip install -r requirements.txt` (après une mise à jour du dépôt par exemple). |
| `-SansNavigateur` | N'ouvre pas le navigateur à la fin. |
| `-Caddy <chemin>` | Emplacement de `caddy.exe` s'il n'est pas trouvé automatiquement (mode prod). |

**Arrêt** : `Ctrl+C` dans la fenêtre principale arrête le serveur **et** ferme les fenêtres ouvertes par le script (Celery, Caddy, Redis éventuel). Les services Windows déjà installés (PostgreSQL, Redis) ne sont pas arrêtés.

## Prérequis

- Windows 10/11 avec Windows PowerShell 5.1 (présent par défaut).
- Python 3.13 (seulement si le dossier `env\` n'existe pas encore).
- PostgreSQL démarré, avec la base indiquée dans `.env` (`DB_NAME`, `stockmaster` par défaut) déjà créée.
- Redis (facultatif) : nécessaire pour Celery, donc pour les prédictions IA.
- Caddy (mode `prod` uniquement) : voir [DEPLOIEMENT.md](DEPLOIEMENT.md).

## Déroulé, étape par étape

Chaque étape affiche `OK` (vert), `..` (information), `!!` (avertissement, le script continue) ou `ERREUR` (rouge, le script s'arrête et ferme ce qu'il a ouvert).

### 1/9 — Environnement Python
- Si `.venv\Scripts\python.exe` n'existe pas, crée l'environnement virtuel `.venv\` avec `py -3` (ou `python`), puis installe les dépendances.
- Sinon, vérifie en une commande que les modules essentiels s'importent (`django`, `rest_framework`, `celery`, `decouple`, `waitress`). S'il en manque un, lance `pip install -r requirements.txt`.
- `-Installer` force l'installation dans tous les cas.

> Échec typique : *« Python est introuvable »* → installer Python 3.13 depuis python.org en cochant « Add to PATH ».

### 2/9 — Configuration (`.env`)
- Si `.env` est absent, le copie depuis `.env.example` et remplace `SECRET_KEY` par une clé aléatoire de 50 caractères. Le script le signale : pensez à renseigner `DB_PASSWORD` et, si besoin, les identifiants email.
- En mode `prod`, refuse de continuer si `SECRET_KEY` est vide ou laissée à sa valeur d'exemple, ou si `ALLOWED_HOSTS` est vide.

`.env` n'est jamais versionné (voir `.gitignore`).

### 3/9 — PostgreSQL (obligatoire)
- Teste une connexion TCP sur `DB_HOST:DB_PORT` (défaut `localhost:5432`).
- Si rien ne répond et qu'un service Windows `postgresql*` existe, tente de le démarrer (nécessite parfois une console administrateur).
- Si la base reste injoignable → `ERREUR`.

### 4/9 — Redis (facultatif)
- Lit l'hôte et le port dans `REDIS_URL` (défaut `127.0.0.1:6379`).
- Si Redis ne répond pas : démarre le service Windows `Redis*` s'il existe, sinon lance `redis-server.exe` (PATH ou `C:\Program Files\Redis`) dans une fenêtre séparée.
- Si Redis reste absent → avertissement, et Celery n'est pas lancé (l'application fonctionne, mais sans analyses IA).

### 5/9 — Contrôle de la configuration Django
- Définit `DJANGO_SETTINGS_MODULE` : `config.settings.dev` ou `config.settings.prod`.
- `dev` : `manage.py check`. `prod` : `manage.py check --deploy --fail-level ERROR` (les avertissements de sécurité s'affichent sans bloquer, les erreurs bloquent).

### 6/9 — Migrations
- `manage.py migrate --noinput`. Sans effet si la base est déjà à jour.

> Échec typique : *« password authentication failed »* → corriger `DB_USER` / `DB_PASSWORD` dans `.env`. *« database "stockmaster" does not exist »* → créer la base : `createdb -U postgres stockmaster`.

### 7/9 — Fichiers statiques
- `dev` : rien à faire, `runserver` les sert lui-même.
- `prod` : `manage.py collectstatic --noinput` rassemble tout dans `staticfiles\` (servi directement par Caddy), et crée `logs\` et `media\` s'ils manquent.

Avant l'étape suivante, le script vérifie que le port choisi est libre ; sinon → `ERREUR` (une autre instance tourne probablement déjà).

### 8/9 — Celery
Ouvre deux fenêtres séparées (elles restent ouvertes en cas de plantage, pour lire l'erreur) :
- **Celery worker** : `celery -A config worker --pool=solo` (le pool par défaut ne fonctionne pas sous Windows) ; exécute les analyses IA.
- **Celery beat** : planificateur ; déclenche l'analyse IA chaque nuit à 2 h.

Ignoré avec `-SansCelery` ou si Redis est absent.

### 9/9 — Serveur web
- **dev** : `manage.py runserver 127.0.0.1:<port>` dans la fenêtre principale (rechargement automatique quand le code change).
- **prod** :
  1. cherche `caddy.exe` (option `-Caddy`, variable `CADDY_EXE`, PATH, puis `C:\caddy\`, `Program Files\Caddy\`, winget, scoop, chocolatey) ;
  2. prépare les variables lues par `deploy\Caddyfile` : `STOCKMASTER_DOMAINE` (valeur du `.env`, sinon premier `ALLOWED_HOSTS`), `STOCKMASTER_RACINE`, `STOCKMASTER_PORT` ;
  3. valide le Caddyfile (`caddy validate`), puis lance Caddy dans une fenêtre séparée ;
  4. lance **waitress** dans la fenêtre principale, sur `127.0.0.1:<port>` uniquement, en déclarant Caddy comme proxy de confiance (sans cela, Django ne verrait pas que la requête d'origine était en HTTPS et redirigerait en boucle).
- Ouvre le navigateur 4 secondes plus tard (sauf `-SansNavigateur`).

## Après le premier démarrage

```powershell
# Créer le super administrateur (identifiants SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD du .env,
# sinon un mot de passe aléatoire est affiché une seule fois)
.venv\Scripts\python.exe manage.py runscript create_superadmin

# Facultatif : jeu de données de démonstration (une entreprise de distribution, 100 produits)
.venv\Scripts\python.exe manage.py runscript seed
```

## Dépannage rapide

| Message | Cause probable | Solution |
|---|---|---|
| *L'exécution de scripts est désactivée sur ce système* | `demarrage.ps1` lancé directement avec la politique par défaut | Passer par `demarrage.bat`, ou `powershell -ExecutionPolicy Bypass -File .\demarrage.ps1` |
| `PostgreSQL ne répond pas` | Service arrêté | `Start-Service postgresql*` dans une console administrateur |
| `Le port 8000 est déjà utilisé` | Une instance tourne déjà | La fermer, ou `demarrage.bat dev -Port 8001` |
| Fenêtre « Celery worker » avec `Error 10061` | Redis s'est arrêté | Redémarrer le service Redis, puis relancer le script |
| `caddy.exe introuvable` | Caddy hors du PATH | `demarrage.bat prod -Caddy C:\chemin\caddy.exe` |
| Boucle de redirection en production | Accès direct à waitress sans passer par Caddy | Toujours passer par l'URL `https://<domaine>/` |
