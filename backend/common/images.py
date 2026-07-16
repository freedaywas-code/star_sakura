import base64
import binascii
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from rest_framework import serializers


ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}


def decode_base64_image(image_data):
    if not image_data:
        return None

    if ";base64," in image_data:
        header, payload = image_data.split(";base64,", 1)
        ext = header.split("/")[-1] or "png"
    else:
        payload = image_data
        ext = "png"

    ext = ext.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise serializers.ValidationError("Unsupported image type.")

    max_size = settings.MAX_IMAGE_UPLOAD_SIZE
    if ((len(payload) * 3) // 4) > max_size:
        raise serializers.ValidationError("Image is too large.")

    try:
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise serializers.ValidationError("Invalid image data.") from exc

    if len(decoded) > max_size:
        raise serializers.ValidationError("Image is too large.")

    return ContentFile(decoded, name=f"{uuid.uuid4().hex}.{ext}")
