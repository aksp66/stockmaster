# Proposition : supervision, facturation, et sécurité avancée

Document de décision. Les choix recommandés sont en **gras** ; les points à vérifier avant engagement (tarifs, disponibilité d'un prestataire dans votre pays, obligations légales) sont signalés « à vérifier » : je ne les ai pas pu confirmer depuis le code.

## 1. Supervision (monitoring)

### Ce qui existe déjà
- Journal d'audit des actions sensibles (`AuditLog`) et journal des exports.
- Tâches planifiées Celery (analyse IA, alertes, rapports) mais **aucun suivi de leur réussite**.
- Aucun journal applicatif en fichier (`LOGGING` non configuré), aucune alerte en cas d'erreur 500, aucun contrôle de disponibilité.

### Ce qu'il faut surveiller (par ordre d'importance)
| Risque | Signal à suivre | Réaction |
|---|---|---|
| Le site ne répond plus | Contrôle externe toutes les minutes sur `/sante/` | Alerte immédiate (email + WhatsApp / SMS) |
| Erreurs 500 | Chaque exception, avec utilisateur, entreprise, page, pile d'appels | Alerte groupée, ticket |
| Celery ou Redis arrêtés | Dernière exécution de chaque tâche planifiée ; ping du broker | Alerte si l'analyse de 2 h n'a pas tourné |
| Base de données | Connexions, taille, requêtes lentes ; **dernière sauvegarde réussie** | Alerte si sauvegarde de plus de 26 h |
| Disque / mémoire du serveur | Occupation, swap | Alerte à 80 % |
| Sécurité | Pics d'échecs de connexion, blocages (`throttle`), désactivations | Alerte au super admin |
| Usage | Entreprises actives, produits, mouvements par jour | Tableau de bord pour piloter l'activité |

### Trois niveaux, du plus léger au plus complet
| Option | Contenu | Effort | Coût récurrent (à vérifier) |
|---|---|---|---|
| **A. Minimale (recommandée pour démarrer)** | Route `/sante/` (base, Redis, Celery, dernière sauvegarde) ; `LOGGING` vers `logs/` avec rotation ; **Sentry** pour les erreurs (offre gratuite suffisante au départ) ; **Uptime Kuma** (outil libre, auto-hébergé) pour la disponibilité et les alertes | 2 à 3 jours | Quasi nul (un petit serveur pour Uptime Kuma, ou un service externe gratuit) |
| B. Complète | A + métriques Prometheus (`django-prometheus`) + tableaux Grafana + suivi Celery (Flower) + agrégation de journaux | 6 à 8 jours | Un serveur dédié de supervision |
| C. Service géré | Datadog / Grafana Cloud | 2 jours | Payant, croît avec l'usage |

**Recommandation : A maintenant, B quand vous aurez plus d'une dizaine d'entreprises clientes.** Raison : A répond aux trois vrais risques (site tombé, erreurs invisibles, sauvegarde ou analyse nocturne en silence) pour un coût presque nul.

### Précautions de confidentialité
- Sentry : ne pas envoyer de données personnelles (`send_default_pii=False`), masquer les champs sensibles ; héberger en Europe ou auto-héberger si vos clients l'exigent.
- La **catégorie « mesure d'audience et supervision » du bandeau de cookies** ne s'applique qu'aux outils déposant un traceur dans le navigateur. La supervision côté serveur (Sentry backend, Uptime Kuma, journaux) n'en dépose pas ; en revanche, tout script de suivi côté navigateur doit tester `window.StockMasterConsent.has('mesure')`.
- Mentionner ces outils dans la politique de confidentialité.

### Plan d'exécution (option A)
1. `/sante/` + `LOGGING` + rotation des journaux.
2. Sentry (backend, Celery, JavaScript désactivé tant que le consentement n'est pas branché).
3. Tâche « battement de cœur » Celery Beat qui enregistre sa dernière exécution, contrôlée par `/sante/`.
4. Script de sauvegarde PostgreSQL + `media/` qui écrit sa date de réussite (déjà au backlog P1) ; contrôle dans `/sante/`.
5. Uptime Kuma : 3 contrôles (site, `/sante/`, certificat HTTPS) et canaux d'alerte.
6. Page « Santé de la plateforme » dans l'espace super admin (état des contrôles, usage par entreprise).

## 2. Facturation et moyens de paiement

### Décisions à prendre avant tout développement
1. **Modèle commercial** : abonnement mensuel / annuel par entreprise, avec **plans selon des limites mesurables** (utilisateurs, entrepôts, produits, analyses IA). *Recommandé* : 3 plans (Démarrage, Pro, Entreprise) + essai gratuit de 14 jours + remise à l'annuel. Les chiffres (prix) sont à fixer par vous.
2. **Devise** : FCFA (XOF) par défaut, seule devise de facturation au lancement.
3. **Qui paie et comment** : paiement en ligne automatique, ou paiement manuel (virement, mobile money) validé par vous ? **Recommandé : commencer par un hybride** — paiement en ligne pour les cas simples, validation manuelle pour les virements — afin de ne pas bloquer la vente.
4. **Obligations fiscales** (TVA, mentions obligatoires d'une facture, numérotation continue, conservation) : **à vérifier** avec votre comptable pour chaque pays de vos clients.

### Moyens de paiement : options (à vérifier : disponibilité, frais et conditions dans chaque pays)
| Moyen | Pour qui | Intérêt | Limite |
|---|---|---|---|
| **Mobile money** (T-Money, Flooz et équivalents) | Clients d'Afrique de l'Ouest | Moyen le plus répandu, pas besoin de carte | Pas de prélèvement automatique récurrent natif : relances à gérer |
| **Agrégateur régional** (ex. CinetPay, PayDunya, FedaPay, Flutterwave, Paystack) | Tous | Une seule intégration pour mobile money + cartes, API et webhooks | Frais par transaction ; chaque agrégateur couvre des pays différents |
| **Carte bancaire via Stripe** | Clients hors zone, grandes entreprises | Abonnements récurrents robustes, factures, relances | Disponibilité de compte marchand selon le pays de l'éditeur |
| **Virement bancaire** | Entreprises structurées | Aucun frais, pas de plafond | Rapprochement manuel |

**Recommandation : un agrégateur régional (mobile money + cartes) pour l'encaissement en ligne, plus le virement validé manuellement.** Stripe seulement si vous visez une clientèle hors zone. Choisir l'agrégateur après avoir vérifié, pour vos 2 ou 3 premiers pays cibles : couverture des opérateurs, frais, délais de versement, support de l'abonnement récurrent.

### Architecture proposée dans l'application
- **Modèles** : `Plan` (nom, prix, périodicité, limites), `Abonnement` (entreprise, plan, statut `essai / actif / en retard / suspendu / résilié`, début, fin de période, prochain paiement), `Facture` (numéro continu, lignes, montant, statut, PDF), `Paiement` (facture, moyen, référence prestataire, statut, montant).
- **Aucune donnée de carte** n'est stockée chez vous : le paiement se fait sur la page du prestataire (aucune charge PCI-DSS pour vous).
- **Webhooks du prestataire** : signature vérifiée, traitement **idempotent** (un même événement reçu deux fois ne crée qu'un paiement), journalisé dans `AuditLog`.
- **Lien avec l'accès** (réutilise l'existant) : un impayé fait passer l'abonnement « en retard » (bandeau d'alerte, accès normal), puis, après un **délai de grâce** (par exemple 7 à 14 jours), « suspendu » : l'entreprise est désactivée par le mécanisme déjà en place (`est_active`, donc ses utilisateurs sont bloqués) et **ses données sont conservées**. Le paiement réactive.
- **Limites des plans** appliquées à la création (utilisateurs, entrepôts, produits) avec un message clair et une invitation à changer de plan.
- **Factures PDF** avec le générateur déjà présent (reportlab), envoyées par email, téléchargeables par l'admin d'entreprise ; **espace « Facturation »** pour l'admin (plan, historique, moyen de paiement, factures).
- **Côté super admin** : liste des abonnements, impayés, chiffre d'affaires récurrent mensuel, actions manuelles (offrir un mois, valider un virement), toutes journalisées.
- **Relances automatiques** par tâche Celery (J-7, J-1, J+3 …) via les emails existants.

### Phasage
| Phase | Contenu | Effort |
|---|---|---|
| 1 | Modèles, plans, abonnements, essai, limites, espace Facturation (lecture), validation manuelle des virements, factures PDF | 6 à 8 jours |
| 2 | Intégration de l'agrégateur choisi : paiement, webhooks idempotents, rapprochement | 5 à 7 jours |
| 3 | Relances, délai de grâce, suspension et réactivation automatiques, tableau de bord de revenus | 4 à 5 jours |
| 4 | Fiscalité spécifique par pays, avoirs, remboursements, codes promo | selon besoin |

Les phases 1 et 2 suffisent pour encaisser ; la phase 3 évite le suivi manuel des impayés.

## 3. Sécurité avancée (« plus tard »)

### Authentification à deux facteurs (2FA)
- **TOTP** (application Google Authenticator, Microsoft Authenticator, Authy…) avec la bibliothèque `pyotp`, plus **10 codes de secours** à usage unique.
- **Obligatoire pour le super admin et les admins d'entreprise** (ils peuvent tout modifier), **facultative mais recommandée** pour les autres rôles.
- Parcours : activation dans le profil (QR code), second écran à la connexion, journalisation des activations / échecs, procédure de récupération par le super admin (avec confirmation d'identité) si un admin perd son appareil.
- La limitation des tentatives de connexion (déjà en place) s'applique aussi au second facteur.
- Effort : **3 à 4 jours**. Choisir SMS plutôt que TOTP n'est pas recommandé : coût, délais et détournement de carte SIM.

### Politique de sécurité du contenu (CSP)
- Les gabarits contiennent beaucoup de scripts et de styles **en ligne** : une CSP stricte les bloquerait. Plan en trois temps avec `django-csp` :
  1. **Mode rapport seul** : on enregistre les violations sans rien bloquer, pour mesurer l'ampleur (1 jour).
  2. Retirer progressivement les gestionnaires `onclick=` et les `<script>` en ligne au profit de fichiers statiques ou de `nonce` (4 à 6 jours, au fil des pages).
  3. Passer en mode appliqué, en gardant `style-src 'unsafe-inline'` tant que les styles en ligne subsistent.
- Gain : même si une faille XSS passait, l'attaquant ne pourrait ni charger de script externe ni exfiltrer facilement.
- Autres durcissements voisins : jeton de l'application mobile hors `localStorage` (cookie `HttpOnly` ou stockage natif), restriction de `/admin/` Django aux adresses de confiance dans le Caddyfile.

## 4. Ordre recommandé

1. **Cette semaine** : renseigner les `LEGAL_*` (mentions légales / CGU) et les faire relire ; confirmer ou retirer « Support 7j/7 » et « 15 minutes ».
2. **Supervision A** (2 à 3 jours) : avant le premier déploiement réel, puisqu'elle vous dit si ce déploiement se passe bien.
3. **Sauvegardes automatiques** (P1 existant), reliées à `/sante/`.
4. **Facturation phases 1 puis 2**, après décision sur le modèle commercial et l'agrégateur.
5. **2FA** avant d'ouvrir à des clients externes ; **CSP** en mode rapport dans la foulée, puis durcissement progressif.

## 5. Questions à trancher
1. Quels sont vos 2 ou 3 premiers pays clients (détermine l'agrégateur et la fiscalité) ?
2. Plans et limites : combien d'utilisateurs, d'entrepôts et de produits par plan ? Quels prix en FCFA ?
3. Essai gratuit : durée, et accès complet ou limité ?
4. Que se passe-t-il à l'impayé : délai de grâce de combien de jours avant la suspension ?
5. Qui reçoit les alertes de supervision, et par quel canal (email, WhatsApp, SMS) ?
