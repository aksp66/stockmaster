
import os
from celery import Celery
from celery.schedules import crontab

# ── Paramètre Django par défaut ──────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("config")

# ── Charger la configuration depuis settings.py (préfixe CELERY_) ───────────
app.config_from_object("django.conf:settings", namespace="CELERY")

# ── Découverte automatique des tâches dans tous les apps Django ──────────────
app.autodiscover_tasks()


# ═══════════════════════════════════════════════════════════════════════════════
#  TÂCHES PLANIFIÉES (Celery Beat)
# ═══════════════════════════════════════════════════════════════════════════════

app.conf.beat_schedule = {

    # ── Prédictions IA ──────────────────────────────────────────────────────
    "lancer-predictions-ia-quotidien": {
        "task":     "apps.ia.tasks.lancer_toutes_predictions",
        "schedule": crontab(hour=2, minute=0),   # Chaque nuit à 2h00
        "options":  {"expires": 3600},
    },

    # ── Vérification des alertes de stock ──────────────────────────────────
    "verifier-alertes-stock": {
        "task":     "apps.inventory.tasks.verifier_seuils_alertes",
        "schedule": crontab(hour="*/4", minute=0),  # Toutes les 4h
        "options":  {"expires": 1800},
    },

    # ── Calcul des statistiques fournisseurs ───────────────────────────────
    "calculer-stats-fournisseurs": {
        "task":     "apps.purchases.tasks.calculer_stats_fournisseurs",
        "schedule": crontab(hour=1, minute=0, day_of_week="1"),  # Lundi 1h00
        "options":  {"expires": 7200},
    },

    # ── Envoi des emails de réapprovisionnement ─────────────────────────────
    "notifier-reapprovisionnement": {
        "task":     "apps.purchases.tasks.notifier_stocks_critiques",
        "schedule": crontab(hour=8, minute=0),  # Chaque matin à 8h00
        "options":  {"expires": 1800},
    },
}

app.conf.timezone = "UTC+0"  # UTC+0, adapte si besoin


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
