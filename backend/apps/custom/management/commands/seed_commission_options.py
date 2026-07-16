import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.custom.models import CommissionOption


class Command(BaseCommand):
    help = "Seed commission option metadata into the database."

    def handle(self, *args, **options):
        fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "commission_options.json"
        items = json.loads(fixture_path.read_text(encoding="utf-8"))

        created = 0
        updated = 0
        seen_codes = set()
        for item in items:
            seen_codes.add(item["code"])
            option, was_created = CommissionOption.objects.get_or_create(
                code=item["code"],
                defaults={
                    "title": item["title"],
                    "price_label": item.get("price_label", ""),
                    "sort_order": item.get("sort_order", 0),
                    "is_active": True,
                },
            )
            changed = False
            for field in ["title", "price_label", "sort_order"]:
                value = item.get(field, "" if field == "price_label" else 0)
                if getattr(option, field) != value:
                    setattr(option, field, value)
                    changed = True
            if not option.is_active:
                option.is_active = True
                changed = True
            if changed:
                option.save()
            if was_created:
                created += 1
            elif changed:
                updated += 1

        disabled = CommissionOption.objects.exclude(code__in=seen_codes).update(is_active=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"Commission options seeded: {created} created, {updated} updated, {disabled} disabled"
            )
        )
