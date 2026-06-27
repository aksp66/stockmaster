from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.stock.models import (
    Produit, Categorie, Mouvement, Alerte, Entrepot, Fournisseur
)

User = get_user_model()

class CategorieMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categorie
        fields = ["id", "nom"]

class FournisseurMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom"]

class EntrepotMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entrepot
        fields = ["id", "nom"]

class ProduitListSerializer(serializers.ModelSerializer):
    categorie_nom = serializers.CharField(source="categorie.nom", read_only=True, default="")
    statut_stock = serializers.SerializerMethodField()
    en_alerte = serializers.SerializerMethodField()
    quantite_totale = serializers.SerializerMethodField()

    class Meta:
        model = Produit
        fields = [
            "id", "sku", "nom", "unite_mesure",
            "quantite_totale", "seuil_alerte",
            "categorie", "categorie_nom",
            "statut_stock", "en_alerte", "est_actif",
        ]

    def get_quantite_totale(self, obj):
        return obj.quantite_totale()

    def get_statut_stock(self, obj):
        stock = obj.quantite_totale()
        seuil = obj.seuil_alerte or 0
        if stock == 0: return "rupture"
        if stock <= seuil: return "critique"
        if stock <= seuil * 2: return "faible"
        return "ok"

    def get_en_alerte(self, obj):
        return obj.quantite_totale() <= (obj.seuil_alerte or 0)

class ProduitDetailSerializer(ProduitListSerializer):
    class Meta(ProduitListSerializer.Meta):
        fields = ProduitListSerializer.Meta.fields + [
            "description", "prix_unitaire", "code_barres",
            "fournisseur_principal", "created_at", "updated_at",
        ]

class ProduitScanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produit
        fields = ["id", "sku", "nom", "code_barres", "quantite_totale", "seuil_alerte", "prix_unitaire"]

class MouvementSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_sku = serializers.CharField(source="produit.sku", read_only=True)
    utilisateur_nom = serializers.SerializerMethodField()
    entrepot_source_nom = serializers.CharField(source="entrepot_source.nom", read_only=True, default="")
    entrepot_destination_nom = serializers.CharField(source="entrepot_destination.nom", read_only=True, default="")

    class Meta:
        model = Mouvement
        fields = [
            "id", "type_mouvement", "quantite", "produit", "produit_nom", "produit_sku",
            "entrepot_source", "entrepot_source_nom",
            "entrepot_destination", "entrepot_destination_nom",
            "reference", "note", "lot_numero", "date_expiration",
            "date_mouvement", "utilisateur_nom",
        ]
        read_only_fields = ["id", "date_mouvement", "utilisateur_nom"]

    def get_utilisateur_nom(self, obj):
        if obj.utilisateur:
            return obj.utilisateur.get_full_name() or obj.utilisateur.username
        return ""

    def validate(self, data):
        type_mvt = data.get("type_mouvement")
        quantite = data.get("quantite")
        if quantite <= 0:
            raise serializers.ValidationError({"quantite": "La quantité doit être positive."})
        if type_mvt in ["sortie", "perte"]:
            ent_src = data.get("entrepot_source")
            if ent_src:
                from apps.stock.models import Stock
                stock = Stock.objects.filter(produit=data["produit"], entrepot=ent_src).first()
                if not stock or stock.quantite < quantite:
                    raise serializers.ValidationError({"quantite": "Stock insuffisant dans l'entrepôt source."})
        return data

class AlerteSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)

    class Meta:
        model = Alerte
        fields = ["id", "produit", "produit_nom", "type_alerte", "priorite", "message", "lue", "created_at"]
        read_only_fields = ["id", "created_at"]

class UserProfileSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role"]

class DashboardMobileSerializer(serializers.Serializer):
    total_produits = serializers.IntegerField()
    produits_en_alerte = serializers.IntegerField()
    mouvements_aujourd_hui = serializers.IntegerField()
    alertes_non_lues = serializers.IntegerField()
    valeur_stock_total = serializers.FloatField()
    derniers_mouvements = MouvementSerializer(many=True)
    alertes_critiques = AlerteSerializer(many=True)