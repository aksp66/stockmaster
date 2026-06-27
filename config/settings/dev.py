from .base import *


DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.ngrok-free.dev', '192.168.1.66', ]
# Base de données Postgres local
DATABASES = {
 'default': {
  'ENGINE': 'django.db.backends.postgresql',
  'NAME': 'stockmaster',
  'USER': 'postgres',
  'PASSWORD': '',
  'HOST': 'localhost',
  'PORT': '5432',
 }
}

CSRF_TRUSTED_ORIGINS = [
    'https://turbulent-army-uncle.ngrok-free.dev',  # ton URL exacte
    # ou utilise un wildcard pour accepter tous les sous-domaines ngrok
    'https://*.ngrok-free.dev',
]

# Email en console
# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'          
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'ahlipedro66@gmail.com'
EMAIL_HOST_PASSWORD = 'mhxzdmstuovjlxgc'
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# ── CORS (pour la PWA en développement) ───────────────────────────────
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    #"https://stockmaster.votre-domaine.com",  
]
CORS_ALLOW_CREDENTIALS = True