from .base import *  # noqa: F403

# Settings for local development

# GENERAL
# ------------------------------------------------------------------------------
DEBUG = True
ENABLE_DEBUG_TOOLBAR = False
# no need since VITE server staticfiles
SILENCED_SYSTEM_CHECKS = ["staticfiles.W004"]


# FRONTEND
# ------------------------------------------------------------------------------
DJANGO_VITE_DEV_MODE = True 
DJANGO_VITE_DEV_SERVER_PORT = 5173  # Browser connects to localhost:5173 (mapped from dataroom_vite container)


# SECURITY
# ------------------------------------------------------------------------------
INTERNAL_IPS = ["127.0.0.1"]
SECRET_KEY = "django-insecure-scw8vaop+fgn=l6*)q2j92hc77*c@0j76xn0awu4%70&!wb8^"
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ["*"]
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = False
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-secure
SESSION_COOKIE_SECURE = False
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-secure
CSRF_COOKIE_SECURE = False


# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# APPS
# ------------------------------------------------------------------------------
if DEBUG and ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS += [
        "debug_toolbar",
    ]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware", *MIDDLEWARE]


# DataRoom
# ------------------------------------------------------------------------------

TASK_RUNNER_STATS_API = "http://localhost:5000"

# OpenSearch
AWS_OPEN_SEARCH_UNAUTHENTICATED_REQUESTS = True


# STORAGES (MinIO for local S3-compatible storage)
# ------------------------------------------------------------------------------
INSTALLED_APPS += ["storages"]

STORAGES["default"] = {
    "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    "OPTIONS": {
        "endpoint_url": env("MINIO_ENDPOINT_URL", default="http://minio:9000"),
        "access_key": env("MINIO_ACCESS_KEY", default="minioadmin"),
        "secret_key": env("MINIO_SECRET_KEY", default="minioadmin"),
        "bucket_name": env("MINIO_BUCKET_NAME", default="dataroom-local"),
        "region_name": "us-east-1",
        "querystring_auth": False,  # Disable signed URLs for local dev
        "file_overwrite": True,
        "signature_version": "s3v4",
        # Required for MinIO
        "addressing_style": "path",
        # Use localhost for browser-accessible URLs
        "custom_domain": env("MINIO_PUBLIC_URL", default="localhost:9000/dataroom-local"),
        "url_protocol": "http:",  # Use http for local dev
    },
}

# Fallback domain for "direct" URLs (image_direct_url) in local dev
# Without this, direct URLs would use internal Docker network (minio:9000)
STORAGE_DIRECT_URL_DOMAIN = env("MINIO_PUBLIC_URL", default="localhost:9000/dataroom-local")
