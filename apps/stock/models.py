import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


# ==============================================================================
# UTILITAIRES
# ==============================================================================

class TimestampMixin(models.Model):
    """Mixin ajoutant created_at et updated_at à tous les modèles."""
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Créé le"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Modifié le"))

    class Meta:
        abstract = True


# ==============================================================================
# 1. CATÉGORIE
# ==============================================================================

class Categorie(TimestampMixin):
    """
    Catégorie de produit, avec support d'arborescence (auto-référencée).
    Exemple : Électronique > Téléphones > Smartphones
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=100, verbose_name=_("Nom"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sous_categories',
        verbose_name=_("Catégorie parente")
    )
    # Lié à l'entreprise (multi-tenant)
    entreprise = models.ForeignKey(
        'entreprises.Entreprise',
        on_delete=models.CASCADE,
        related_name='categories',
        verbose_name=_("Entreprise")
    )

    class Meta:
        verbose_name = _("Catégorie")
        verbose_name_plural = _("Catégories")
        ordering = ['nom']
        unique_together = [('nom', 'entreprise', 'parent')]

    def __str__(self):
        if self.parent:
            return f"{self.parent.nom} > {self.nom}"
        return self.nom

    def get_ancestors(self):
        """Retourne la liste des ancêtres (pour le fil d'Ariane)."""
        ancestors = []
        current = self.parent
        while current is not None:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors


# ==============================================================================
# 2. ENTREPÔT & EMPLACEMENT
# ==============================================================================

class Entrepot(TimestampMixin):
    """
    Entrepôt physique appartenant à une entreprise.
    Un entrepôt peut avoir plusieurs emplacements (allées, rayons, casiers).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=150, verbose_name=_("Nom"))
    adresse = models.TextField(blank=True, verbose_name=_("Adresse"))
    ville = models.CharField(max_length=100, blank=True, verbose_name=_("Ville"))
    pays = models.CharField(max_length=100, blank=True, verbose_name=_("Pays"))
    telephone = models.CharField(max_length=30, blank=True, verbose_name=_("Téléphone"))
    est_actif = models.BooleanField(default=True, verbose_name=_("Actif"))
    entreprise = models.ForeignKey(
        'entreprises.Entreprise',
        on_delete=models.CASCADE,
        related_name='entrepots',
        verbose_name=_("Entreprise")
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='entrepots_responsable',
        verbose_name=_("Responsable")
    )

    class Meta:
        verbose_name = _("Entrepôt")
        verbose_name_plural = _("Entrepôts")
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.entreprise.nom})"

    def valeur_totale_stock(self):
        """Calcule la valeur totale du stock dans cet entrepôt."""
        total = 0
        for stock in self.stocks.select_related('produit'):
            total += stock.quantite * stock.produit.prix_unitaire
        return total


class Emplacement(TimestampMixin):
    """
    Emplacement physique à l'intérieur d'un entrepôt.
    Exemple : Allée A, Rayon 3, Casier 12 → code "A-03-12"
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, verbose_name=_("Code"))
    description = models.CharField(max_length=200, blank=True, verbose_name=_("Description"))
    entrepot = models.ForeignKey(
        Entrepot,
        on_delete=models.CASCADE,
        related_name='emplacements',
        verbose_name=_("Entrepôt")
    )
    capacite_max = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Capacité maximale")
    )

    class Meta:
        verbose_name = _("Emplacement")
        verbose_name_plural = _("Emplacements")
        ordering = ['code']
        unique_together = [('code', 'entrepot')]

    def __str__(self):
        return f"{self.entrepot.nom} / {self.code}"


# ==============================================================================
# 3. FOURNISSEUR
# ==============================================================================

class Fournisseur(TimestampMixin):
    """
    Fournisseur de produits, lié à une entreprise.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=200, verbose_name=_("Nom"))
    contact = models.CharField(max_length=150, blank=True, verbose_name=_("Nom du contact"))
    email = models.EmailField(blank=True, verbose_name=_("Email"))
    telephone = models.CharField(max_length=30, blank=True, verbose_name=_("Téléphone"))
    adresse = models.TextField(blank=True, verbose_name=_("Adresse"))
    pays = models.CharField(max_length=100, blank=True, verbose_name=_("Pays"))
    delai_moyen_jours = models.PositiveSmallIntegerField(
        default=7,
        verbose_name=_("Délai moyen de livraison (jours)")
    )
    est_actif = models.BooleanField(default=True, verbose_name=_("Actif"))
    entreprise = models.ForeignKey(
        'entreprises.Entreprise',
        on_delete=models.CASCADE,
        related_name='fournisseurs',
        verbose_name=_("Entreprise")
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes internes"))

    class Meta:
        verbose_name = _("Fournisseur")
        verbose_name_plural = _("Fournisseurs")
        ordering = ['nom']

    def __str__(self):
        return self.nom


# ==============================================================================
# 4. PRODUIT
# ==============================================================================

class UniteMesure(models.TextChoices):
    UNITE    = 'unite',    _('Unité')
    KG       = 'kg',       _('Kilogramme')
    GRAMME   = 'g',        _('Gramme')
    LITRE    = 'l',        _('Litre')
    ML       = 'ml',       _('Millilitre')
    METRE    = 'm',        _('Mètre')
    CM       = 'cm',       _('Centimètre')
    BOITE    = 'boite',    _('Boîte')
    CARTON   = 'carton',   _('Carton')
    PALETTE  = 'palette',  _('Palette')


class Produit(TimestampMixin):
    """
    Produit référencé dans le catalogue de l'entreprise.
    Chaque produit peut être stocké dans plusieurs entrepôts (via le modèle Stock).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=200, verbose_name=_("Nom du produit"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    sku = models.CharField(
        max_length=100,
        verbose_name=_("SKU (référence interne)"),
        help_text=_("Stock Keeping Unit — identifiant unique interne")
    )
    code_barres = models.CharField(
        max_length=100, blank=True,
        verbose_name=_("Code-barres (EAN/UPC)")
    )
    categorie = models.ForeignKey(
        Categorie,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='produits',
        verbose_name=_("Catégorie")
    )
    unite_mesure = models.CharField(
        max_length=20,
        choices=UniteMesure.choices,
        default=UniteMesure.UNITE,
        verbose_name=_("Unité de mesure")
    )
    seuil_alerte = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Seuil d'alerte (quantité minimale)")
    )
    prix_unitaire = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Prix unitaire (HT)")
    )
    image = models.ImageField(
        upload_to='produits/',
        null=True, blank=True,
        verbose_name=_("Image du produit")
    )
    est_actif = models.BooleanField(default=True, verbose_name=_("Actif"))
    entreprise = models.ForeignKey(
        'entreprises.Entreprise',
        on_delete=models.CASCADE,
        related_name='produits',
        verbose_name=_("Entreprise")
    )
    fournisseur_principal = models.ForeignKey(
        Fournisseur,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='produits_principaux',
        verbose_name=_("Fournisseur principal")
    )
    prix_vente = models.DecimalField(
    max_digits=12, decimal_places=2,
    null=True, blank=True,
    verbose_name="Prix de vente HT"
    )
    delai_reappro = models.PositiveIntegerField(
        default=7,
        verbose_name=_("Délai de réapprovisionnement (jours)")
    )
    qte_min_commande = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Quantité minimale de commande")
    )

    class Meta:
        verbose_name = _("Produit")
        verbose_name_plural = _("Produits")
        ordering = ['nom']
        unique_together = [('sku', 'entreprise')]
        constraints = [
            # Unicité du code-barres par entreprise, uniquement quand il est renseigné
            # (le champ est optionnel : on ne veut pas qu'une chaîne vide bloque les autres produits).
            models.UniqueConstraint(
                fields=['entreprise', 'code_barres'],
                condition=models.Q(code_barres__gt=''),
                name='unique_code_barres_par_entreprise',
            ),
        ]

    def __str__(self):
        return f"[{self.sku}] {self.nom}"

    def quantite_totale(self):
        """Retourne la quantité totale disponible tous entrepôts confondus."""
        result = self.stocks.aggregate(total=models.Sum('quantite'))
        return result['total'] or 0

    def est_en_alerte(self):
        """Retourne True si le stock total est sous le seuil d'alerte."""
        return self.quantite_totale() <= self.seuil_alerte

    def valeur_stock_total(self):
        """Valeur financière du stock total (quantité × prix unitaire)."""
        return self.quantite_totale() * self.prix_unitaire


# ==============================================================================
# 5. STOCK (position courante)
# ==============================================================================

class Stock(TimestampMixin):
    """
    Représente la quantité d'un produit dans un entrepôt (et optionnellement un emplacement).
    C'est la "photographie" du stock à un instant T.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    produit = models.ForeignKey(
        Produit,
        on_delete=models.CASCADE,
        related_name='stocks',
        verbose_name=_("Produit")
    )
    entrepot = models.ForeignKey(
        Entrepot,
        on_delete=models.CASCADE,
        related_name='stocks',
        verbose_name=_("Entrepôt")
    )
    emplacement = models.ForeignKey(
        Emplacement,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='stocks',
        verbose_name=_("Emplacement")
    )
    quantite = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Quantité en stock")
    )

    class Meta:
        verbose_name = _("Stock")
        verbose_name_plural = _("Stocks")
        unique_together = [('produit', 'entrepot', 'emplacement')]

    def __str__(self):
        return f"{self.produit.nom} — {self.entrepot.nom} : {self.quantite} {self.produit.unite_mesure}"


# ==============================================================================
# 6. MOUVEMENT DE STOCK
# ==============================================================================

class TypeMouvement(models.TextChoices):
    ENTREE      = 'entree',      _('Entrée')
    SORTIE      = 'sortie',      _('Sortie')
    TRANSFERT   = 'transfert',   _('Transfert entre entrepôts')
    AJUSTEMENT  = 'ajustement',  _('Ajustement inventaire')
    RETOUR      = 'retour',      _('Retour fournisseur/client')
    PERTE       = 'perte',       _('Perte / Casse')


class Mouvement(TimestampMixin):
    """
    Enregistre chaque entrée, sortie, transfert ou ajustement de stock.
    C'est le journal comptable du stock — aucun mouvement n'est supprimé.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_mouvement = models.CharField(
        max_length=20,
        choices=TypeMouvement.choices,
        verbose_name=_("Type de mouvement")
    )
    produit = models.ForeignKey(
        Produit,
        on_delete=models.PROTECT,
        related_name='mouvements',
        verbose_name=_("Produit")
    )
    quantite = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0.01)],
        verbose_name=_("Quantité")
    )
    # Source et destination (pour transferts)
    entrepot_source = models.ForeignKey(
        Entrepot,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='mouvements_sortants',
        verbose_name=_("Entrepôt source")
    )
    entrepot_destination = models.ForeignKey(
        Entrepot,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='mouvements_entrants',
        verbose_name=_("Entrepôt destination")
    )
    emplacement_source = models.ForeignKey(
        Emplacement,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mouvements_source',
        verbose_name=_("Emplacement source")
    )
    emplacement_destination = models.ForeignKey(
        Emplacement,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mouvements_destination',
        verbose_name=_("Emplacement destination")
    )
    # Traçabilité
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='mouvements',
        verbose_name=_("Utilisateur")
    )
    reference = models.CharField(
        max_length=100, blank=True,
        verbose_name=_("Référence externe (BC, BL, facture...)")
    )
    note = models.TextField(blank=True, verbose_name=_("Note"))
    # Gestion des lots
    lot_numero = models.CharField(max_length=100, blank=True, verbose_name=_("Numéro de lot"))
    date_expiration = models.DateField(null=True, blank=True, verbose_name=_("Date d'expiration"))
    # Prix au moment du mouvement (pour FIFO/CUMP)
    prix_unitaire_snapshot = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Prix unitaire au moment du mouvement")
    )
    date_mouvement = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date du mouvement")
    )

    class Meta:
        verbose_name = _("Mouvement de stock")
        verbose_name_plural = _("Mouvements de stock")
        ordering = ['-date_mouvement']

    def __str__(self):
        return f"{self.get_type_mouvement_display()} — {self.produit.nom} × {self.quantite} ({self.date_mouvement:%d/%m/%Y})"

    def save(self, *args, **kwargs):
        """
        Snapshot du prix au moment de la création (pour l'historique comptable).
        Ne se recalcule pas si le mouvement est modifié ultérieurement.
        """
        if not self.pk and self.prix_unitaire_snapshot is None:
            self.prix_unitaire_snapshot = self.produit.prix_unitaire
        super().save(*args, **kwargs)


# ==============================================================================
# 7. BONS DE COMMANDE
# ==============================================================================

class StatutBonCommande(models.TextChoices):
    BROUILLON        = 'brouillon',        _('Brouillon')
    ENVOYE           = 'envoye',           _('Envoyé au fournisseur')
    RECU_PARTIEL     = 'recu_partiel',     _('Reçu partiellement')
    RECU_COMPLET     = 'recu_complet',     _('Reçu en totalité')
    CLOTURE          = 'cloture',          _('Clôturé')
    ANNULE           = 'annule',           _('Annulé')


class BonCommande(TimestampMixin):
    """
    Bon de commande envoyé à un fournisseur.
    Workflow : Brouillon → Envoyé → Reçu partiel → Reçu complet → Clôturé
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero = models.CharField(
        max_length=50, unique=True,
        verbose_name=_("Numéro de BC")
    )
    fournisseur = models.ForeignKey(
        Fournisseur,
        on_delete=models.PROTECT,
        related_name='bons_commande',
        verbose_name=_("Fournisseur")
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutBonCommande.choices,
        default=StatutBonCommande.BROUILLON,
        verbose_name=_("Statut")
    )
    date_commande = models.DateField(default=timezone.now, verbose_name=_("Date de commande"))
    date_livraison_prevue = models.DateField(null=True, blank=True, verbose_name=_("Date de livraison prévue"))
    date_livraison_effective = models.DateField(null=True, blank=True, verbose_name=_("Date de livraison effective"))
    utilisateur_createur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='bons_commande_crees',
        verbose_name=_("Créé par")
    )
    utilisateur_validation = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bons_commande_valides',
        verbose_name=_("Validé par")
    )
    entrepot_destination = models.ForeignKey(
        Entrepot,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bons_commande',
        verbose_name=_("Entrepôt de réception")
    )
    note = models.TextField(blank=True, verbose_name=_("Note"))
    entreprise = models.ForeignKey(
        'entreprises.Entreprise',
        on_delete=models.CASCADE,
        related_name='bons_commande',
        verbose_name=_("Entreprise")
    )

    class Meta:
        verbose_name = _("Bon de commande")
        verbose_name_plural = _("Bons de commande")
        ordering = ['-date_commande']

    def __str__(self):
        return f"BC-{self.numero} — {self.fournisseur.nom}"

    def total_ht(self):
        """Calcule le total HT du bon de commande."""
        return sum(
            ligne.quantite_commandee * ligne.prix_unitaire_ht
            for ligne in self.lignes.all()
        )

    def save(self, *args, **kwargs):
        """Génère automatiquement un numéro de BC si absent."""
        if not self.numero:
            from django.utils.timezone import now
            count = BonCommande.objects.filter(entreprise=self.entreprise).count() + 1
            self.numero = f"{now().year}-{count:05d}"
        super().save(*args, **kwargs)


class LigneCommande(TimestampMixin):
    """
    Ligne détaillée d'un bon de commande.
    Permet le suivi de la réception partielle.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bon_commande = models.ForeignKey(
        BonCommande,
        on_delete=models.CASCADE,
        related_name='lignes',
        verbose_name=_("Bon de commande")
    )
    produit = models.ForeignKey(
        Produit,
        on_delete=models.PROTECT,
        related_name='lignes_commande',
        verbose_name=_("Produit")
    )
    quantite_commandee = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0.01)],
        verbose_name=_("Quantité commandée")
    )
    quantite_recue = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Quantité reçue")
    )
    prix_unitaire_ht = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("Prix unitaire HT")
    )

    class Meta:
        verbose_name = _("Ligne de commande")
        verbose_name_plural = _("Lignes de commande")

    def __str__(self):
        return f"{self.produit.nom} × {self.quantite_commandee}"

    def quantite_restante(self):
        return self.quantite_commandee - self.quantite_recue

    def montant_ht(self):
        return self.quantite_commandee * self.prix_unitaire_ht


# ==============================================================================
# 8. INVENTAIRE
# ==============================================================================

class StatutInventaire(models.TextChoices):
    EN_COURS  = 'en_cours',  _('En cours')
    VALIDE    = 'valide',    _('Validé')
    ANNULE    = 'annule',    _('Annulé')


class InventaireSession(TimestampMixin):
    """
    Session d'inventaire physique dans un entrepôt.
    Durant une session, les magasiniers comptent les produits et saisissent les quantités réelles.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entrepot = models.ForeignKey(
        Entrepot,
        on_delete=models.PROTECT,
        related_name='sessions_inventaire',
        verbose_name=_("Entrepôt")
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutInventaire.choices,
        default=StatutInventaire.EN_COURS,
        verbose_name=_("Statut")
    )
    date_debut = models.DateTimeField(default=timezone.now, verbose_name=_("Date de début"))
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name=_("Date de fin"))
    utilisateur_demarrage = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='inventaires_demarre',
        verbose_name=_("Démarré par")
    )
    utilisateur_validation = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='inventaires_valides',
        verbose_name=_("Validé par")
    )
    note = models.TextField(blank=True, verbose_name=_("Note"))

    class Meta:
        verbose_name = _("Session d'inventaire")
        verbose_name_plural = _("Sessions d'inventaire")
        ordering = ['-date_debut']

    def __str__(self):
        return f"Inventaire {self.entrepot.nom} — {self.date_debut:%d/%m/%Y}"

    def ecart_total(self):
        """Retourne la somme des écarts (positifs et négatifs) de toutes les lignes."""
        return sum(ligne.ecart() for ligne in self.lignes.all())


class LigneInventaire(TimestampMixin):
    """
    Ligne d'une session d'inventaire : un produit compté, sa quantité théorique et réelle.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        InventaireSession,
        on_delete=models.CASCADE,
        related_name='lignes',
        verbose_name=_("Session d'inventaire")
    )
    produit = models.ForeignKey(
        Produit,
        on_delete=models.PROTECT,
        related_name='lignes_inventaire',
        verbose_name=_("Produit")
    )
    emplacement = models.ForeignKey(
        Emplacement,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Emplacement")
    )
    quantite_theorique = models.DecimalField(
        max_digits=14, decimal_places=2,
        verbose_name=_("Quantité théorique (système)")
    )
    quantite_comptee = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Quantité comptée (réelle)")
    )
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Note"))

    class Meta:
        verbose_name = _("Ligne d'inventaire")
        verbose_name_plural = _("Lignes d'inventaire")
        unique_together = [('session', 'produit', 'emplacement')]

    def __str__(self):
        return f"{self.produit.nom} — théorique: {self.quantite_theorique} / compté: {self.quantite_comptee}"

    def ecart(self):
        """Écart = quantité comptée - quantité théorique. Négatif = perte."""
        if self.quantite_comptee is None:
            return 0
        return self.quantite_comptee - self.quantite_theorique


# ==============================================================================
# 9. ALERTES
# ==============================================================================

class TypeAlerte(models.TextChoices):
    SEUIL_BAS    = 'seuil_bas',    _('Stock sous le seuil d\'alerte')
    PREDICTIVE   = 'predictive',   _('Rupture prévue par l\'IA')
    EXPIRATION   = 'expiration',   _('Produit proche de l\'expiration')
    RUPTURE      = 'rupture',      _('Rupture de stock (quantité = 0)')


class PrioriteAlerte(models.TextChoices):
    BASSE   = 'basse',   _('Basse')
    MOYENNE = 'moyenne', _('Moyenne')
    HAUTE   = 'haute',   _('Haute')
    CRITIQUE = 'critique', _('Critique')


class Alerte(TimestampMixin):
    """
    Alerte générée automatiquement (seuil, IA, expiration) ou manuellement.
    Les alertes sont consultées principalement par le gestionnaire de stock.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    produit = models.ForeignKey(
        Produit,
        on_delete=models.CASCADE,
        related_name='alertes',
        verbose_name=_("Produit")
    )
    entrepot = models.ForeignKey(
        Entrepot,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='alertes',
        verbose_name=_("Entrepôt (optionnel)")
    )
    type_alerte = models.CharField(
        max_length=20,
        choices=TypeAlerte.choices,
        verbose_name=_("Type d'alerte")
    )
    priorite = models.CharField(
        max_length=10,
        choices=PrioriteAlerte.choices,
        default=PrioriteAlerte.MOYENNE,
        verbose_name=_("Priorité")
    )
    message = models.TextField(verbose_name=_("Message"))
    lue = models.BooleanField(default=False, verbose_name=_("Lue"))
    date_lecture = models.DateTimeField(null=True, blank=True, verbose_name=_("Date de lecture"))
    lue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='alertes_lues',
        verbose_name=_("Lue par")
    )

    class Meta:
        verbose_name = _("Alerte")
        verbose_name_plural = _("Alertes")
        ordering = ['-created_at', 'lue']

    def __str__(self):
        return f"[{self.get_priorite_display()}] {self.get_type_alerte_display()} — {self.produit.nom}"

    def acquitter(self, utilisateur):
        """Marque l'alerte comme lue."""
        self.lue = True
        self.lue_par = utilisateur
        self.date_lecture = timezone.now()
        self.save(update_fields=['lue', 'lue_par', 'date_lecture'])


# ==============================================================================
# 10. MODULE IA — PRÉDICTIONS DE STOCK
# ==============================================================================

class PredictionStock(TimestampMixin):
    """
    Prédiction générée par l'IA (Prophet ou RandomForest) pour un produit donné.
    Indique la quantité prévue à une date cible, avec des bornes de confiance.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    produit = models.ForeignKey(
        Produit,
        on_delete=models.CASCADE,
        related_name='predictions',
        verbose_name=_("Produit")
    )
    entrepot = models.ForeignKey(
        Entrepot,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='predictions',
        verbose_name=_("Entrepôt")
    )
    date_cible = models.DateField(verbose_name=_("Date cible de la prédiction"))
    quantite_prevue = models.DecimalField(
        max_digits=14, decimal_places=2,
        verbose_name=_("Quantité prévue")
    )
    borne_inferieure = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Borne inférieure (intervalle de confiance)")
    )
    borne_superieure = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Borne supérieure (intervalle de confiance)")
    )
    confiance = models.FloatField(
        null=True, blank=True,
        verbose_name=_("Score de confiance (0 à 1)")
    )
    modele_utilise = models.CharField(
        max_length=50, blank=True,
        verbose_name=_("Modèle IA utilisé"),
        help_text=_("Ex: prophet, random_forest, arima")
    )
    quantite_recommandee_commande = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Quantité recommandée à commander")
    )
    precision_mape = models.FloatField(
        null=True, blank=True,
        verbose_name="Erreur absolue moyenne (MAPE en %)"
    )

    class Meta:
        verbose_name = _("Prédiction de stock")
        verbose_name_plural = _("Prédictions de stock")
        ordering = ['date_cible']

    def __str__(self):
        return f"Prédiction {self.produit.nom} — {self.date_cible} : {self.quantite_prevue}"


# ==============================================================================
# 11. SCAN LOG (traçabilité des scans code-barres)
# ==============================================================================

class ScanLog(TimestampMixin):
    """
    Enregistre chaque scan de code-barres effectué dans l'application.
    Utile pour l'audit et le débogage des opérations de scan.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='scans',
        verbose_name=_("Utilisateur")
    )
    produit = models.ForeignKey(
        Produit,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='scans',
        verbose_name=_("Produit identifié")
    )
    code_barre_scanne = models.CharField(
        max_length=100,
        verbose_name=_("Code-barres scanné")
    )
    action_attendue = models.CharField(
        max_length=50, blank=True,
        verbose_name=_("Action attendue"),
        help_text=_("Ex: entree, sortie, inventaire")
    )
    succes = models.BooleanField(default=True, verbose_name=_("Scan réussi"))
    message_erreur = models.CharField(
        max_length=255, blank=True,
        verbose_name=_("Message d'erreur si échec")
    )

    class Meta:
        verbose_name = _("Log de scan")
        verbose_name_plural = _("Logs de scan")
        ordering = ['-created_at']

    def __str__(self):
        statut = "✓" if self.succes else "✗"
        return f"{statut} Scan {self.code_barre_scanne} par {self.utilisateur} le {self.created_at:%d/%m/%Y %H:%M}"