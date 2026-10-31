
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

    # Tâches prévues mais pas encore écrites (voir TASKS.md) : vérification périodique
    # des seuils d'alerte, statistiques fournisseurs, notification des stocks critiques.
}

# Fuseau horaire : CELERY_TIMEZONE dans config/settings/base.py


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
