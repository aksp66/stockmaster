

from django.urls import path
from . import views

app_name = 'auditeur'

urlpatterns = [
    # ── Tableau de bord ──────────────────────────────────────
    path(
        '', views.dashboard, name='dashboard'
    ),

    # ── Analyse ──────────────────────────────────────────────
    path(
        'mouvements/',
        views.mouvements,
        name='mouvements'
    ),
    path(
        'ecarts/',
        views.ecarts,
        name='ecarts'
    ),
    path(
        'valorisation/',
        views.valorisation,
        name='valorisation'
    ),
    path(
        'conformite/',
        views.conformite,
        name='conformite'
    ),

    # ── Traçabilité ──────────────────────────────────────────
    path(
        'logs/',
        views.logs,
        name='logs'
    ),

    # ── Exports ──────────────────────────────────────────────
    path(
        'exports/',
        views.exports,
        name='exports'
    ),
]
