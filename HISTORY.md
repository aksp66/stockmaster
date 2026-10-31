# Historique de StockMaster

Journal des grandes étapes du projet, de la plus ancienne à la plus récente. Le détail ligne à ligne est dans l'historique Git (`git log`). Les tâches restantes sont dans [TASKS.md](TASKS.md).

> Avant le premier commit (27/06/2026), le projet n'était pas versionné : les dates de cette période sont déduites des dates de modification des fichiers.

---

## Avril – mai 2026 — Construction de l'application (hors Git)

- **08/04** : création du projet Django (`config/`, `manage.py`), Tailwind installé via npm.
- **Avril** : développement des 14 applications : `core`, `entreprises`, `accounts` (utilisateurs, 7 rôles, inscription en 3 étapes, invitations), `stock` (modèles métier), un espace par rôle (`superadmin`, `admin_entreprise`, `gestionnaire`, `responsable_achat`, `magasinier`, `auditeur`, `comptable`), `ia` (prédictions Prophet / RandomForest via Celery), `api` (REST + JWT), `pages` (site public).
- **18/04** : `GUIDE_INSTALLATION_IA.txt` (installation de Prophet, Celery, Redis).
- **19/04** : `GUIDE_API_PWA.txt` (API REST et application mobile PWA du magasinier).
- **25/04** : `Readme.md` (guide fonctionnel complet), scripts de données de démonstration (`scripts/seed.py`, `scripts/stockmaster_seed.py`).
- **02/05** : `StockMaster_Livrables_UML.html` (livrables de conception UML).

## 27/06/2026 — Mise sous Git et audit complet

- `e50663c` — **Point de départ** : premier commit, le code tel qu'il était avant l'audit.
- `6cc5a11` — **Audit complet et corrections** :
  - *Sécurité* : `role_required` ne vérifiait aucun rôle (tout utilisateur connecté accédait à tous les espaces) ; secrets retirés du code (passage à `python-decouple` + `.env`) ; `prod.py` réécrit (il ne démarrait pas) ; validation des mots de passe ; restriction de rôle sur le scan du magasinier.
  - *Métier* : stock pouvant devenir négatif (verrou `select_for_update` + transaction) ; ajustements d'inventaire au signe inversé ; réception de bon de commande sans effet sur le stock ; champ `code_barres` mal nommé dans le formulaire produit ; champs `delai_reappro` / `qte_min_commande` ajoutés ; code-barres unique par entreprise.
  - *Design* : polices et thème de la barre latérale unifiés ; fichiers orphelins supprimés.
  - *PWA* : manifeste, Service Worker, icônes générées, installation et synchronisation hors ligne.
  - `requirements.txt` créé, `MEDIA_URL` / `MEDIA_ROOT` ajoutés.

## 28/06/2026 — Dépôt GitHub

- `d399604` — `tailwind.exe` (binaire de 120 Mo) exclu du dépôt.
- `475136b` — `SIGNATURE.md` : attestation de paternité du projet.
- Publication sur https://github.com/aksp66/stockmaster.

## 31/10/2026 — Pages cassées, tests, démarrage et déploiement

**Base de données**
- Migrations `stock.0004` et `stock.0005` appliquées en local (elles ne l'étaient pas, ce qui faisait planter la création de produit).

**Workflow des bons de commande (responsable achat)**
- Nouvelles routes et vues : envoyer, clôturer, annuler (POST uniquement, transitions contrôlées), **PDF** du bon de commande (reportlab), fiche fournisseur.
- La liste des bons de commande était **toujours vide** (la vue et le template n'utilisaient pas le même nom de variable) : corrigé, avec filtres (recherche, statut, fournisseur), résumé par statut et export CSV.
- Le formulaire de création envoyait les lignes sous un format que la vue ne lisait pas : **les bons de commande étaient créés sans aucune ligne**. Corrigé (remise appliquée au prix net, bouton « Enregistrer et envoyer » pris en compte).
- La page de réception ne recevait pas la liste des entrepôts (champ obligatoire vide) : **la réception était impossible depuis l'interface**. Corrigé ; l'entrepôt choisi et la référence du bon de livraison sont désormais enregistrés.
- Formulaire fournisseur : contact, délai de livraison et statut actif n'étaient pas enregistrés.
- Numéro de BC : collision possible entre deux entreprises (numéro unique dans toute la base) → plantage dès le premier BC d'une deuxième entreprise. Corrigé.
- Templates alignés sur les vrais champs du modèle (`numero`, `total_ht`, statuts `recu_partiel` / `recu_complet`, etc.) : la plupart des valeurs s'affichaient vides.
- Tableau de bord achats : le template ne se compilait pas (balise Django coupée sur deux lignes par Prettier) et ne recevait aucune des données attendues.

**Autres pages réparées**
- Magasinier : vue `inventaire_sauvegarder` (sauvegarde ou suspension du comptage) ; la page de saisie d'inventaire **plantait à chaque ouverture** (erreur de syntaxe de template).
- Site public : dépôt d'avis clients (nouveau modèle `Avis`, modération dans l'admin Django, un avis par utilisateur).
- Module IA : redirection vers une route inexistante corrigée, noms de rôles corrigés (`admin_entreprise` → `admin_ent`), filtrage par entreprise ajouté (fuite de données possible entre entreprises).
- Gestionnaire : `except (…, uuid.UUID, …)` provoquait une erreur 500 au lieu du message « Produit invalide ».
- Celery Beat : suppression de 3 tâches planifiées qui n'existent pas et d'un fuseau horaire invalide.
- `apps/stock/urls.py` supprimé (code mort pointant vers des vues inexistantes).

**Tests** : première suite de 39 tests (`tests/`) couvrant les permissions par rôle, la séparation entre entreprises, le stock jamais négatif, le workflow des bons de commande, l'inventaire et les avis. Réglages dédiés `config.settings.test`.

**Démarrage et déploiement (sans Docker)**
- `demarrage.bat` / `demarrage.ps1` : lancement en un clic, en mode dev ou prod (voir [DEMARRAGE.md](DEMARRAGE.md)).
- Production avec **Caddy** (HTTPS automatique) + **waitress** sous Windows / **gunicorn** sous Linux : `deploy/Caddyfile`, services systemd, procédure NSSM (voir [DEPLOIEMENT.md](DEPLOIEMENT.md)).
- `SECURE_PROXY_SSL_HEADER` ajouté (sans lui, Django derrière Caddy redirigeait en boucle).
- CI GitHub Actions (`.github/workflows/ci.yml`) : `check`, migrations à jour, `check --deploy`, tests.
- Documentation : `DEMARRAGE.md`, `DEPLOIEMENT.md`, `HISTORY.md`, `TASKS.md`, Readme mis à jour.

## 31/10/2026 (suite) — Vérification de tous les espaces, chiffres publics, Tailwind compilé

**Méthode** : base de démonstration séparée (`stockmaster_audit`, 100 produits, 200 bons de commande, 5 ans de mouvements), robot qui parcourt toutes les pages de chaque espace avec le rôle correspondant en signalant les erreurs et chaque variable de template introuvable (y compris dans les `{% if %}`), et analyse statique comparant les champs lus dans `request.POST` aux champs des formulaires.

**Pertes de données corrigées**
- Gestionnaire : **modifier un produit le désactivait** (case « actif » absente du formulaire), **remettait son unité à « Unité »** et **effaçait son fournisseur** (mauvais noms de champs dans le template).
- Gestionnaire : le **prix d'achat** saisi sur une entrée (utilisé pour la valorisation CUMP), la **date** et la **référence** du mouvement étaient ignorés ou mal enregistrés ; les commentaires par ligne d'inventaire étaient perdus.
- Responsable achat : modifier un fournisseur vidait son contact et ses notes.

**Pages qui affichaient des données fausses ou vides**
- Magasinier : la page **Alertes affichait toujours « aucune alerte »** ; tableau de bord (compteurs du jour, alertes, inventaires en cours), historique de scan, préférences (entrepôt et type par défaut désormais appliqués), création d'inventaire (filtre par catégorie).
- Gestionnaire : fiche produit (le graphique cassait tout le JavaScript de la page ; ajout de l'historique paginé avec stock après chaque mouvement, de la synthèse IA et des indicateurs 30 jours), liste produits (compteurs, filtre rupture / alerte / OK), liste des mouvements (entrepôt, motif, référence, résumé par type, filtres entrepôt et produit), inventaires (progression, compteurs, filtre).
- Auditeur : journal d'audit (date, type d'action, objet, détail), conformité (domaine, date, statut), écarts d'inventaire, mouvements.
- Responsable achat : **suggestions d'achat en erreur 500** (`Decimal × float`), fournisseur dans les suggestions et prédictions, badge des commandes en attente.
- Super admin : nombre d'entrepôts et de produits d'une entreprise.

**Site public** : les chiffres inventés (« +200 entreprises », « 4.8 », « 84 avis », « 97 % », « −72 % de ruptures », « 98 % de satisfaction ») et trois **témoignages fictifs** présentés comme réels sont remplacés par les chiffres de la base (entreprises activées, avis publiés et modérés). Rien n'est affiché tant qu'il n'y a pas de données.

**Tailwind** : le script `cdn.tailwindcss.com` (outil de développement, dépendance externe) est remplacé dans les 11 templates par `static/css/output.css`, compilé avec Tailwind 3.4.17 (même famille que le CDN). Rendu vérifié identique au pixel près sur les pages publiques, et contrôle de couverture des classes. Le Service Worker de la PWA passe en `v1.1.0` et met le CSS en cache.

**Tests** : 55 (contre 39), dont l'affichage de chaque page de chaque espace et les régressions ci-dessus.

## 31/10/2026 (suite 2) — Paramètres d'entreprise, ajustements, formulaires secondaires

- `46ccc6d` poussé sur GitHub (travail des deux étapes précédentes).
- **Paramètres de l'admin entreprise** : la page n'enregistrait rien. Nouveau modèle `ParametresEntreprise`, et chaque réglage a maintenant un effet : seuil d'alerte proposé à la création d'un produit, email aux admins et gestionnaires à chaque nouvelle alerte, alertes « proche de l'expiration » (tâche quotidienne), rapport hebdomadaire et suggestions d'achat IA par email (tâches Celery Beat).
- **Ajustement de stock** : le formulaire du gestionnaire propose « surplus / manque » (tout ajustement était auparavant un retrait). Un mouvement sans entrepôt valide est refusé (il était enregistré sans effet sur le stock).
- **Formulaires secondaires soumis un par un** (38 nouveaux tests). Corrigé au passage :
  - import CSV : séparateur et gestion des doublons ignorés (un CSV Excel à point-virgule créait un produit vide), colonnes catégorie / description / fournisseur ignorées, existants comptés comme importés, lignes invalides acceptées ;
  - transfert : quantité négative acceptée (transfert inversé sans contrôle de stock), page dédiée jamais affichée ;
  - champs numériques : Django affichait « 368,00 », valeur rejetée par le navigateur — **le prix disparaissait à chaque modification de produit** (19 champs corrigés) ;
  - super admin : **changement de rôle en erreur 500** ; activation / désactivation d'entreprises et d'utilisateurs par simple lien (passées en POST) ;
  - admin entreprise : un admin pouvait se supprimer, se désactiver ou changer son propre rôle ; suppression d'un entrepôt avec historique en erreur 500 (désormais désactivé) ; fiche entreprise en erreur 500 si le nombre d'entrepôts est vide ; échec d'envoi d'invitation en erreur 500 ;
  - erreurs 500 sur champs vides ou invalides : sélection « — Sélectionner — » dans les formulaires de mouvement et de bon de commande, paramètres achats, API de scan, étapes de l'inscription (saut d'étape impossible).
- **Tests** : 93.

## 31/10/2026 (suite 3) — Retours, réapprovisionnement, seuils

- `a7227c4` poussé sur GitHub (paramètres, ajustements, formulaires secondaires).
- **Retours** : le type « Retour » n'avait aucun effet sur le stock. Le formulaire demande maintenant s'il s'agit d'un retour client (la marchandise revient : entrée) ou d'un retour fournisseur (elle repart : sortie, avec contrôle du stock disponible). Même convention que l'ajustement (entrepôt de destination = +, source = −). Les historiques affichent le signe réel de chaque mouvement. Un type de mouvement inconnu est refusé.
- **Quantité suggérée** : elle valait `seuil × 2 − stock`, sans lien avec la consommation. Nouveau calcul commun (`apps/stock/reappro.py`) aux suggestions, à la liste des prédictions et à la fiche produit : consommation journalière (prédiction IA, sinon moyenne des sorties sur 28 jours) × (délai de réappro + 30 jours) + stock de sécurité − stock − commandes en cours, arrondi et au moins égal à la quantité minimale de commande. « Urgent » = rupture avant qu'une commande passée aujourd'hui soit livrée. Le bouton « Commander » pré-remplit le bon de commande.
- Au passage : la prédiction IA enregistrée est la consommation **totale** sur 30 jours (une ligne par produit) ; elle est désormais convertie en débit journalier, et la confiance est normalisée (0-1 ou 0-100 selon la source).
- **Seuils** : vérifiés aussi après une réception de bon de commande, une validation d'inventaire, un mouvement via l'API mobile et la création d'un produit avec stock initial (qui passe désormais par la règle commune de mise à jour du stock). Quand le stock remonte au-dessus du seuil, les alertes de rupture / seuil bas devenues sans objet sont clôturées automatiquement.
- **Tests** : 111.

## 31/10/2026 (suite 4) — Rapports du comptable, données de démonstration

- `ce4e28b` poussé sur GitHub (retours, réapprovisionnement, seuils).
- **Rapport comptable périodique** réécrit sur une valorisation en inventaire permanent au CUMP (`apps/comptable/valorisation.py`) : les mouvements sont rejoués dans l'ordre, chaque achat recalcule le coût moyen, chaque sortie part au coût moyen du moment. Le rapport présente désormais tous les flux (achats, retours clients, ajustements +, coût des ventes, pertes, retours fournisseurs, ajustements −), un stock de début et de fin calculés **à la date de la période** (auparavant : stock actuel, même pour une période passée), et se réconcilie exactement.
- Corrigé au passage dans l'espace comptable :
  - le **chiffre d'affaires était inventé** (sorties × 1,30) : il est maintenant calculé aux prix de vente, les produits sans prix de vente étant signalés et exclus ;
  - la valorisation **ignorait tous les stocks sans emplacement** (filtre sur `emplacement__entrepot`), c'est-à-dire la plupart ;
  - le « FIFO » prenait le prix du lot le plus ancien (et une branche reposait sur un import inexistant) : vrai FIFO, stock restant valorisé aux prix des entrées les plus récentes ;
  - catégorie « Sans catégorie » ajoutée (ces produits manquaient au total), export CSV du rapport (le bouton existait sans effet), montants en FCFA au lieu d'euros dans les exports et le PDF, ligne « Dépréciations » toujours à 0 retirée du compte de stock.
- **Script de démonstration** (`scripts/seed.py`) : les prédictions IA reprennent le format de la vraie tâche (une ligne par produit, consommation totale sur 30 jours issue de l'historique, confiance sur 100), au lieu de valeurs proches du stock.
- **Tests** : 118.

## 31/10/2026 (suite 5) — Cache de valorisation, unités des prédictions, retours dans les marges

- `33d9e6e` poussé sur GitHub (rapports du comptable, prédictions de démonstration).
- **Cache** : le profilage a montré que 85 % du temps des pages du comptable était passé à recharger l'historique des mouvements. Le rejeu est désormais mis en cache, avec une clé construite sur l'état des données (nombre et dernière modification des mouvements, stocks, prix) : toute modification l'invalide d'elle-même. FIFO calculé en une requête au lieu d'une par produit. Tableau de bord du comptable : 1,8 s → 0,10 s ; rapport : 1,08 s → 0,04 s (cache chaud). Le cache Redis est configuré pour être ignoré s'il est indisponible.
- **Unités des prédictions IA** : la quantité prévue était un total sur 30 jours mais les bornes des valeurs journalières (« 590 [12 – 31] »). Convention unique : tout est en totaux sur la période, documentée sur le modèle. La tâche IA enregistre la quantité recommandée avec le calcul commun des suggestions d'achat (au lieu d'une formule à part). L'écran IA de l'admin entreprise n'affiche plus que la dernière prédiction de chaque produit (il cumulait celles de chaque nuit), avec période, consommation par jour et confiance normalisée ; l'export CSV suit la même convention. Page des prédictions de l'espace achats : demi-intervalle correctement calculé.
- **Retours clients** : déduits des quantités vendues et du chiffre d'affaires (marges, exports, rapport périodique où le coût des ventes est également net des retours).
- **Tests** : 122.

## 31/10/2026 (suite 6) — Anciennes prédictions, marges au coût réel

- `95c87d8` poussé sur GitHub (cache, unités des prédictions, retours dans les marges).
- **Anciennes prédictions** : migration de données `stock.0007`. Les prédictions dont la borne haute est inférieure à la consommation prévue (bornes journalières de l'ancienne tâche IA) gardent leur consommation prévue, mais leurs bornes passent à « inconnues » et leur quantité recommandée (ancienne formule) est effacée ; les confiances exprimées entre 0 et 1 (ancien script de démonstration) sont ramenées sur 100. Base de dev : 400 prédictions mises à jour. Nouvelle commande `nettoyer_predictions` (avec `--apercu`) pour ne garder que la prédiction la plus récente de chaque produit — non exécutée.
- **Marges au coût réel** : chaque vente est valorisée au coût moyen du moment où elle a eu lieu (rejeu au CUMP permanent) au lieu du CUMP actuel appliqué à tout l'historique. Sur les données de démonstration, la page Marges et le rapport périodique sur tout l'historique donnent exactement le même chiffre d'affaires et le même coût des ventes.
- **Cache versionné** : le robot de parcours a révélé qu'après la modification du calcul, le cache servait encore des résultats de l'ancienne version (erreur 500 sur la page Marges). La clé de cache inclut désormais une version du calcul, à incrémenter à chaque changement de règle.
- **Tests** : 125.

