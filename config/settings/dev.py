from .base import *
from decouple import config

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.1.66'] + (
    [config('NGROK_HOST')] if config('NGROK_HOST', default='') else []
)
# Base de données Postgres local (identifiants lus depuis .env, voir .env.example)
DATABASES = {
 'default': {
  'ENGINE': 'django.db.backends.postgresql',
  'NAME': config('DB_NAME', default='stockmaster'),
  'USER': config('DB_USER', default='postgres'),
  'PASSWORD': config('DB_PASSWORD', default=''),
  'HOST': config('DB_HOST', default='localhost'),
  'PORT': config('DB_PORT', default='5432'),
 }
}

# CSRF : n'autorise que l'URL ngrok explicitement configurée (pas de wildcard ouvert à tous les tunnels).
CSRF_TRUSTED_ORIGINS = [f"https://{config('NGROK_HOST')}"] if config('NGROK_HOST', default='') else []

# Email — identifiants lus depuis .env (voir .env.example). Bascule en console si non configuré.
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = 'StockMaster <no-reply@stockmaster.local>'

# ── CORS (pour la PWA en développement) ───────────────────────────────
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
CORS_ALLOW_CREDENTIALS = True
