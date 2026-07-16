import base64
import json
import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.artworks.models import Artwork


class Command(BaseCommand):
    help = "Seed the initial gallery artworks into the database."

    def _decode_image(self, image_data):
        if not image_data:
            return None
        ext = "jpg"
        if ";base64," in image_data:
            header, image_data = image_data.split(";base64,", 1)
            ext = (header.split("/")[-1] or ext).replace("jpeg", "jpg")
        return ContentFile(base64.b64decode(image_data), name=f"initial-{uuid.uuid4().hex}.{ext}")

    def handle(self, *args, **options):
        fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "initial_artworks.json"
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
            title = item["title"]
            tag = item["tag"]
            artwork, was_created = Artwork.objects.get_or_create(
                owner=admin,
                title=title,
                category=tag,
                defaults={
                    "description": title,
                    "tags": [tag],
                    "price": 0,
                    "is_available": True,
                },
            )
            if was_created:
                image = self._decode_image(item.get("image_data", ""))
                if image:
                    artwork.image.save(image.name, image, save=False)
                artwork.save()
                created += 1
                continue

            changed = False
            if artwork.description != title:
                artwork.description = title
                changed = True
            if artwork.tags != [tag]:
                artwork.tags = [tag]
                changed = True
            if not artwork.image:
                image = self._decode_image(item.get("image_data", ""))
                if image:
                    artwork.image.save(image.name, image, save=False)
                    changed = True
            if changed:
                artwork.save()
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Initial artworks seeded: {created} created, {updated} updated"))
