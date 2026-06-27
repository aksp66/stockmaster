

from django.urls import path
from . import views

app_name = 'comptable'

urlpatterns = [
    # ── Tableau de bord ──────────────────────────────────────
    path(
        '',
        views.dashboard,
        name='dashboard',
    ),

    # ── Valorisation ─────────────────────────────────────────
    path(
        'valorisation/',
        views.valorisation,
        name='valorisation',
    ),
    path(
        'prix/',
        views.prix,
        name='prix',
    ),
    path(
        'marges/',
        views.marges,
        name='marges',
    ),
    path(
        'depreciation/',
        views.depreciation,
        name='depreciation',
    ),

    # ── Reporting ────────────────────────────────────────────
    path(
        'rapports/',
        views.rapports,
        name='rapports',
    ),
    path(
        'exports/',
        views.exports,
        name='exports',
    ),
]
