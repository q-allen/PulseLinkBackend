# ⚠️  WARNING: If you have already run migrate with Django's default auth.User,
#     you must clear all migrations and drop/recreate the database
#     before applying this custom user model.

import os
from datetime import timedelta

# ── INSTALLED_APPS ──────────────────────────────────────────────────────────
# Add 'users' to your existing INSTALLED_APPS list:
#
# INSTALLED_APPS = [
#     ...
#     'users',   # ← add this
# ]

# ── AUTH USER MODEL ──────────────────────────────────────────────────────────
AUTH_USER_MODEL = "users.User"

# ── DATABASE (PostgreSQL) ────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME"),
        "USER": os.environ.get("DB_USER"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# ── REDIS CACHE ──────────────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# ── SIMPLE JWT ───────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ── REST FRAMEWORK ───────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}
