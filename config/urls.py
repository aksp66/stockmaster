from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.static import serve
import os

def serve_sw(request):
    """Servir le service worker depuis la racine (hors static)."""
    path = os.path.join(settings.BASE_DIR, 'static', 'pwa', 'sw.js')
    return serve(request, path, document_root=os.path.dirname(path))

def serve_manifest(request):
    """Servir le manifeste depuis la racine."""
    path = os.path.join(settings.BASE_DIR, 'static', 'pwa', 'manifest.json')
    return serve(request, path, document_root=os.path.dirname(path))

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.pages.urls')),
    path('comptes/', include('apps.accounts.urls')),
    path('superadmin/', include('apps.superadmin.urls')),
    path('admin-entreprise/', include('apps.admin_entreprise.urls')),
    path('gestionnaire/', include('apps.gestionnaire.urls')),
    path('responsable-achat/', include('apps.responsable_achat.urls')),
    path('magasinier/', include('apps.magasinier.urls')),
    path('auditeur/', include('apps.auditeur.urls')),
    path('comptable/', include('apps.comptable.urls')),
    path("ia/", include("apps.ia.urls")),
    
    path("auth/", include("rest_framework.urls")),
    path("api/v1/", include("apps.api.urls")),

    # Service Worker doit être servi depuis la racine
    path("sw.js", serve_sw, name="sw"),
    path("manifest.json", serve_manifest, name="manifest"),
]