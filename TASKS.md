# Tâches — StockMaster

Suivi de ce qui est fait et de ce qui reste à faire. Mettre à jour ce fichier à chaque étape. L'historique détaillé est dans [HISTORY.md](HISTORY.md).

Priorités : **P1** bloquant ou risque pour les données · **P2** fonctionnalité incomplète · **P3** amélioration.

---

## Fait

### Juin 2026 — audit
- [x] Contrôle d'accès par rôle réellement appliqué (`role_required`)
- [x] Secrets sortis du code (`.env`), `prod.py` fonctionnel
- [x] Stock jamais négatif (verrou + transaction), signe des ajustements d'inventaire, réception de BC qui alimente le stock
- [x] PWA : manifeste, Service Worker, icônes
- [x] `requirements.txt`

### Octobre 2026
- [x] Migrations `stock.0004` / `stock.0005` appliquées en local
- [x] Bons de commande : envoyer / clôturer / annuler / PDF, liste, filtres, export CSV
- [x] Bons de commande : création avec lignes, réception depuis l'interface, numérotation sans collision entre entreprises
- [x] Fiche fournisseur (`fournisseur_detail`), enregistrement complet du formulaire fournisseur
- [x] Tableau de bord achats (template réparé, données branchées)
- [x] Inventaire magasinier : `inventaire_sauvegarder` + page de saisie réparée
- [x] Avis clients (`soumettre_avis`, modèle `Avis`, modération dans l'admin)
- [x] Module IA : redirection, noms de rôles, filtrage par entreprise
- [x] Erreur 500 du formulaire de mouvement (`uuid.UUID` dans un `except`)
- [x] Celery Beat nettoyé (tâches fantômes, fuseau invalide)
- [x] 39 tests sur les points critiques + `config.settings.test`
- [x] `demarrage.bat` / `demarrage.ps1` + `DEMARRAGE.md`
- [x] Déploiement Caddy + waitress/gunicorn sans Docker + `DEPLOIEMENT.md`
- [x] CI GitHub Actions
- [x] `HISTORY.md`, `TASKS.md`, Readme à jour

### Octobre 2026 (suite) — vérification des espaces, chiffres publics, Tailwind
- [x] Vérification page par page de tous les espaces (robot de parcours sur une base de démonstration + contrôle des champs de formulaire) et correction des décalages templates / modèles
- [x] Produit : la modification ne désactive plus le produit et ne réinitialise plus l'unité ni le fournisseur
- [x] Mouvement : prix d'achat, date et motif saisis enregistrés ; présélection du produit
- [x] Fiche produit : graphique, historique paginé avec stock après mouvement, synthèse IA
- [x] Magasinier : page Alertes, tableau de bord, historique de scan, préférences, motif du mouvement rapide
- [x] Auditeur : journal d'audit et conformité alignés sur les vrais champs
- [x] Suggestions d'achat : erreur 500 corrigée
- [x] Site public : chiffres réels (entreprises actives, avis publiés) à la place des chiffres et témoignages inventés
- [x] Tailwind compilé (`static/css/output.css`, v3.4.17) à la place du CDN, rendu vérifié identique
- [x] 55 tests (dont affichage de chaque page de chaque espace)

### Octobre 2026 (suite 2) — paramètres, ajustements, formulaires secondaires
- [x] Paramètres de l'admin entreprise enregistrés (modèle `ParametresEntreprise`) et réellement utilisés : seuil par défaut des nouveaux produits, emails d'alerte, alertes d'expiration, rapport hebdomadaire, suggestions IA par email (tâches Celery Beat)
- [x] Ajustement de stock : choix « surplus / manque » ; mouvement sans entrepôt refusé
- [x] Tous les formulaires secondaires soumis et testés (catégories, emplacements, transferts, import CSV, inventaires, alertes, utilisateurs, invitations, entreprise, entrepôts, fournisseurs, paramètres achats, API de scan, super admin, inscription)
- [x] Champs numériques des formulaires : plus de virgule décimale qui vidait les champs prix / quantités en modification
- [x] 93 tests

### Octobre 2026 (suite 3) — retours, réapprovisionnement, seuils
- [x] Retour : retour client (entrée) ou retour fournisseur (sortie), choisi dans le formulaire ; signe +/− correct dans tous les historiques
- [x] Quantité suggérée calculée sur la consommation prévue (IA, ou moyenne des sorties sur 28 jours), le délai de réappro, le stock de sécurité, la quantité minimale et les commandes en cours (`apps/stock/reappro.py`, commun aux trois écrans)
- [x] Bouton « Commander » des suggestions : bon de commande pré-rempli
- [x] Seuils vérifiés après réception de commande, validation d'inventaire, API mobile et stock initial ; alertes clôturées quand le stock remonte
- [x] 111 tests

---

## À faire

### P1 — Avant une mise en production réelle
- [ ] Sauvegardes automatiques PostgreSQL + dossier `media/` (voir la liste de vérification de [DEPLOIEMENT.md](DEPLOIEMENT.md)).
- [ ] Premier déploiement réel avec Caddy, puis dérouler la liste de vérification de `DEPLOIEMENT.md`.
- [ ] Valider les deux promesses restantes de la page d'accueil, qui ne sont pas des chiffres mesurés : « Support 7j/7 » et « Opérationnel en moins de 15 minutes ». Les garder seulement si elles sont vraies.
- [ ] Configurer le SMTP en production (`EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`) et vérifier la réception des emails d'alerte, du rapport hebdomadaire et des suggestions IA (ils dépendent aussi de Celery Beat).

### P2 — Fonctionnalités incomplètes
- [ ] **Module `apps/ia/views.py` (routes `/ia/…`)** : code hérité, inutilisable en l'état (templates `ia/*.html` absents ; champs et modèles inexistants : `date_prediction`, `consommation_prevue`, `actif`, `MouvementStock`, `LigneBonCommande`). Les écrans IA réellement utilisés sont `admin_entreprise` → IA et `responsable_achat` → Prédictions / Suggestions. Décider : supprimer ces routes ou les réécrire. Les tâches Celery (`apps/ia/tasks.py`) ne sont pas concernées.
- [ ] Statistiques fournisseurs hebdomadaires (tâche prévue, jamais écrite).
- [ ] Rapports du comptable (stock début / entrées / sorties / stock fin, valorisation) : ne comptent que les types « entrée » et « sortie » ; les retours, pertes et ajustements n'y figurent pas.
- [ ] Prédictions IA : une seule prédiction (total sur 30 jours) est conservée par produit ; les écrans IA de l'admin entreprise et le script de démonstration (`scripts/seed.py`, qui génère des valeurs proches du stock) n'utilisent pas tous cette convention.
- [ ] Formulaire fournisseur : champs sans colonne en base (code, description longue, site web, ville, code postal, délai de paiement, remise, devise). Les ajouter au modèle `Fournisseur` (migration) ou les retirer du formulaire.
- [ ] Remise par ligne de BC : appliquée au prix net à l'enregistrement mais non conservée. Ajouter un champ `remise` à `LigneCommande` si elle doit apparaître sur le PDF.
- [ ] `boncommande_changer_statut` (`/commandes/<id>/statut/<statut>/`) change l'état sur une requête GET. Le passer en POST ou le supprimer (les nouvelles actions envoyer / clôturer / annuler le remplacent).
- [ ] Options d'inventaire affichées mais non implémentées : « masquer le stock théorique aux compteurs » et « ajustement automatique ».
- [ ] Bon de commande : « Envoyé le » toujours vide (pas de champ `date_envoi`). L'ajouter, et l'enregistrer lors de l'envoi.

### P3 — Améliorations
- [ ] Étendre les tests : API REST (JWT, scan, mouvements hors ligne), exports CSV/PDF, valorisation CUMP/FIFO du comptable, tâches IA.
- [ ] Performance : `_calculer_suggestions` exécute plusieurs requêtes par produit (appelée sur le tableau de bord achats) ; à optimiser ou mettre en cache si le catalogue dépasse quelques centaines de produits.
- [ ] Interface de modération des avis dans l'espace super admin (aujourd'hui : admin Django).
- [ ] Ménage : dossier `.venv/` en double de `env/` (non versionné), `GUIDE_*.txt` à relire et éventuellement convertir en Markdown.
- [ ] Journalisation (`LOGGING`) en production vers `logs/`.
- [ ] Tableau de bord auditeur : icône par type d'action dans le fil d'activité (toujours l'icône par défaut).
- [ ] Préférences de scan du magasinier (sons, vibration…) : la section est masquée tant qu'aucune n'est implémentée.
- [ ] Intégrer le robot de parcours des pages (`string_if_invalid` + échecs de résolution) à la CI pour détecter automatiquement tout nouveau décalage template / modèle.
