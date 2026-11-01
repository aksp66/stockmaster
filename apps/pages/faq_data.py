"""Contenu de la FAQ publique. Chaque réponse décrit ce que l'application fait réellement aujourd'hui :
à mettre à jour avec les fonctionnalités, jamais l'inverse."""

CATEGORIES = [
    {'slug': 'demarrer', 'nom': 'Démarrer', 'icon': 'fas fa-rocket'},
    {'slug': 'stock', 'nom': 'Stock', 'icon': 'fas fa-boxes-stacked'},
    {'slug': 'ia', 'nom': 'IA et achats', 'icon': 'fas fa-brain'},
    {'slug': 'securite', 'nom': 'Sécurité et données', 'icon': 'fas fa-shield-halved'},
    {'slug': 'compte', 'nom': 'Comptes et apparence', 'icon': 'fas fa-users'},
]

QUESTIONS = [
    ('demarrer', 'fas fa-rocket', "Comment ouvrir un compte pour mon entreprise ?",
     "Remplissez le formulaire d'inscription de votre entreprise. Votre demande est examinée par l'équipe StockMaster, "
     "qui active le compte ; vous pouvez ensuite vous connecter et inviter vos collaborateurs depuis l'espace "
     "administrateur."),
    ('demarrer', 'fas fa-coins', "Quels sont les tarifs ?",
     "La facturation est en cours de définition. <a href=\"/contact/\">Contactez-nous</a> pour connaître les "
     "conditions applicables à votre entreprise."),
    ('demarrer', 'fas fa-mobile-screen', "Peut-on utiliser StockMaster sur téléphone ?",
     "Oui. L'application est une PWA : elle s'installe depuis le navigateur sur le téléphone ou l'ordinateur. "
     "Les mouvements saisis sans connexion sont mis en file d'attente puis synchronisés au retour du réseau."),
    ('stock', 'fas fa-warehouse', "Peut-on gérer plusieurs entrepôts ?",
     "Oui. Chaque entreprise peut créer plusieurs entrepôts, y définir des emplacements et transférer du stock de "
     "l'un à l'autre. Le stock d'un produit est suivi par entrepôt et en total."),
    ('stock', 'fas fa-barcode', "Comment enregistrer une entrée ou une sortie ?",
     "Depuis la page de scan (code-barres ou référence du produit), le mouvement rapide ou le formulaire de "
     "mouvement complet. Entrées, sorties, pertes, transferts, retours et ajustements sont journalisés avec leur "
     "auteur et leur date, et modifient le stock immédiatement."),
    ('stock', 'fas fa-bell', "Comment suis-je prévenu d'une rupture ?",
     "Une alerte est créée dès qu'un produit passe sous son seuil ou en rupture, ou qu'un lot approche de sa date "
     "d'expiration. L'administrateur choisit dans les Paramètres de recevoir ou non ces alertes par email, ainsi "
     "qu'un rapport hebdomadaire."),
    ('stock', 'fas fa-calculator', "Comment le stock est-il valorisé ?",
     "Au coût moyen unitaire pondéré (CUMP) en inventaire permanent, avec une valorisation FIFO également "
     "disponible. Le comptable dispose des rapports de période, des marges au coût réel de chaque vente et des "
     "exports CSV et PDF."),
    ('ia', 'fas fa-brain', "Comment fonctionne la prédiction IA ?",
     "Chaque nuit, un modèle de séries temporelles (Prophet, avec RandomForest en alternative) analyse l'historique "
     "des sorties de chaque produit et prévoit la consommation des 30 jours suivants, avec un score de confiance. "
     "Un produit doit avoir au moins 14 jours de données de sorties pour qu'une prévision soit calculée."),
    ('ia', 'fas fa-cart-shopping', "D'où viennent les quantités à commander suggérées ?",
     "De la consommation prévue (ou, à défaut, de la moyenne des sorties des 28 derniers jours), du délai de "
     "réapprovisionnement, du seuil d'alerte, du stock actuel et des commandes déjà en cours. Vous gardez la main : "
     "la suggestion préremplit un bon de commande que vous validez."),
    ('securite', 'fas fa-lock', "Mes données sont-elles protégées ?",
     "Les échanges se font en HTTPS, les mots de passe sont stockés sous forme hachée et chaque entreprise ne voit "
     "que ses propres données. Chaque rôle n'accède qu'aux écrans qui le concernent. Les détails figurent dans la "
     "<a href=\"/politique/\">politique de confidentialité</a>."),
    ('securite', 'fas fa-cookie-bite', "Quels cookies sont utilisés ?",
     "Uniquement des cookies nécessaires au fonctionnement (session et protection CSRF) et le cookie qui mémorise "
     "votre choix de consentement. Vous pouvez modifier ce choix à tout moment avec le lien « Gérer mes cookies » en "
     "bas de page."),
    ('securite', 'fas fa-file-export', "Puis-je récupérer mes données ?",
     "Oui. Les listes et rapports s'exportent en CSV (et en PDF pour les rapports comptables). Pour la suppression "
     "d'un compte, l'administrateur en fait la demande depuis ses Paramètres."),
    ('compte', 'fas fa-user-tag', "Quels rôles existent ?",
     "Administrateur de l'entreprise, gestionnaire de stock, responsable achat, magasinier, comptable et auditeur "
     "(lecture seule). Les rôles proposés dépendent du type d'entreprise ; l'administrateur invite les utilisateurs "
     "et leur attribue un rôle."),
    ('compte', 'fas fa-palette', "Peut-on personnaliser l'apparence ?",
     "Oui. L'administrateur choisit un thème de couleurs parmi six dans les Paramètres ; il s'applique à toute "
     "l'application, pour tous les utilisateurs de l'entreprise."),
    ('compte', 'fas fa-headset', "Comment contacter l'équipe ?",
     "Par la <a href=\"/contact/\">page de contact</a>. Joignez la page concernée et une description de ce que vous "
     "attendiez : cela accélère la réponse."),
]


def faqs():
    icones = {c['slug']: c['icon'] for c in CATEGORIES}
    return [{'categorie': cat, 'icone': icone or icones[cat], 'question': q, 'reponse': r}
            for cat, icone, q, r in QUESTIONS]
