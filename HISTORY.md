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


## 01/11/2026 — Prix de vente pratiqué, nettoyage des prédictions

- `8677ec7` poussé sur GitHub (anciennes prédictions, marges au coût réel, cache versionné).
- **Prix de vente pratiqué** : nouveau champ `Mouvement.prix_vente_snapshot`, renseigné à chaque vente et chaque retour client (par défaut le prix de vente du produit à ce moment, saisissable dans le formulaire de mouvement, pré-rempli). Le chiffre d'affaires du rapport et des marges l'utilise ; un changement de prix de vente ne modifie plus les ventes passées. La page Marges affiche le prix moyen pratiqué. Migration `stock.0008` : les 62 826 ventes et retours clients existants de la base de dev reçoivent le prix actuel de leur produit, le chiffre d'affaires est donc identique (1 160 251 477 FCFA sur la démo, rapport et marges égaux).
- **Bug corrigé au passage** : le prix d'achat par défaut d'un mouvement n'était jamais enregistré, le test « nouvel objet » (`not self.pk`) étant toujours faux avec une clé primaire UUID générée avant l'enregistrement. Remplacé par `_state.adding`.
- **Nettoyage des prédictions** : tâche Celery `apps.ia.tasks.nettoyer_predictions`, chaque dimanche à 3h30. Elle supprime les prédictions remplacées par une plus récente, en conservant 90 jours d'historique (`IA_CONFIG["CONSERVATION_PREDICTIONS_JOURS"]`) pour pouvoir comparer plus tard prévisions et ventes réelles. Commande : nouvelle option `--garder-jours`.
- **Environnement virtuel** : `.venv\` remplace `env\` dans le script de démarrage, la documentation et les services Linux ; dépendances installées dans `.venv`.
- **Tests** : 131.

### Suite — Prix de vente au scan et dans l'API mobile

- **Prix de vente pratiqué** saisissable partout où une sortie est enregistrée : page de scan et mouvement rapide du magasinier (champ affiché pour une sortie, pré-rempli avec le prix du produit), API mobile (`prix_vente` sur `/mouvements/rapide/`, `prix_vente_snapshot` sur `/mouvements/`). Les produits exposent leur prix de vente pour le pré-remplissage. Prix invalide (négatif, texte, NaN, infini) refusé ; vide : prix du produit.
- **Page de scan réparée** : depuis l'origine, la page envoyait `produit_id` et `type` alors que la vue attendait `code` et `action` ; tout enregistrement répondait « Action non reconnue ». La vue accepte les deux formes et renvoie ce que la page affiche (nouveau stock, entrepôt, heure, message d'erreur). Le motif saisi est enregistré. L'entrepôt par défaut des préférences est de nouveau présélectionné (balise `{% if %}` cassée par un formateur).
- **API `/api/v1/mouvements/`** (utilisée par la file hors ligne de la PWA) : la création n'appliquait pas le mouvement au stock, acceptait les produits et entrepôts d'une autre entreprise, et tout mouvement pouvait être modifié ou supprimé sans corriger le stock. Désormais : création et mise à jour du stock dans la même transaction, utilisateur enregistré, seuils vérifiés, entrepôts contrôlés selon le type, produits et entrepôts limités à l'entreprise ; modification et suppression refusées (405). `/mouvements/rapide/` exige un entrepôt valide et ne plante plus sur un identifiant mal formé.
- **Tests** : 147.

### Suite — Rôles de l'API mobile

- **Création de mouvements par l'API** (`/mouvements/` et `/mouvements/rapide/`) réservée à l'admin entreprise, au gestionnaire et au magasinier ; comptable, auditeur et responsable achat gardent la consultation (403 en écriture). Nouvelle permission `LectureOuSaisieMouvements`.
- **API des alertes** : le marquage comme lue (`PATCH /alertes/<id>/`) et le détail répondaient 404, car le queryset était découpé (`[:100]`) avant la recherche de l'élément ; même défaut sur le détail d'un mouvement (`[:200]`). Les listes restent limitées par la pagination. La création, le remplacement et la suppression d'alertes ne sont plus exposés : n'importe quel utilisateur pouvait créer une alerte, y compris sur le produit d'une autre entreprise.
- **Tests** : 152.

## 01/11/2026 (suite) — Refonte : étape 0, API produits

- Plan de la refonte dans `PLAN_REFONTE.md` (design commun, thèmes par entreprise, conformité, audit, tests par rôle).
- **API produits** : écriture réservée à l'admin entreprise et au gestionnaire (le magasinier pouvait modifier et supprimer) ; suppression remplacée par l'archivage (le produit garde son historique) ; l'entreprise est renseignée à la création (qui échouait) ; référence ou code-barres en double refusés proprement (erreur 500 auparavant) ; catégorie et fournisseur limités à l'entreprise.
- **Tests** : 157.

### Refonte, étape 1 — système de design commun

- Nouvelle feuille `static/css/stockmaster.css` (jetons de couleur, polices, composants, gabarit, animations, utilitaires flexbox / grid, statuts de stock et catégories, sélecteur de thème). Elle reprend le CSS du gabarit gestionnaire, le plus complet, et remplace les copies que contenaient les 8 gabarits de base : environ 1 550 lignes de CSS dupliqué en moins.
- **Une seule identité visuelle pour tous les rôles** : blanc et orange, barre latérale sombre, mêmes cartes, boutons, tableaux et formulaires. Le super admin, auparavant en thème sombre, passe au thème clair ; ses jetons sont des alias des jetons communs. Les autres espaces ne se distinguent plus que par leur navigation et le badge du rôle.
- **Polices** : Poppins pour les titres et boutons, Tahoma pour le texte (repli Segoe UI / Verdana), Fira Code pour les chiffres. Plus de Plus Jakarta Sans.
- **Thèmes** : toutes les couleurs de marque passent par des variables (`--or`, `--or-rgb`…). Cinq thèmes alternatifs sont déjà définis (`data-theme` = ocean, foret, violet, rubis, ardoise) ; leur sélection par entreprise vient à l'étape 2.
- **Palette des produits** : mêmes couleurs pour les statuts de stock (`st-ok`, `st-faible`, `st-critique`, `st-rupture`) et huit couleurs de catégories (`cat-0`…`cat-7`).
- Mouvement réduit respecté (`prefers-reduced-motion`), styles d'impression, cache hors ligne de la PWA mis à jour (v1.2.0).
- Vérifié par captures d'écran de chaque espace (Edge) ; 157 tests.

### Refonte, étape 2 — thèmes par entreprise

- Champ `theme` sur `ParametresEntreprise` (migration `entreprises.0003`), six thèmes : Orange (défaut), Océan, Forêt, Violet, Rubis, Ardoise.
- Nouvelle carte « Apparence » dans les Paramètres de l'admin entreprise : choix du thème avec aperçu immédiat sur la page, enregistré seulement au clic. Réservé à l'admin entreprise ; un thème inconnu est refusé.
- Le thème s'applique à tous les rôles de l'entreprise (attribut `data-theme` sur chaque gabarit, via le processeur de contexte `apps.entreprises.context_processors.theme`, mis en cache et invalidé à l'enregistrement). Les autres entreprises et le super admin gardent l'orange.
- Tests : 161.

### Refonte, étape 3 — cohérence et alignement des pages

- **Une seule règle et une seule palette pour les produits** : nouvelles balises `apps/stock/templatetags/stock_ui.py` (`st_badge`, `st_color`, `st_dim`, `cat_badge`). Statuts de stock rupture / alerte / faible (jusqu'à 2 × le seuil) / OK, mêmes couleurs dans les espaces gestionnaire, magasinier et achats et dans l'API ; chaque catégorie garde toujours la même couleur parmi huit. Remplace des conditions recopiées dans chaque gabarit, qui donnaient trois couleurs différentes selon la page.
- **Responsive** : audit automatisé (62 pages sans paramètre de tous les espaces, rendues dans Edge en écran étroit et large, détection de tout élément qui dépasse sans être dans une zone défilante). 29 pages débordaient ; règles communes ajoutées : tableaux défilant horizontalement dans leur carte, grilles à colonnes fixes qui se replient, en-têtes et barres de boutons qui passent à la ligne, fenêtres modales et notifications adaptées au mobile. Résultat : 62 pages sur 62 sans débordement, à 1440 px comme en écran étroit.
- Colonne SKU et prix des tableaux sans retour à la ligne.
- **Tests** : 164.

### Refonte, étape 4 — cookies, FAQ, confidentialité

- **Bannière de consentement aux cookies** sur toutes les pages publiques : Tout refuser / Personnaliser / Tout accepter (même poids visuel pour refuser et accepter), fenêtre de choix par catégorie, choix mémorisé 180 jours dans le cookie `sm_consent`, lien « Gérer mes cookies » dans le pied de page et dans la politique. Seuls les cookies nécessaires (session, CSRF, choix) sont déposés aujourd'hui ; la catégorie « mesure d'audience et supervision » est désactivée par défaut et exposée aux scripts futurs par `window.StockMasterConsent.has('mesure')` — tout outil de supervision ajouté plus tard devra la tester. Fichiers : `static/js/cookies.js`, `templates/partials/cookies.html`.
- **Politique de confidentialité** : la section cookies décrit le cookie de choix et le bandeau.
- **FAQ** réécrite à partir de `apps/pages/faq_data.py` (15 questions en 5 catégories, filtre « Tout voir »). Les anciennes réponses contenaient des affirmations fausses ou invérifiables : prévisions « à 30, 60 et 90 jours » (la tâche IA prévoit 30 jours), « nombre illimité d'entrepôts », « réponse sous 2h ouvrées ». Les nouvelles décrivent ce que l'application fait (14 jours de données minimum pour une prévision, valorisation CUMP / FIFO, six rôles, thèmes, PWA hors ligne, etc.).
- Reste à rédiger : mentions légales et conditions générales d'utilisation (contenu juridique à fournir), et à confirmer ou retirer « Support 7j/7 » et « Opérationnel en moins de 15 minutes » sur l'accueil.
- **Tests** : 168.

### Refonte, étape 5 — actions du super admin et validations

**Constat sur le super admin** : ses actions étaient déjà en POST uniquement, avec garde contre l'auto-désactivation. Mais aucune n'était journalisée (la page « Logs d'audit » lisait un modèle que rien n'alimentait, avec des filtres et un export CSV sans effet), il n'y avait aucune confirmation, et il pouvait se rétrograder ou désactiver le dernier super admin.

- **Un seul journal d'audit** : `apps.core.models.AuditLog` (déjà lu par l'espace auditeur). Le modèle en doublon de `superadmin` (vide) est supprimé. Nouveaux types : archivage de produit, annulation et clôture de bon de commande, suppression de fournisseur, modification des paramètres.
- **Toutes les actions du super admin sont journalisées** avec auteur, adresse IP, état avant / après : activation et désactivation d'entreprise, suppression douce, activation et désactivation d'utilisateur, changement de rôle. La page des logs filtre vraiment (recherche, famille d'action, dates), pagine en gardant les filtres et exporte en CSV.
- **Garde-fous** : impossible de désactiver ou rétrograder le dernier super admin actif, de modifier son propre rôle, ou de donner un rôle d'entreprise à un compte sans entreprise. Les changements de rôle et la suppression d'entreprise ne se font plus qu'en POST.
- **Mêmes validations pour les autres rôles** :
  - confirmation commune (`data-confirm`, fenêtre au style de l'application, `static/js/stockmaster.js`) sur les actions sans confirmation : désactivation d'entreprise ou d'utilisateur, analyse IA, acquittement de toutes les alertes, envoi et clôture d'un bon de commande ; le `confirm()` brut du navigateur est remplacé. Les actions qui avaient déjà un modal (archivage de produit, annulation de commande, validation d'inventaire, fournisseur) le gardent ;
  - journalisation des invitations, modifications, changements de rôle, désactivations et suppressions d'utilisateurs, des paramètres et du thème, de l'analyse IA, de l'archivage de produits, des transitions de bons de commande, de la suppression de fournisseurs et d'entrepôts ;
  - l'admin d'entreprise ne peut plus supprimer, désactiver ou rétrograder le dernier admin actif de son entreprise ;
  - le changement de statut d'un bon de commande par l'URL `/commandes/<id>/statut/<statut>/` n'accepte plus que POST (il modifiait l'état sur une simple requête GET).
- **Tests** : 181.

### Refonte, étape 6 — audit de sécurité et revue de code

Méthode : contrôles Django (`check --deploy`), recherche de motifs dangereux dans le code, audit générique calculé sur **toutes** les routes (matrice rôle × espace, puis chaque URL à identifiant essayée par un utilisateur d'une autre entreprise avec les identifiants réels de l'entreprise A, en GET et en POST, avec comparaison de l'état de la base avant et après), audit des dépendances (`pip-audit`).

**Failles et défauts corrigés**
- **XSS stockée dans les graphiques** : les tableaux de bord de l'auditeur, du comptable et la fiche produit insèrent des données dans un `<script>` avec `|safe`. Un nom de catégorie contenant `</script>` s'exécutait chez l'auditeur ou l'admin (élévation de privilège entre rôles). Nouveau filtre `json_js` qui échappe `<`, `>`, `&`.
- **Une entreprise désactivée continuait de travailler** : le contrôle `entreprise_active_required` existait mais n'était utilisé nulle part, si bien que « désactiver une entreprise » n'avait aucun effet, ni sur le web ni par l'API mobile. Nouveau middleware (utilisateur déconnecté avec un message) et authentification JWT qui refusent ses utilisateurs ; connexion API refusée. L'état est mis en cache une minute et invalidé à l'enregistrement de l'entreprise.
- **Aucune limitation des tentatives de connexion** (force brute) : 5 échecs par adresse IP et identifiant, 30 par adresse, blocage de 15 minutes, même avec le bon mot de passe ; connexion réussie = compteur remis à zéro ; vaut pour le web et l'API. L'adresse IP du journal d'audit ne peut plus être falsifiée par un en-tête `X-Forwarded-For` envoyé par le client.
- **Inscription** : la confirmation de l'email activait automatiquement l'entreprise, ce qui rendait inutile la validation par le super admin (liste « en attente d'activation »). L'entreprise reste maintenant en attente jusqu'à son activation. Réglable : `ENTREPRISE_VALIDATION_MANUELLE=False` rétablit l'ancien comportement.
- **Erreur 500 du super admin** : sans entreprise rattachée, tout espace d'entreprise plantait ; il est désormais renvoyé vers son tableau de bord.
- **Injection de formules dans les exports CSV** : un nom de produit ou de fournisseur commençant par `=`, `+`, `-` ou `@` était exécuté à l'ouverture dans Excel. Les 16 exports passent par `apps/core/csv_safe.py` (les nombres, même négatifs, ne sont pas modifiés).
- Recherche de produits du magasinier ouverte à tout utilisateur connecté : réservée aux rôles concernés. Import CSV de produits limité à 5 Mo. En-têtes de sécurité ajoutés (Referrer-Policy, Cross-Origin-Opener-Policy, X-Frame-Options, cookies HttpOnly et SameSite). Import inutilisé de `csrf_exempt` retiré.
- **Dépendances : 98 vulnérabilités connues** dans Django 6.0.4, Pillow 12.2.0, Django REST Framework 3.17.1 et WeasyPrint 68.1. Mises à jour vers Django 6.0.8, Pillow 13.0.0, DRF 3.18.2 et WeasyPrint 70.0 ; plus aucune vulnérabilité connue, tous les tests passent. `pip-audit` ajouté à la CI (sans bloquer la livraison).

**Constaté sans défaut** : aucune fuite ni modification entre entreprises sur toutes les URL à identifiant ; aucune réponse 500 sur ces requêtes hostiles ; matrice des accès conforme (les écarts volontaires sont documentés dans le test) ; pas de SQL brut, de `eval`, de désérialisation ni de commande système ; redirection après connexion sûre ; jetons d'invitation et de confirmation à usage unique et à durée limitée ; mots de passe hachés.

**Tests** : 206 (dont `test_securite_generique.py` : matrice des accès et isolation entre entreprises, qui couvrent automatiquement toute nouvelle route).
