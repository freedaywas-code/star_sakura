import json
from datetime import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.inspirations.models import Inspiration


class Command(BaseCommand):
    help = "Seed the initial inspiration posts into the database."

    def _parse_created_at(self, value):
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed)
        return parsed

    def handle(self, *args, **options):
        fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "initial_inspirations.json"
        items = json.loads(fixture_path.read_text(encoding="utf-8"))

        User = get_user_model()
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "is_admin": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        created = 0
        updated = 0
        for item in items:
            inspiration, was_created = Inspiration.objects.get_or_create(
                owner=admin,
                title=item["title"],
                defaults={
                    "tag": item.get("tag", ""),
                    "content": item.get("content", ""),
                },
            )
            changed = was_created
            if inspiration.tag != item.get("tag", ""):
                inspiration.tag = item.get("tag", "")
                changed = True
            if inspiration.content != item.get("content", ""):
                inspiration.content = item.get("content", "")
                changed = True
            if changed:
                inspiration.save()
            created_at = self._parse_created_at(item.get("created_at"))
            if created_at:
                Inspiration.objects.filter(pk=inspiration.pk).update(created_at=created_at)
            if was_created:
                created += 1
            elif changed:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Initial inspirations seeded: {created} created, {updated} updated"))
