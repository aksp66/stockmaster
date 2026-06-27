#!/usr/bin/env python
"""
Script de création d'un super administrateur pour StockMaster.
Exécution : python manage.py shell < create_superadmin.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from apps.accounts.models import Utilisateur, RoleUtilisateur

def run():
    """Fonction appelée par django-extensions runscript."""
    from apps.accounts.models import Utilisateur, RoleUtilisateur

    email = "ahlipedro66@gmail.com"
    password = "AAKSP@12"
    first_name = "Super"
    last_name = "Admin"

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