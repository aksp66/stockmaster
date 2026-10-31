"""
Réglages utilisés par la suite de tests (`python manage.py test --settings=config.settings.test`).
Aucun service externe requis à part PostgreSQL : cache et emails en mémoire, Celery synchrone.
"""
from .dev import *

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Hachage rapide : les tests créent beaucoup d'utilisateurs
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
