#!/usr/bin/env python
"""
Script de création d'un super administrateur pour StockMaster.
Exécution : python manage.py shell < create_superadmin.py
"""

import os
import django
from decouple import config
from django.utils.crypto import get_random_string

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from apps.accounts.models import Utilisateur, RoleUtilisateur

def run():
    """Fonction appelée par django-extensions runscript.

    Identifiants lus depuis .env (SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD).
    Si absents, un mot de passe aléatoire est généré et affiché une seule fois.
    """
    from apps.accounts.models import Utilisateur, RoleUtilisateur

    email = config('SUPERADMIN_EMAIL', default='')
    password = config('SUPERADMIN_PASSWORD', default='')
    first_name = "Super"
    last_name = "Admin"

    if not email:
        print("❌ Définissez SUPERADMIN_EMAIL dans .env avant d'exécuter ce script.")
        return
    if not password:
        password = get_random_string(16)
        print(f"ℹ️ SUPERADMIN_PASSWORD non défini : mot de passe généré : {password}")

    user, created = Utilisateur.objects.get_or_create(
        email=email,
        defaults={
            "username": email,
            "first_name": first_name,
            "last_name": last_name,
            "role": RoleUtilisateur.SUPER_ADMIN,
            "is_superuser": True,
            "is_staff": True,
            "est_actif": True,
            "is_active": True,
        }
    )

    if created:
        user.set_password(password)
        user.save()
        print(f"✅ Super Admin créé : {email}")
        print(f"   Mot de passe : {password}")
    else:
        user.role = RoleUtilisateur.SUPER_ADMIN
        user.is_superuser = True
        user.is_staff = True
        user.est_actif = True
        user.is_active = True
        user.set_password(password)
        user.save()
        print(f"⚠️ Utilisateur {email} existant, mis à jour en Super Admin.")
        print(f"   Mot de passe : {password}")

if __name__ == "__main__":
    run()