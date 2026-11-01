# Déploiement de StockMaster — Caddy, sans Docker

## Architecture

```text
Navigateur / PWA ──HTTPS──▶ Caddy :443 ─┬─ /static/*  → staticfiles\   (fichiers servis par Caddy)
                                        ├─ /media/*   → media\
                                        └─ le reste   → 127.0.0.1:8000  waitress (Windows) / gunicorn (Linux)
                                                                          └─ Django (config.settings.prod)
                                                                               ├─ PostgreSQL
                                                                               └─ Redis ◀── Celery worker + beat (IA)
```

- **Caddy** obtient et renouvelle seul le certificat HTTPS (Let's Encrypt) pour un vrai domaine, ou un certificat local pour `localhost`.
- **waitress** (Windows) / **gunicorn** (Linux) n'écoute qu'en local : il n'est jamais exposé directement.
- Configuration : [deploy/Caddyfile](deploy/Caddyfile) (commune aux deux systèmes) et `.env`.

## 1. Préparer le serveur

1. Installer Python 3.13, PostgreSQL, Redis et [Caddy](https://caddyserver.com/download) (un seul exécutable `caddy.exe` / `caddy`).
2. Récupérer le code, par exemple dans `C:\apps\stockmaster` (Windows) ou `/srv/stockmaster` (Linux).
3. Créer la base : `createdb -U postgres stockmaster`.
4. Créer `.env` à partir de `.env.example` et renseigner au minimum :

```ini
SECRET_KEY=<50+ caractères aléatoires>   # python -c "import secrets; print(secrets.token_urlsafe(50))"
DEBUG=False
DB_NAME=stockmaster
DB_USER=postgres
DB_PASSWORD=<mot de passe>
DB_HOST=localhost
STOCKMASTER_DOMAINE=stock.mon-entreprise.tg
ALLOWED_HOSTS=stock.mon-entreprise.tg
CSRF_TRUSTED_ORIGINS=https://stock.mon-entreprise.tg
CORS_ALLOWED_ORIGINS=https://stock.mon-entreprise.tg
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=<mot de passe d'application>
```

5. DNS : un enregistrement A de `stock.mon-entreprise.tg` vers l'IP publique du serveur. Ports **80 et 443** ouverts (le port 80 sert à la validation Let's Encrypt et à la redirection vers HTTPS).

> Réseau local sans domaine public : mettre `STOCKMASTER_DOMAINE=localhost` (ou le nom de la machine) ; Caddy génère alors un certificat interne. Lancer une fois `caddy trust` sur chaque poste client pour que le navigateur l'accepte.

## 2. Windows

### Premier lancement (test)

```bat
demarrage.bat prod
```

Le script fait tout dans l'ordre : contrôles, `check --deploy`, migrations, `collectstatic`, Celery, Caddy, waitress (détail dans [DEMARRAGE.md](DEMARRAGE.md)). Si `caddy.exe` n'est pas dans le PATH : `demarrage.bat prod -Caddy C:\caddy\caddy.exe`.

Puis créer le super administrateur :

```bat
set DJANGO_SETTINGS_MODULE=config.settings.prod
.venv\Scripts\python.exe manage.py runscript create_superadmin
```

### Fonctionnement permanent (services Windows)

`demarrage.bat prod` convient pour tester ou pour un poste qui reste ouvert. Pour un serveur qui redémarre seul, installer chaque processus comme service avec [NSSM](https://nssm.cc/download) (console **administrateur**, adapter `C:\apps\stockmaster`) :

```bat
set APP=C:\apps\stockmaster
set ENV=DJANGO_SETTINGS_MODULE=config.settings.prod

:: Serveur WSGI
nssm install StockMaster-Web "%APP%\.venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:8000 --threads=8 --trusted-proxy=127.0.0.1 "--trusted-proxy-headers=x-forwarded-for x-forwarded-proto" config.wsgi:application
nssm set StockMaster-Web AppDirectory "%APP%"
nssm set StockMaster-Web AppEnvironmentExtra %ENV%
nssm set StockMaster-Web AppStdout "%APP%\logs\web.log"
nssm set StockMaster-Web AppStderr "%APP%\logs\web.log"

:: Celery worker et beat
nssm install StockMaster-Celery "%APP%\.venv\Scripts\python.exe" -m celery -A config worker --pool=solo --loglevel=info
nssm set StockMaster-Celery AppDirectory "%APP%"
nssm set StockMaster-Celery AppEnvironmentExtra %ENV%
nssm set StockMaster-Celery AppStderr "%APP%\logs\celery.log"

nssm install StockMaster-Beat "%APP%\.venv\Scripts\python.exe" -m celery -A config beat --loglevel=info
nssm set StockMaster-Beat AppDirectory "%APP%"
nssm set StockMaster-Beat AppEnvironmentExtra %ENV%
nssm set StockMaster-Beat AppStderr "%APP%\logs\beat.log"

:: Caddy (les variables remplacent celles que demarrage.ps1 définit)
nssm install StockMaster-Caddy C:\caddy\caddy.exe run --config "%APP%\deploy\Caddyfile" --adapter caddyfile
nssm set StockMaster-Caddy AppDirectory "%APP%"
nssm set StockMaster-Caddy AppEnvironmentExtra STOCKMASTER_DOMAINE=stock.mon-entreprise.tg STOCKMASTER_RACINE=C:/apps/stockmaster STOCKMASTER_PORT=8000

for %S in (Web Celery Beat Caddy) do nssm start StockMaster-%S
```

Les services démarrent avec Windows. Gestion : `nssm restart StockMaster-Web`, `nssm edit StockMaster-Web`, ou la console `services.msc`.

### Mettre à jour une installation Windows

```bat
git pull
.venv\Scripts\python.exe -m pip install -r requirements.txt
set DJANGO_SETTINGS_MODULE=config.settings.prod
.venv\Scripts\python.exe manage.py migrate --noinput
.venv\Scripts\python.exe manage.py collectstatic --noinput
for %S in (Web Celery Beat) do nssm restart StockMaster-%S
```

(Caddy n'a pas besoin d'être redémarré, sauf si `deploy\Caddyfile` a changé : `nssm restart StockMaster-Caddy`.)

## 3. Linux (Debian / Ubuntu)

```bash
sudo apt install python3.13-venv postgresql redis-server caddy
sudo useradd --system --home /srv/stockmaster stockmaster
cd /srv/stockmaster
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt   # installe aussi gunicorn
# .env comme ci-dessus, puis :
export DJANGO_SETTINGS_MODULE=config.settings.prod
.venv/bin/python manage.py check --deploy
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py runscript create_superadmin
mkdir -p logs media && sudo chown -R stockmaster: /srv/stockmaster
sudo chown caddy: logs    # Caddy y écrit son journal d'accès
```

Services systemd fournis dans [deploy/linux/](deploy/linux/) (gunicorn, Celery worker, Celery beat) :

```bash
sudo cp deploy/linux/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stockmaster-web stockmaster-celery stockmaster-beat
```

Caddy (installé comme service par le paquet) : définir les variables dans `sudo systemctl edit caddy` :

```ini
[Service]
Environment=STOCKMASTER_DOMAINE=stock.mon-entreprise.tg
Environment=STOCKMASTER_RACINE=/srv/stockmaster
Environment=STOCKMASTER_PORT=8000
```

puis faire pointer `/etc/caddy/Caddyfile` vers celui du projet (`import /srv/stockmaster/deploy/Caddyfile`) et `sudo systemctl reload caddy`. Gunicorn n'a pas besoin de réglage de proxy : il fait confiance à `127.0.0.1` par défaut.

## 4. Vérifications après déploiement

- [ ] `https://<domaine>/` s'affiche avec un cadenas valide ; `http://<domaine>/` redirige vers HTTPS.
- [ ] Connexion du super administrateur, puis création d'une entreprise de test.
- [ ] `https://<domaine>/static/pwa/manifest.json` répond 200 (statiques servis par Caddy).
- [ ] L'installation de la PWA est proposée sur mobile (nécessite HTTPS).
- [ ] Lancement manuel d'une analyse IA (espace responsable achat → Prédictions) : la fenêtre ou le journal Celery montre la tâche.
- [ ] Un email (invitation d'utilisateur) arrive bien.
- [ ] Celery Beat tourne : il déclenche chaque jour l'analyse IA (2 h), les alertes d'expiration (6 h) et les suggestions d'achat par email (6 h 30), et le rapport hebdomadaire le lundi (7 h). Ces emails ne partent que si l'entreprise les a activés dans **Admin entreprise → Paramètres**.
- [ ] Sauvegarde PostgreSQL planifiée (`pg_dump -Fc stockmaster > stockmaster_AAAAMMJJ.dump`, tâche planifiée Windows ou cron), ainsi que du dossier `media\`.

## Points de sécurité déjà en place

- `config.settings.prod` : `DEBUG=False`, `SECRET_KEY` obligatoire, cookies `Secure`, HSTS, redirection HTTPS, `X-Frame-Options: DENY`.
- `SECURE_PROXY_SSL_HEADER` : Django reconnaît les requêtes HTTPS transmises par Caddy via `X-Forwarded-Proto`.
- waitress / gunicorn n'écoutent que sur `127.0.0.1` ; seuls les ports 80/443 de Caddy sont exposés.
