from .base import *

from cryptography.fernet import Fernet


DEBUG = False

_INSECURE_SECRET_KEYS = {
    "dev-only-star-sakura-secret-key",
    "change-this-in-production",
    "change-me",
    "changeme",
}
if not SECRET_KEY or SECRET_KEY.strip().lower() in _INSECURE_SECRET_KEYS:
    raise RuntimeError("DJANGO_SECRET_KEY must be a non-placeholder production secret.")
if len(SECRET_KEY) < 32:
    raise RuntimeError("DJANGO_SECRET_KEY must be at least 32 characters in production.")

if not AI_CREDENTIAL_ENCRYPTION_KEY:
    raise RuntimeError("AI_CREDENTIAL_ENCRYPTION_KEY must be set in production.")
try:
    Fernet(AI_CREDENTIAL_ENCRYPTION_KEY.encode("ascii"))
except (UnicodeEncodeError, TypeError, ValueError) as exc:
    raise RuntimeError(
        "AI_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key."
    ) from exc

if not ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set in production.")

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", [])
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [])

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", SECURE_SSL_REDIRECT)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", SECURE_SSL_REDIRECT)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
