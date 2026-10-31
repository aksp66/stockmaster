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

---

## À faire

### P1 — Avant une mise en production réelle
- [ ] Sauvegardes automatiques PostgreSQL + dossier `media/` (voir la liste de vérification de [DEPLOIEMENT.md](DEPLOIEMENT.md)).
- [ ] Premier déploiement réel avec Caddy, puis dérouler la liste de vérification de `DEPLOIEMENT.md`.
- [ ] Valider les deux promesses restantes de la page d'accueil, qui ne sont pas des chiffres mesurés : « Support 7j/7 » et « Opérationnel en moins de 15 minutes ». Les garder seulement si elles sont vraies.
- [ ] **Formulaires de soumission non vérifiés en conditions réelles** : le robot a contrôlé l'affichage de toutes les pages et la correspondance des champs ; les formulaires critiques sont couverts par des tests, mais pas tous (catégories, emplacements, transferts, entrepôts, invitations). Les soumettre une fois chacun avec la base de démonstration.

### P2 — Fonctionnalités incomplètes
- [ ] **Module `apps/ia/views.py` (routes `/ia/…`)** : code hérité, inutilisable en l'état (templates `ia/*.html` absents ; champs et modèles inexistants : `date_prediction`, `consommation_prevue`, `actif`, `MouvementStock`, `LigneBonCommande`). Les écrans IA réellement utilisés sont `admin_entreprise` → IA et `responsable_achat` → Prédictions / Suggestions. Décider : supprimer ces routes ou les réécrire. Les tâches Celery (`apps/ia/tasks.py`) ne sont pas concernées.
- [ ] Tâches planifiées prévues mais jamais écrites (retirées de `config/celery.py`) : vérification des seuils d'alerte toutes les 4 h, statistiques fournisseurs hebdomadaires, email quotidien des stocks critiques.
- [ ] Formulaire fournisseur : champs sans colonne en base (code, description longue, site web, ville, code postal, délai de paiement, remise, devise). Les ajouter au modèle `Fournisseur` (migration) ou les retirer du formulaire.
- [ ] Remise par ligne de BC : appliquée au prix net à l'enregistrement mais non conservée. Ajouter un champ `remise` à `LigneCommande` si elle doit apparaître sur le PDF.
- [ ] `boncommande_changer_statut` (`/commandes/<id>/statut/<statut>/`) change l'état sur une requête GET. Le passer en POST ou le supprimer (les nouvelles actions envoyer / clôturer / annuler le remplacent).
- [ ] Création de BC depuis une suggestion IA (lien `?produit=…&qte=…` du tableau de bord) : le formulaire ne pré-remplit pas encore la ligne.
- [ ] **Paramètres de l'admin entreprise** (`/admin-entreprise/parametres/`) : page purement visuelle, rien n'est enregistré (notifications, seuil d'alerte par défaut, délai d'expiration). Créer un modèle de réglages par entreprise.
- [ ] **Ajustement depuis le formulaire de mouvement du gestionnaire** : toujours appliqué en retrait de stock (pas de choix « surplus / manque »). Ajouter le sens de l'ajustement au formulaire.
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
