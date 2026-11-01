# Plan de refonte — design, thèmes, conformité, audit

Un commit par étape ; push à la fin. Cases cochées au fur et à mesure.

## Constat de départ
- 7 gabarits de base (un par rôle) + `templates/base.html`, chacun avec son CSS en ligne (~3 000 lignes dupliquées). Mêmes variables orange (`--or`…), mais déclarées 8 fois, avec des écarts (bleu `#2563eb` / `#3b82f6`, orange `--orange` / `--or`).
- Polices : Plus Jakarta Sans + Fira Code. Cible : Poppins (titres) + Tahoma (texte), chiffres en monospace.
- Aucune bannière de cookies, FAQ ni politique de confidentialité.

## Étapes

### 0. API produits (reliquat) — fait
Écriture réservée à l'admin entreprise et au gestionnaire, suppression désactivée (archivage), entreprise renseignée à la création.

### 1. Système de design commun — fait
- `static/css/stockmaster.css` : jetons (couleurs, ombres, rayons, espacements, typographie), composants (cartes, boutons, formulaires, tableaux, badges, onglets, modales, alertes), grilles flexbox/grid, animations (CSS pur, inspirées d'Animate.css / AOS, sans dépendance externe pour rester utilisables hors ligne dans la PWA).
- Polices Poppins + Tahoma, variante `prefers-reduced-motion` respectée.
- Un seul fichier de base partagé par tous les rôles ; chaque rôle ne garde que sa navigation. Couleurs identiques pour tous les rôles (le rôle se distingue par son badge, pas par sa couleur).
- Palette unique des statuts produits (OK / faible / critique / rupture) et des catégories, appliquée partout.

### 2. Thèmes par entreprise — fait
- Champ `theme` sur `ParametresEntreprise` (migration), 6 thèmes prédéfinis (Orange par défaut, Océan, Forêt, Violet, Rubis, Ardoise).
- Choix dans Paramètres de l'admin entreprise avec aperçu en direct ; le thème est appliqué à toute l'application via `data-theme` (jetons CSS redéfinis), tous rôles confondus.

### 3. Pages : alignement et cohérence
Passer en revue chaque page des 7 espaces + pages publiques : en-têtes, grilles, tableaux, formulaires alignés en flexbox/grid, responsive mobile.

### 4. Pages publiques et conformité
Bannière de consentement aux cookies (accepter / refuser / personnaliser, mémorisé), page FAQ, politique de confidentialité, mentions légales, conditions d'utilisation.

### 5. Actions du super admin et validations
Inventaire des actions du super admin, constat de ce qui est validé (confirmation, POST, journalisation), puis généralisation aux autres rôles : confirmations pour les actions destructrices, journal d'audit des actions sensibles.

### 6. Audit de sécurité et revue de code
`check --deploy`, matrice rôle × URL, isolation entre entreprises, CSRF, injection, téléversements, en-têtes de sécurité, limitation des tentatives de connexion, secrets, dépendances.

### 7. Tests par rôle et par cas de figure
Parcours automatisés pour chaque rôle (accès autorisé / refusé sur chaque route, cas limites des formulaires), robot de parcours des pages intégré à la CI.

### 8. Clôture
Documentation (HISTORY, TASKS, README), CI verte, push. La supervision (monitoring) et la facturation sont traitées ensuite, à part.
