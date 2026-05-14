from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


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
        admin.set_password("admin123456")
        admin.save()

        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Default admin {action}: admin / admin123456"))
