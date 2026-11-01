from rest_framework.permissions import BasePermission, SAFE_METHODS

ROLES_LECTURE  = ["admin_ent", "gestionnaire", "responsable_achat",
                  "magasinier", "auditeur", "comptable", "super_admin"]
ROLES_ECRITURE = ["admin_ent", "gestionnaire", "magasinier"]

class EntrepriseActive(BasePermission):
    """Refuse l'API aux utilisateurs dont l'entreprise est désactivée ou en attente d'activation."""
    message = "Votre entreprise est désactivée ou en attente d'activation."

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or getattr(user, "role", "") == "super_admin" or not user.entreprise_id:
            return True
        from apps.entreprises.models import entreprise_est_active
        return entreprise_est_active(user.entreprise_id)


class IsMagasinier(BasePermission):
    """Permet de créer des mouvements de stock."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", "") in ROLES_ECRITURE

class IsGestionnaire(BasePermission):
    """Gestion complète des produits et mouvements."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", "") in ["admin_ent", "gestionnaire"]

class LectureOuSaisieMouvements(BasePermission):
    """
    Mouvements de stock : consultation pour tous les rôles de l'entreprise, création réservée
    à l'admin entreprise, au gestionnaire et au magasinier (ni comptable, ni auditeur, ni achats).
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        roles = ROLES_LECTURE if request.method in SAFE_METHODS else ROLES_ECRITURE
        return getattr(request.user, "role", "") in roles

class ReadOnlyOrGestionnaire(BasePermission):
    """Lecture : tous les rôles authentifiés ; écriture : gestionnaire et admin entreprise uniquement."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return getattr(request.user, "role", "") in ROLES_LECTURE
        return getattr(request.user, "role", "") in ("admin_ent", "gestionnaire")