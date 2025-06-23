from .base import *  # noqa: F403

# Settings for local development

# GENERAL
# ------------------------------------------------------------------------------
DEBUG = True
ENABLE_DEBUG_TOOLBAR = False


# FRONTEND
# ------------------------------------------------------------------------------
DJANGO_VITE_DEV_MODE = DEBUG


# SECURITY
# ------------------------------------------------------------------------------
INTERNAL_IPS = ["127.0.0.1"]
SECRET_KEY = "django-insecure-scw8vaop+fgn=l6*)q2j92hc77*c@0j76xn0a$wu4%70&!wb8^"
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
