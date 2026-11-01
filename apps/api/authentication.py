from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication


class EntrepriseJWTAuthentication(JWTAuthentication):
    """
    Authentification JWT qui refuse aussi les utilisateurs dont l'entreprise est désactivée ou en attente
    d'activation. Placée ici, la règle vaut pour toutes les vues de l'API, même celles qui redéfinissent leurs permissions.
    """

    def authenticate(self, request):
        resultat = super().authenticate(request)
        if resultat is not None:
            user = resultat[0]
            if getattr(user, 'role', '') != 'super_admin' and user.entreprise_id:
                from apps.entreprises.models import entreprise_est_active
                if not entreprise_est_active(user.entreprise_id):
                    raise PermissionDenied("Votre entreprise est désactivée ou en attente d'activation.")
        return resultat
