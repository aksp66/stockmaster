from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

router = DefaultRouter()
router.register("produits", views.ProduitViewSet, basename="produit")
router.register("mouvements", views.MouvementViewSet, basename="mouvement")
router.register("alertes", views.AlerteViewSet, basename="alerte")
router.register("categories", views.CategorieViewSet, basename="categorie")
router.register("entrepots", views.EntrepotViewSet, basename="entrepot")
router.register("fournisseurs", views.FournisseurViewSet, basename="fournisseur")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="api_login"),
    path("auth/logout/", views.LogoutView.as_view(), name="api_logout"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="api_token_refresh"),
    path("auth/profile/", views.ProfileView.as_view(), name="api_profile"),
    path("mobile/dashboard/", views.DashboardMobileView.as_view(), name="api_dashboard_mobile"),
    path("", include(router.urls)),
]