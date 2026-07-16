import os
import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


DEFAULT_ADMIN_PROFILE = {
    "displayName": "星野樱",
    "avatar": "",
    "intro": "用画笔创造无限可能的世界",
    "philosophy": "用色彩传递情感，用线条勾勒梦想",
    "skills": ["Clip Studio Paint", "Photoshop", "Procreate", "SAI", "Wacom Intuos"],
    "gender": "",
    "birthday": "",
    "signature": "用画笔创造无限可能的世界",
}


class Command(BaseCommand):
    help = "Create or update the default admin account."

    def handle(self, *args, **options):
        User = get_user_model()
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "is_admin": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.email = admin.email or "admin@example.com"
        admin.is_admin = True
        admin.is_staff = True
        admin.is_superuser = True
        admin.profile = {**DEFAULT_ADMIN_PROFILE, **(admin.profile or {})}
        admin.bio = admin.bio or DEFAULT_ADMIN_PROFILE["intro"]
        password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123456")
        admin.set_password(password)
        admin.save()

        action = "created" if created else "updated"
        message = f"Default admin {action}: admin"
        if created and not password:
            message += " (set DEFAULT_ADMIN_PASSWORD and rerun this command to choose a password)"
        self.stdout.write(self.style.SUCCESS(message))
