
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
    "nettoyer-predictions-hebdo": {
        "task":     "apps.ia.tasks.nettoyer_predictions",
        "schedule": crontab(hour=3, minute=30, day_of_week="0"),  # Dimanche 3h30, après les prédictions
        "options":  {"expires": 7200},
    },

    # ── Notifications (selon les Paramètres de chaque entreprise) ──────────
    "verifier-expirations": {
        "task":     "apps.admin_entreprise.tasks.verifier_expirations",
        "schedule": crontab(hour=6, minute=0),   # Chaque matin à 6h00
        "options":  {"expires": 3600},
    },
    "envoyer-suggestions-ia": {
        "task":     "apps.admin_entreprise.tasks.envoyer_suggestions_ia",
        "schedule": crontab(hour=6, minute=30),  # Après les prédictions de la nuit
        "options":  {"expires": 3600},
    },
    "envoyer-rapports-hebdo": {
        "task":     "apps.admin_entreprise.tasks.envoyer_rapports_hebdo",
        "schedule": crontab(hour=7, minute=0, day_of_week="1"),  # Lundi 7h00
        "options":  {"expires": 7200},
    },

    # Tâches prévues mais pas encore écrites (voir TASKS.md) : vérification périodique
    # des seuils d'alerte, statistiques fournisseurs.
}

# Fuseau horaire : CELERY_TIMEZONE dans config/settings/base.py


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
