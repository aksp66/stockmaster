from rest_framework.permissions import BasePermission, SAFE_METHODS

ROLES_LECTURE  = ["admin_ent", "gestionnaire", "responsable_achat",
                  "magasinier", "auditeur", "comptable", "super_admin"]
ROLES_ECRITURE = ["admin_ent", "gestionnaire", "magasinier"]

class IsMagasinier(BasePermission):
    """Permet de créer des mouvements de stock."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", "") in ROLES_ECRITURE

class IsGestionnaire(BasePermission):
    """Gestion complète des produits et mouvements."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", "") in ["admin_ent", "gestionnaire"]

class ReadOnlyOrGestionnaire(BasePermission):
    """Lecture : tous les rôles authentifiés ; écriture : gestionnaire et admin."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return getattr(request.user, "role", "") in ROLES_LECTURE
        return getattr(request.user, "role", "") in ROLES_ECRITURE