from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

import time

from django.conf import settings

from apps.entreprises.models import entreprise_est_active, reglages_session

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


class InactiviteSessionMiddleware:
    """
    Déconnecte l'utilisateur sans activité depuis le délai fixé par son entreprise (Paramètres → Sécurité des
    sessions), et applique le choix « déconnexion à la fermeture du navigateur ». Le super admin utilise les
    valeurs par défaut (SESSION_INACTIVITE_MINUTES).
    """
    CLE = '_derniere_activite'
    DUREE_MAX_COOKIE = 14 * 24 * 3600  # sans fermeture du navigateur, la session survit au plus 14 jours

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not request.path.startswith(CHEMINS_LIBRES[:2]):
            minutes, fermeture = reglages_session(None if user.role == 'super_admin' else user.entreprise_id)
            maintenant = time.time()
            derniere = request.session.get(self.CLE)
            if derniere is not None and maintenant - derniere > minutes * 60:
                logout(request)
                messages.info(request, "Vous avez été déconnecté après une période d'inactivité.")
                return redirect('accounts:connexion')
            request.session[self.CLE] = maintenant
            request.session.set_expiry(
                0 if fermeture and not request.session.get('_se_souvenir') else self.DUREE_MAX_COOKIE)
        return self.get_response(request)
