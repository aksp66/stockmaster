from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from apps.entreprises.models import entreprise_est_active

CHEMINS_LIBRES = ('/static/', '/media/', '/comptes/')


class EntrepriseActiveMiddleware:
    """
    Un utilisateur dont l'entreprise est désactivée (ou en attente de validation) est déconnecté et ne peut plus
    travailler, quel que soit son rôle. Le super admin n'est rattaché à aucune entreprise : il n'est pas concerné.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (user is not None and user.is_authenticated and user.role != 'super_admin' and user.entreprise_id
                and not request.path.startswith(CHEMINS_LIBRES) and not entreprise_est_active(user.entreprise_id)):
            logout(request)
            messages.error(request, "Votre entreprise est désactivée ou en attente d'activation par l'équipe StockMaster. "
                                    "Contactez-nous si vous pensez qu'il s'agit d'une erreur.")
            return redirect('pages:accueil')
        return self.get_response(request)
