# apps/accounts/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*roles):
    """
    Décorateur vérifiant que l'utilisateur connecté possède l'un des rôles requis.
    Usage : @role_required('gestionnaire', 'admin_ent')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('accounts:connexion')
            # Super admin a toujours accès ; sinon le rôle doit être explicitement autorisé.
            if request.user.role == 'super_admin' or request.user.role in roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, "Vous n'avez pas accès à cette section.")
            return redirect('pages:accueil')
        return wrapped
    return decorator


def entreprise_active_required(view_func):
    """Vérifie que l'entreprise de l'utilisateur est active."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:connexion')
        if request.user.entreprise and not request.user.entreprise.est_active:
            messages.error(request, "Votre entreprise est en attente d'activation.")
            return redirect('pages:accueil')
        return view_func(request, *args, **kwargs)
    return wrapped


def superadmin_required(view_func):
    """Décorateur pour les vues réservées aux super admins."""
    return role_required('super_admin')(view_func)