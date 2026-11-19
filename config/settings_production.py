"""SmartMart ERP production-only Django settings.

This module intentionally does not affect the existing local settings.py.
Use on a deployed HTTPS host with a managed PostgreSQL database and persistent media.

    DJANGO_SETTINGS_MODULE=config.settings_production

Never commit live SMARTMART_SECRET_KEY, DATABASE_URL, or database backups.
"""
from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F401,F403  Preserve existing SmartMart apps and middleware.


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"Production requires environment variable {name}.")
    return value


def _csv(name):
    return [part.strip() for part in _required(name).split(",") if part.strip()]


DEBUG = False
SECRET_KEY = _required("SMARTMART_SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("SMARTMART_SECRET_KEY must be a unique, strong, randomly generated production-only secret.")
SECRET_KEY_FALLBACKS = []  # Never use a developer key as a fallback in production.

ALLOWED_HOSTS = _csv("SMARTMART_ALLOWED_HOSTS")
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set explicit production hosts. Wildcard ALLOWED_HOSTS is not accepted.")
CSRF_TRUSTED_ORIGINS = _csv("SMARTMART_CSRF_TRUSTED_ORIGINS")
if any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("SMARTMART_CSRF_TRUSTED_ORIGINS must contain HTTPS origins only.")

# On production configure a managed, backed-up PostgreSQL database; do not
# silently point a public supermarket at its developer SQLite database.
import dj_database_url
DATABASE_URL = _required("DATABASE_URL")
if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
    raise ImproperlyConfigured("Production DATABASE_URL must specify PostgreSQL, not SQLite.")
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=60,
        conn_health_checks=True,
        ssl_require=True,
    )
}

# Only enable proxy header trust if the platform is a trusted reverse proxy
# that DROPS any user-supplied X-Forwarded-Proto header and sets its own.
if os.environ.get("SMARTMART_TRUST_PROXY_HTTPS", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Start with 0 until HTTPS, domain, and all subdomains are verified.
# Increase later following the HSTS rollout plan in the README.
SECURE_HSTS_SECONDS = int(os.environ.get("SMARTMART_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Static assets: WhiteNoise serves collected immutable site assets. User media
# needs persistent private storage and is NOT served by WhiteNoise.
STATIC_ROOT = BASE_DIR / "staticfiles"
MIDDLEWARE = list(MIDDLEWARE)
security_middleware = "django.middleware.security.SecurityMiddleware"
white_noise = "whitenoise.middleware.WhiteNoiseMiddleware"
if white_noise not in MIDDLEWARE:
    if security_middleware not in MIDDLEWARE:
        raise ImproperlyConfigured("SecurityMiddleware is required in production.")
    MIDDLEWARE.insert(MIDDLEWARE.index(security_middleware) + 1, white_noise)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Require persistent media storage. Never depend on an ephemeral host filesystem.
_media_path = Path(_required("SMARTMART_MEDIA_ROOT")).expanduser()
if not _media_path.is_absolute():
    raise ImproperlyConfigured("SMARTMART_MEDIA_ROOT must be an absolute persistent storage path.")
MEDIA_ROOT = _media_path
