import os
from pathlib import Path


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(name, default=None):
    value = os.getenv(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


def env_int(name, default=0):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


BASE_DIR = Path(__file__).resolve().parents[2]


def load_local_env(path):
    """Load backend/.env for direct manage.py/IDE runs; real environment wins."""
    try:
        if not path.is_file() or path.stat().st_size > 64 * 1024:
            return
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


load_local_env(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-star-sakura-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", [])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_filters",
    "rest_framework",
    "rest_framework_simplejwt",
    "apps.users",
    "apps.artworks",
    "apps.orders",
    "apps.custom",
    "apps.reviews",
    "apps.inspirations",
    "apps.recommendations",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "configs.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "configs.wsgi.application"

DATABASE_ENGINE = os.getenv("DATABASE_ENGINE", "sqlite").lower()
if DATABASE_ENGINE in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "star_sakura"),
            "USER": os.getenv("POSTGRES_USER", "star_sakura"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
            "OPTIONS": {
                "connect_timeout": env_int("DB_CONNECT_TIMEOUT", 5),
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("SQLITE_NAME", BASE_DIR / "db.sqlite3"),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 30),
        }
    }

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 5 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 5 * 1024 * 1024)
MAX_IMAGE_UPLOAD_SIZE = env_int("MAX_IMAGE_UPLOAD_SIZE", 5 * 1024 * 1024)
PUBLIC_API_CACHE_TIMEOUT = env_int("PUBLIC_API_CACHE_TIMEOUT", 30)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 12,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("DRF_ANON_THROTTLE_RATE", "120/min"),
        "user": os.getenv("DRF_USER_THROTTLE_RATE", "1200/min"),
        "login": os.getenv("DRF_LOGIN_THROTTLE_RATE", "10/min"),
        "write": os.getenv("DRF_WRITE_THROTTLE_RATE", "120/min"),
        "ai_chat": os.getenv("DRF_AI_CHAT_THROTTLE_RATE", "20/min"),
        "ai_settings": os.getenv("DRF_AI_SETTINGS_THROTTLE_RATE", "30/min"),
        "ai_settings_test": os.getenv("DRF_AI_SETTINGS_TEST_THROTTLE_RATE", "5/min"),
    },
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
}

REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,
            },
            "KEY_PREFIX": os.getenv("CACHE_KEY_PREFIX", "star_sakura"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "star-sakura",
        }
    }

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = env_bool("CSRF_COOKIE_HTTPONLY", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# OpenAI-compatible AI service. Credentials are read from the environment only.
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_API_BASE = os.getenv("AI_API_BASE", "https://open.bigmodel.cn/api/paas/v4").strip()
AI_MODEL = os.getenv("AI_MODEL", "glm-4-flash").strip()
AI_API_TIMEOUT = env_int("AI_API_TIMEOUT", 60)
AI_DNS_TIMEOUT = env_int("AI_DNS_TIMEOUT", 5)
AI_DNS_MAX_CONCURRENCY = env_int("AI_DNS_MAX_CONCURRENCY", 2)
AI_CUSTOM_MAX_CONCURRENCY = env_int("AI_CUSTOM_MAX_CONCURRENCY", 4)
AI_OFFICIAL_MAX_CONCURRENCY = env_int("AI_OFFICIAL_MAX_CONCURRENCY", 4)
AI_MAX_INPUT_LENGTH = env_int("AI_MAX_INPUT_LENGTH", 2000)
AI_MAX_OUTPUT_LENGTH = env_int("AI_MAX_OUTPUT_LENGTH", 12000)
AI_CREDENTIAL_ENCRYPTION_KEY = os.getenv("AI_CREDENTIAL_ENCRYPTION_KEY", "").strip()
