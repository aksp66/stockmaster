<#
.SYNOPSIS
    Démarre StockMaster en développement (runserver) ou en production (waitress + Caddy).

.DESCRIPTION
    Vérifie et prépare tout ce dont l'application a besoin, puis lance les processus :
      1. environnement Python (env\) et dépendances
      2. fichier .env (créé depuis .env.example si absent)
      3. PostgreSQL (obligatoire)
      4. Redis (facultatif : sans lui, pas de Celery donc pas d'analyses IA)
      5. contrôle Django (check / check --deploy)
      6. migrations
      7. fichiers statiques (production uniquement)
      8. Celery worker + beat (fenêtres séparées)
      9. serveur web : runserver (dev) ou waitress + Caddy (prod)
    Ctrl+C dans cette fenêtre arrête le serveur ET les fenêtres ouvertes par le script.
    Le détail de chaque étape est dans DEMARRAGE.md.

.PARAMETER Mode
    dev (défaut) ou prod.

.PARAMETER Port
    Port local du serveur Django / waitress (défaut 8000).

.PARAMETER SansCelery
    Ne lance ni le worker ni le beat Celery.

.PARAMETER Installer
    Force la réinstallation des dépendances (pip install -r requirements.txt).

.PARAMETER SansNavigateur
    N'ouvre pas le navigateur à la fin.

.PARAMETER Caddy
    Chemin complet de caddy.exe s'il n'est pas dans le PATH (mode prod).

.EXAMPLE
    .\demarrage.ps1
.EXAMPLE
    .\demarrage.ps1 -Mode prod -Caddy C:\caddy\caddy.exe
#>
[CmdletBinding()]
param(
    [ValidateSet('dev', 'prod')][string]$Mode = 'dev',
    [int]$Port = 8000,
    [switch]$SansCelery,
    [switch]$Installer,
    [switch]$SansNavigateur,
    [string]$Caddy = ''
)

$ErrorActionPreference = 'Stop'
$Racine = $PSScriptRoot
Set-Location -LiteralPath $Racine
$Python = Join-Path $Racine '.venv\Scripts\python.exe'
$Fenetres = New-Object System.Collections.ArrayList

# ── Affichage ─────────────────────────────────────────────────────────────────
function Etape([string]$Num, [string]$Texte) { Write-Host ''; Write-Host "[$Num] $Texte" -ForegroundColor Cyan }
function Ok([string]$Texte)     { Write-Host "    OK  $Texte" -ForegroundColor Green }
function Info([string]$Texte)   { Write-Host "    ..  $Texte" -ForegroundColor Gray }
function Alerte([string]$Texte) { Write-Host "    !!  $Texte" -ForegroundColor Yellow }
function Echec([string]$Texte) {
    Write-Host ''
    Write-Host "ERREUR : $Texte" -ForegroundColor Red
    Arreter-Fenetres
    exit 1
}

# ── Outils ────────────────────────────────────────────────────────────────────
function Test-Port([string]$Hote, [int]$NumPort) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $essai = $client.BeginConnect($Hote, $NumPort, $null, $null)
        if (-not $essai.AsyncWaitHandle.WaitOne(800)) { return $false }
        $client.EndConnect($essai)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Lire-Env([string]$Cle, [string]$Defaut = '') {
    if (-not (Test-Path '.env')) { return $Defaut }
    foreach ($ligne in Get-Content '.env' -Encoding UTF8) {
        if ($ligne -match "^\s*$Cle\s*=\s*(.*?)\s*$") {
            $valeur = $Matches[1].Trim('"').Trim("'")
            if ($valeur -ne '') { return $valeur }
        }
    }
    return $Defaut
}

# Exécute une commande native en ignorant sa sortie ; renvoie son code de retour.
# (Sous PowerShell 5.1, rediriger stderr avec ErrorActionPreference=Stop interromprait le script.)
function Natif-Silencieux([scriptblock]$Bloc) {
    $ErrorActionPreference = 'Continue'
    & $Bloc 2>&1 | Out-Null
    return $LASTEXITCODE
}

function Manage([string[]]$Arguments, [string]$MessageErreur) {
    & $Python manage.py @Arguments
    if ($LASTEXITCODE -ne 0) { Echec $MessageErreur }
}

# Ouvre une console séparée (cmd /k : elle reste ouverte si le processus plante, pour lire l'erreur)
function Ouvrir-Fenetre([string]$Titre, [string]$Commande) {
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList "/k title StockMaster - $Titre & $Commande" `
        -WorkingDirectory $Racine -PassThru
    [void]$Fenetres.Add($p)
    Info "Fenêtre « $Titre » ouverte (PID $($p.Id))"
}

function Arreter-Fenetres {
    foreach ($p in $Fenetres) {
        if (-not $p.HasExited) { [void](Natif-Silencieux { taskkill.exe /T /F /PID $p.Id }) }
    }
    $Fenetres.Clear()
}

function Trouver-Caddy {
    if ($Caddy -ne '') {
        if (Test-Path $Caddy) { return (Resolve-Path $Caddy).Path }
        Echec "caddy.exe introuvable à l'emplacement indiqué : $Caddy"
    }
    if ($env:CADDY_EXE -and (Test-Path $env:CADDY_EXE)) { return $env:CADDY_EXE }
    $cmd = Get-Command caddy -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidats = @(
        'C:\caddy\caddy.exe',
        (Join-Path $env:ProgramFiles 'Caddy\caddy.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\caddy.exe'),
        (Join-Path $env:USERPROFILE 'scoop\shims\caddy.exe'),
        'C:\ProgramData\chocolatey\bin\caddy.exe'
    )
    foreach ($c in $candidats) { if (Test-Path $c) { return $c } }
    return $null
}

Write-Host '══════════════════════════════════════════════' -ForegroundColor DarkCyan
Write-Host "  StockMaster — démarrage en mode $($Mode.ToUpper())" -ForegroundColor White
Write-Host '══════════════════════════════════════════════' -ForegroundColor DarkCyan

try {
    # ── 1. Environnement Python ───────────────────────────────────────────────
    Etape '1/9' 'Environnement Python'
    if (-not (Test-Path $Python)) {
        Info "Aucun environnement virtuel dans env\ : création…"
        if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
        elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
        else { Echec "Python est introuvable. Installez Python 3.13 (python.org) puis relancez." }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Python)) { Echec "Création de l'environnement virtuel impossible." }
        $Installer = $true
    }
    Ok (& $Python --version)

    if (-not $Installer) {
        if ((Natif-Silencieux { & $Python -c "import django, rest_framework, celery, decouple, waitress" }) -ne 0) { Info 'Dépendances manquantes : installation…'; $Installer = $true }
    }
    if ($Installer) {
        & $Python -m pip install --upgrade pip --quiet
        & $Python -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Echec "pip install -r requirements.txt a échoué (voir le message ci-dessus)." }
        Ok 'Dépendances installées'
    } else {
        Ok 'Dépendances présentes'
    }

    # ── 2. Fichier .env ───────────────────────────────────────────────────────
    Etape '2/9' 'Configuration (.env)'
    if (-not (Test-Path '.env')) {
        Copy-Item '.env.example' '.env'
        $cle = & $Python -c "import secrets; print(secrets.token_urlsafe(50))"
        $contenu = (Get-Content '.env' -Encoding UTF8) -replace '^SECRET_KEY=.*', "SECRET_KEY=$cle"
        [System.IO.File]::WriteAllLines((Join-Path $Racine '.env'), $contenu)
        Alerte '.env créé depuis .env.example avec une SECRET_KEY aléatoire.'
        Alerte 'Renseignez au moins DB_PASSWORD (et les emails) dans .env si nécessaire.'
    } else {
        Ok '.env présent'
    }
    if ($Mode -eq 'prod') {
        if ((Lire-Env 'SECRET_KEY') -match '^(|change-moi.*)$') { Echec "SECRET_KEY doit être définie dans .env pour la production." }
        if ((Lire-Env 'ALLOWED_HOSTS') -eq '') { Echec "ALLOWED_HOSTS doit être défini dans .env (ex. stock.mon-entreprise.tg)." }
    }

    # ── 3. PostgreSQL ─────────────────────────────────────────────────────────
    Etape '3/9' 'PostgreSQL'
    $dbHote = Lire-Env 'DB_HOST' 'localhost'
    $dbPort = [int](Lire-Env 'DB_PORT' '5432')
    if (-not (Test-Port $dbHote $dbPort)) {
        $service = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($service) {
            Info "Démarrage du service $($service.Name)…"
            try { Start-Service $service.Name } catch { Alerte "Impossible de démarrer $($service.Name) (droits administrateur requis ?)" }
            Start-Sleep -Seconds 3
        }
    }
    if (-not (Test-Port $dbHote $dbPort)) { Echec "PostgreSQL ne répond pas sur ${dbHote}:${dbPort}. Démarrez-le puis relancez." }
    Ok "PostgreSQL joignable sur ${dbHote}:${dbPort}"

    # ── 4. Redis ──────────────────────────────────────────────────────────────
    Etape '4/9' 'Redis (Celery / IA)'
    $redisUrl = Lire-Env 'REDIS_URL' 'redis://127.0.0.1:6379'
    $redisHote = '127.0.0.1'; $redisPort = 6379
    if ($redisUrl -match '^redis://(?:[^@]*@)?([^:/]+)(?::(\d+))?') {
        $redisHote = $Matches[1]
        if ($Matches[2]) { $redisPort = [int]$Matches[2] }
    }
    if (-not $SansCelery -and -not (Test-Port $redisHote $redisPort)) {
        $service = Get-Service -Name 'Redis*' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($service) {
            Info "Démarrage du service $($service.Name)…"
            try { Start-Service $service.Name } catch { Alerte "Impossible de démarrer $($service.Name) (droits administrateur requis ?)" }
        } else {
            $redisExe = Get-Command redis-server -ErrorAction SilentlyContinue
            if (-not $redisExe -and (Test-Path "$env:ProgramFiles\Redis\redis-server.exe")) { $redisExe = Get-Item "$env:ProgramFiles\Redis\redis-server.exe" }
            if ($redisExe) {
                $chemin = if ($redisExe.Source) { $redisExe.Source } else { $redisExe.FullName }
                Ouvrir-Fenetre 'Redis' "`"$chemin`" --port $redisPort"
            }
        }
        Start-Sleep -Seconds 2
    }
    if ($SansCelery) {
        Info 'Ignoré (-SansCelery)'
    } elseif (Test-Port $redisHote $redisPort) {
        Ok "Redis joignable sur ${redisHote}:${redisPort}"
    } else {
        Alerte "Redis absent sur ${redisHote}:${redisPort} : Celery et les analyses IA ne seront pas lancés."
        $SansCelery = $true
    }

    # ── 5. Contrôle Django ────────────────────────────────────────────────────
    Etape '5/9' 'Contrôle de la configuration Django'
    $env:DJANGO_SETTINGS_MODULE = if ($Mode -eq 'prod') { 'config.settings.prod' } else { 'config.settings.dev' }
    $env:PYTHONIOENCODING = 'utf-8'
    Info "DJANGO_SETTINGS_MODULE = $env:DJANGO_SETTINGS_MODULE"
    if ($Mode -eq 'prod') { Manage @('check', '--deploy', '--fail-level', 'ERROR') 'La configuration de production comporte des erreurs.' }
    else { Manage @('check') 'La configuration Django comporte des erreurs.' }
    Ok 'Configuration valide'

    # ── 6. Migrations ─────────────────────────────────────────────────────────
    Etape '6/9' 'Migrations de la base de données'
    Manage @('migrate', '--noinput') "Les migrations ont échoué (vérifiez DB_NAME / DB_USER / DB_PASSWORD dans .env)."
    Ok 'Base à jour'

    # ── 7. Fichiers statiques ─────────────────────────────────────────────────
    Etape '7/9' 'Fichiers statiques'
    if ($Mode -eq 'prod') {
        Manage @('collectstatic', '--noinput', '--verbosity', '0') 'collectstatic a échoué.'
        foreach ($d in 'logs', 'media') { if (-not (Test-Path $d)) { New-Item -ItemType Directory $d | Out-Null } }
        Ok 'staticfiles\ à jour (servi par Caddy)'
    } else {
        Info 'Servis directement par runserver en développement'
    }

    # ── Port libre ? ─────────────────────────────────────────────────────────
    if (Test-Port '127.0.0.1' $Port) { Echec "Le port $Port est déjà utilisé (StockMaster déjà lancé ?). Fermez l'autre instance ou utilisez -Port." }

    # ── 8. Celery ─────────────────────────────────────────────────────────────
    Etape '8/9' 'Celery (tâches IA en arrière-plan)'
    if ($SansCelery) {
        Info 'Non lancé'
    } else {
        # --pool=solo : le pool par défaut (prefork) ne fonctionne pas sous Windows
        Ouvrir-Fenetre 'Celery worker' "`"$Python`" -m celery -A config worker --pool=solo --loglevel=info"
        Ouvrir-Fenetre 'Celery beat' "`"$Python`" -m celery -A config beat --loglevel=info"
        Ok 'Worker et beat lancés'
    }

    # ── 9. Serveur web ────────────────────────────────────────────────────────
    Etape '9/9' 'Serveur web'
    if ($Mode -eq 'prod') {
        $caddyExe = Trouver-Caddy
        if (-not $caddyExe) { Echec "caddy.exe introuvable. Ajoutez-le au PATH ou passez -Caddy C:\chemin\caddy.exe (voir DEPLOIEMENT.md)." }
        $domaine = Lire-Env 'STOCKMASTER_DOMAINE' ''
        if ($domaine -eq '') { $domaine = ((Lire-Env 'ALLOWED_HOSTS' 'localhost') -split ',')[0].Trim() }
        $env:STOCKMASTER_DOMAINE = $domaine
        $env:STOCKMASTER_RACINE = $Racine -replace '\\', '/'
        $env:STOCKMASTER_PORT = "$Port"
        if ((Natif-Silencieux { & $caddyExe validate --config deploy\Caddyfile --adapter caddyfile }) -ne 0) { Echec "deploy\Caddyfile invalide : lancez « caddy validate --config deploy\Caddyfile » pour le détail." }
        Ouvrir-Fenetre 'Caddy' "`"$caddyExe`" run --config deploy\Caddyfile --adapter caddyfile"
        $url = "https://$domaine/"
        Ok "Caddy : $url  →  127.0.0.1:$Port"
    } else {
        $url = "http://127.0.0.1:$Port/"
    }

    if (-not $SansNavigateur) {
        # Ouverture différée : laisse au serveur le temps de démarrer
        Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile -Command Start-Sleep -Seconds 4; Start-Process '$url'"
    }

    Write-Host ''
    Write-Host "  StockMaster : $url" -ForegroundColor Green
    Write-Host '  Ctrl+C pour tout arrêter.' -ForegroundColor Green
    Write-Host ''

    if ($Mode -eq 'prod') {
        # Caddy (127.0.0.1) est déclaré proxy de confiance : sinon waitress supprime X-Forwarded-Proto,
        # Django croit chaque requête en HTTP et SECURE_SSL_REDIRECT redirige en boucle.
        & (Join-Path $Racine '.venv\Scripts\waitress-serve.exe') --listen="127.0.0.1:$Port" --threads=8 `
            --trusted-proxy=127.0.0.1 '--trusted-proxy-headers=x-forwarded-for x-forwarded-proto' `
            config.wsgi:application
    } else {
        & $Python manage.py runserver "127.0.0.1:$Port"
    }
} finally {
    if ($Fenetres.Count -gt 0) {
        Write-Host ''
        Write-Host 'Arrêt des processus lancés par le script…' -ForegroundColor Gray
        Arreter-Fenetres
    }
}
