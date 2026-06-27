from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model

from apps.stock.models import (
    Produit, Categorie, Mouvement, TypeMouvement, Alerte,
    Entrepot, Fournisseur, Stock
)
from .serializers import (
    ProduitListSerializer, ProduitDetailSerializer, ProduitScanSerializer,
    MouvementSerializer, AlerteSerializer,
    UserProfileSerializer,
    CategorieMinimalSerializer, EntrepotMinimalSerializer, FournisseurMinimalSerializer,
)
from .permissions import IsMagasinier, IsGestionnaire, ReadOnlyOrGestionnaire
from apps.gestionnaire.views import _appliquer_mouvement

User = get_user_model()

# ═══════════════════════════════════════════════════════════════════════
#  AUTHENTIFICATION JWT
# ═══════════════════════════════════════════════════════════════════════

class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({"detail": "Identifiants incorrects."}, status=401)
        if not user.is_active:
            return Response({"detail": "Compte désactivé."}, status=403)
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.pk,
                "username": user.username,
                "nom": user.get_full_name(),
                "email": user.email,
                "role": getattr(user, "role", ""),
            },
            "expires_in": 3600,
        })

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Déconnecté avec succès."})
        except Exception:
            return Response({"detail": "Token invalide."}, status=400)

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

# ═══════════════════════════════════════════════════════════════════════
#  DASHBOARD MOBILE
# ═══════════════════════════════════════════════════════════════════════

class DashboardMobileView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        today = timezone.now().date()
        entreprise = request.user.entreprise
        qs_produits = Produit.objects.filter(entreprise=entreprise, est_actif=True)
        total = qs_produits.count()
        en_alerte = sum(1 for p in qs_produits if p.quantite_totale() <= (p.seuil_alerte or 0))
        mouvements_today = Mouvement.objects.filter(produit__entreprise=entreprise, date_mouvement__date=today).count()
        alertes_non_lues = Alerte.objects.filter(produit__entreprise=entreprise, lue=False).count()
        valeur_total = sum((p.quantite_totale() or 0) * float(p.prix_unitaire or 0) for p in qs_produits)
        derniers = Mouvement.objects.filter(produit__entreprise=entreprise).select_related(
            "produit", "entrepot_source", "entrepot_destination", "utilisateur"
        ).order_by("-date_mouvement")[:10]
        alertes_crit = Alerte.objects.filter(produit__entreprise=entreprise, lue=False, priorite__in=["haute", "critique"]).select_related("produit").order_by("-created_at")[:5]
        data = {
            "total_produits": total,
            "produits_en_alerte": en_alerte,
            "mouvements_aujourd_hui": mouvements_today,
            "alertes_non_lues": alertes_non_lues,
            "valeur_stock_total": round(valeur_total, 2),
            "derniers_mouvements": MouvementSerializer(derniers, many=True, context={"request": request}).data,
            "alertes_critiques": AlerteSerializer(alertes_crit, many=True).data,
        }
        return Response(data)

# ═══════════════════════════════════════════════════════════════════════
#  PRODUITS
# ═══════════════════════════════════════════════════════════════════════

class ProduitViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ReadOnlyOrGestionnaire]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nom", "sku", "code_barres"]
    ordering_fields = ["nom", "prix_unitaire"]
    ordering = ["nom"]

    def get_queryset(self):
        qs = Produit.objects.filter(entreprise=self.request.user.entreprise, est_actif=True).select_related("categorie", "fournisseur_principal")
        cat_id = self.request.query_params.get("categorie")
        if cat_id:
            qs = qs.filter(categorie_id=cat_id)
        # Le filtre en_alerte ne peut pas être fait au niveau SQL simplement, donc on le fait en Python
        en_alerte = self.request.query_params.get("en_alerte")
        if en_alerte in ("1", "true"):
            ids = [p.id for p in qs if p.quantite_totale() <= (p.seuil_alerte or 0)]
            qs = qs.filter(id__in=ids)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return ProduitListSerializer
        if self.action == "scan":
            return ProduitScanSerializer
        return ProduitDetailSerializer

    @action(detail=False, methods=["get"], url_path="scan")
    def scan(self, request):
        code = request.query_params.get("code", "").strip()
        if not code:
            return Response({"detail": "Paramètre 'code' requis."}, status=400)
        produit = Produit.objects.filter(
            Q(sku__iexact=code) | Q(code_barres=code),
            entreprise=request.user.entreprise
        ).first()
        if produit:
            return Response(ProduitScanSerializer(produit).data)
        return Response({"detail": "Produit introuvable.", "code": code}, status=404)

    @action(detail=False, methods=["get"], url_path="alertes")
    def alertes(self, request):
        qs = Produit.objects.filter(entreprise=request.user.entreprise, est_actif=True)
        ids = [p.id for p in qs if p.quantite_totale() <= (p.seuil_alerte or 0)]
        produits = Produit.objects.filter(id__in=ids).select_related("categorie")
        return Response(ProduitListSerializer(produits, many=True).data)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        qs = Produit.objects.filter(entreprise=request.user.entreprise, est_actif=True)
        total = qs.count()
        ruptures = 0
        critiques = 0
        valeur_totale = 0
        for p in qs:
            stock = p.quantite_totale()
            if stock == 0:
                ruptures += 1
            elif stock <= (p.seuil_alerte or 0):
                critiques += 1
            valeur_totale += stock * float(p.prix_unitaire or 0)
        return Response({
            "total_produits": total,
            "en_rupture": ruptures,
            "en_alerte_critique": critiques,
            "valeur_stock": round(valeur_totale, 2),
            "taux_rupture": round(ruptures / total * 100, 1) if total else 0,
        })

    @action(detail=True, methods=["get"], url_path="mouvements")
    def mouvements(self, request, pk=None):
        produit = self.get_object()
        mvts = Mouvement.objects.filter(produit=produit).order_by("-date_mouvement")[:50]
        return Response(MouvementSerializer(mvts, many=True, context={"request": request}).data)

# ═══════════════════════════════════════════════════════════════════════
#  MOUVEMENTS DE STOCK
# ═══════════════════════════════════════════════════════════════════════

class MouvementViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MouvementSerializer
    ordering = ["-date_mouvement"]

    def get_queryset(self):
        qs = Mouvement.objects.filter(produit__entreprise=self.request.user.entreprise).select_related(
            "produit", "entrepot_source", "entrepot_destination", "utilisateur"
        )
        produit_id = self.request.query_params.get("produit")
        if produit_id:
            qs = qs.filter(produit_id=produit_id)
        type_mv = self.request.query_params.get("type")
        if type_mv:
            qs = qs.filter(type_mouvement=type_mv)
        depuis = self.request.query_params.get("depuis")
        if depuis:
            qs = qs.filter(date_mouvement__date__gte=depuis)
        return qs.order_by("-date_mouvement")[:200]

    @action(detail=False, methods=["post"], url_path="rapide")
    def rapide(self, request):
        required = ["produit_id", "type_mouvement", "quantite"]
        for field in required:
            if field not in request.data:
                return Response({"detail": f"Champ requis : {field}"}, status=400)
        produit = Produit.objects.filter(pk=request.data["produit_id"], entreprise=request.user.entreprise).first()
        if not produit:
            return Response({"detail": "Produit invalide."}, status=400)
        type_mvt = request.data["type_mouvement"]
        quantite = Decimal(str(request.data["quantite"]))
        entrepot_id = request.data.get("entrepot_id")
        entrepot = Entrepot.objects.filter(pk=entrepot_id, entreprise=request.user.entreprise).first() if entrepot_id else None
        if type_mvt == "sortie":
            stock = Stock.objects.filter(produit=produit, entrepot=entrepot).first()
            if not stock or stock.quantite < quantite:
                return Response({"detail": "Stock insuffisant."}, status=400)
        mvt = Mouvement.objects.create(
            type_mouvement=type_mvt,
            produit=produit,
            quantite=quantite,
            entrepot_source=entrepot if type_mvt in ("sortie", "perte") else None,
            entrepot_destination=entrepot if type_mvt == "entree" else None,
            utilisateur=request.user,
            note=request.data.get("commentaire", "Scan mobile")
        )
        _appliquer_mouvement(mvt)
        return Response({
            "succes": True,
            "mouvement_id": mvt.pk,
            "nouveau_stock": float(produit.quantite_totale()),
            "en_alerte": produit.quantite_totale() <= (produit.seuil_alerte or 0),
            "produit_nom": produit.nom,
            "message": f"✅ Mouvement enregistré — Stock : {produit.quantite_totale()} {produit.unite_mesure}",
        }, status=201)

# ═══════════════════════════════════════════════════════════════════════
#  ALERTES
# ═══════════════════════════════════════════════════════════════════════

class AlerteViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AlerteSerializer

    def get_queryset(self):
        qs = Alerte.objects.filter(produit__entreprise=self.request.user.entreprise).select_related("produit").order_by("-created_at")
        non_lues = self.request.query_params.get("non_lues")
        if non_lues in ("1", "true"):
            qs = qs.filter(lue=False)
        priorite = self.request.query_params.get("priorite")
        if priorite:
            qs = qs.filter(priorite=priorite)
        return qs[:100]

    def partial_update(self, request, *args, **kwargs):
        alerte = self.get_object()
        alerte.lue = True
        alerte.save(update_fields=["lue"])
        return Response(self.get_serializer(alerte).data)

    @action(detail=False, methods=["post"], url_path="lire-toutes")
    def lire_toutes(self, request):
        nb = Alerte.objects.filter(produit__entreprise=request.user.entreprise, lue=False).update(lue=True)
        return Response({"detail": f"{nb} alerte(s) marquée(s) comme lue(s)."})

    @action(detail=False, methods=["get"], url_path="compteur")
    def compteur(self, request):
        nb = Alerte.objects.filter(produit__entreprise=request.user.entreprise, lue=False).count()
        return Response({"non_lues": nb})

# ═══════════════════════════════════════════════════════════════════════
#  RÉFÉRENTIELS (lecture seule)
# ═══════════════════════════════════════════════════════════════════════

class CategorieViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorieMinimalSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return Categorie.objects.filter(entreprise=self.request.user.entreprise)

class EntrepotViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EntrepotMinimalSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return Entrepot.objects.filter(entreprise=self.request.user.entreprise, est_actif=True)

class FournisseurViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FournisseurMinimalSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return Fournisseur.objects.filter(entreprise=self.request.user.entreprise, est_actif=True)