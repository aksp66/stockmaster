

# Importe l'instance Celery pour qu'elle soit chargée avec Django
from .celery import app as celery_app

__all__ = ("celery_app",)
