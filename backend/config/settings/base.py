"""
Django settings for project.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.1/ref/settings/
"""

from pathlib import Path

from ddtrace import tracer
from ddtrace.filters import FilterRequestsOnUrl
from environ import Env

env = Env()


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
BASE_DIR = BACKEND_DIR.parent

Env.read_env(BASE_DIR / ".env")


# GENERAL
# ------------------------------------------------------------------------------
DEBUG = False
TESTING = False

# https://docs.djangoproject.com/en/4.1/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

SITE_ID = 1


# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = []

# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = True
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-secure
SESSION_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-age
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 4  # 4 weeks
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-secure
CSRF_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-failure-view
# CSRF_FAILURE_VIEW = 'your_app_name.views.csrf_failure'  # TODO: add custom csrf error page

# https://docs.djangoproject.com/en/dev/ref/settings/#data-upload-max-memory-size
DATA_UPLOAD_MAX_MEMORY_SIZE = 2621440 * 20  # 50 MB
# https://docs.djangoproject.com/en/dev/ref/settings/#data-upload-max-number-fields
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000 * 5

DATA_UPLOAD_MAX_NUMBER_FILES = 200


# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL", "postgresql://postgres:postgres@dataroom_postgres:5432/dataroom")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=10)
DATABASES["default"]["OPTIONS"] = {
    'options': '-c statement_timeout=180000',  # timeout queries that take longer than 3 minutes
}

# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "backend.config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "backend.config.wsgi.application"


# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "admin_shortcuts",  # must come before admin
    "django.contrib.admin",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "django_extensions",
    "django_jinja",
    "django_vite",
    "model_utils",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    'allauth.socialaccount.providers.google',
    "rest_framework",
    "django_filters",
    "drf_spectacular",
]
LOCAL_APPS = [
    "backend.users",
    "backend.dataroom",
    "backend.api",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "index"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "account_login"

# django-allauth
# ------------------------------------------------------------------------------
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_ALLOW_REGISTRATION = False
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_SIGNUP_EMAIL_ENTER_TWICE = False
ACCOUNT_MAX_EMAIL_ADDRESSES = 2
ACCOUNT_TEMPLATE_EXTENSION = "jinja"
ACCOUNT_EMAIL_SUBJECT_PREFIX = ''


# SESSIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-SESSION_ENGINE
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"


# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    'backend.config.middleware.HealthCheckMiddleware',
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    # project
    "backend.users.middleware.user_middleware.UpdateDateAccessedMiddleware",
    "backend.users.middleware.datadog.DatadogUserEmailMiddleware",
]


# STATIC
# ------------------------------------------------------------------------------

# Django Vite
# https://github.com/MrBin99/django-vite
DJANGO_VITE_ASSETS_PATH = BACKEND_DIR / "static_built"
DJANGO_VITE_DEV_MODE = DEBUG
DJANGO_VITE_DEV_SERVER_PORT = 3000

# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = BACKEND_DIR / "static_collected"
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [DJANGO_VITE_ASSETS_PATH]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

STORAGES = {
    "default": {
        "BACKEND": "backend.config.storage.OverwriteStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


# Deepscatter static files (for development only)
DEEPSCATTER_STATIC_ROOT = BACKEND_DIR / "static_deepscatter"
DEEPSCATTER_STATIC_URL = "/deepscatter/"
DEEPSCATTER_URL = "/deepscatter/tiles"


# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = BACKEND_DIR / "media"
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"


# TEMPLATES
# ------------------------------------------------------------------------------

# https://docs.djangoproject.com/en/dev/ref/templates/api/#using-requestcontext
CONTEXT_PROCESSORS = [
    "django.template.context_processors.debug",
    "django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth",
    "django.template.context_processors.i18n",
    "django.template.context_processors.media",
    "django.template.context_processors.static",
    "django.template.context_processors.tz",
    "django.contrib.messages.context_processors.messages",
    "backend.users.context_processors.theme",
]


# https://docs.djangoproject.com/en/dev/ref/settings/#templates

TEMPLATES = [
    {
        # https://niwi.nz/django-jinja/latest/
        "BACKEND": "django_jinja.backend.Jinja2",
        "DIRS": [BACKEND_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "match_extension": ".jinja",
            "match_regex": None,
            "app_dirname": "templates",
            "undefined": "jinja2.Undefined",
            "trim_blocks": True,
            "lstrip_blocks": True,
            "context_processors": CONTEXT_PROCESSORS,
            "globals": {
                # django-vite
                "vite_asset": "django_vite.templatetags.django_vite.vite_asset",
                "vite_asset_url": "django_vite.templatetags.django_vite.vite_asset_url",
                "vite_hmr_client": "django_vite.templatetags.django_vite.vite_hmr_client",
                "vite_react_refresh": "django_vite.templatetags.django_vite.vite_react_refresh",
                # heroicons
                "heroicon_outline": "heroicons.jinja.heroicon_outline",
                "heroicon_solid": "heroicons.jinja.heroicon_solid",
                # allauth
                "user_display": "allauth.account.utils.user_display",
                # project
                "set_key": "backend.common.jinja_utils.set_key",
            },
        },
    },
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#template-dirs
        "DIRS": [BACKEND_DIR / "templates"],
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-loaders
            # https://docs.djangoproject.com/en/dev/ref/templates/api/#loader-types
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            "builtins": [
                "django.templatetags.static",
            ],
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": CONTEXT_PROCESSORS,
        },
    },
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"


# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin-backend/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = []
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS


# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "django.utils.autoreload": {  # if you take this out, runserver logs twice, annoying
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "task_runner": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "opensearch": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}


# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = "hello@localhost"
# https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX = "[Staff] "


# django-admin-shortcuts
# ------------------------------------------------------------------------------

ADMIN_SHORTCUTS = [
    {
        'shortcuts': [
            {
                'title': 'Users',
                'url_name': 'admin:users_user_changelist',
            },
            {
                'title': 'Tasks',
                'url_name': 'admin:admin_tasks',
            },
            {
                'title': 'OpenSearch',
                'url_name': 'admin:admin_opensearch',
            },
        ],
    },
]


# Rest Framework
# ------------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'backend.api.authentication.APITokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'backend.api.permissions.DataroomAccessPermission',
    ],
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'backend.api.pagination.CustomCursorPagination',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'DataRoom API',
    'DESCRIPTION': 'Store training images at scale.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}


# Datadog
# ------------------------------------------------------------------------------
tracer.configure(
    settings={
        'FILTERS': [
            FilterRequestsOnUrl(r'http://.*/_health/$'),
        ],
    }
)


# DataRoom
# ------------------------------------------------------------------------------

# data
IMAGE_ID_MIN_LENGTH = 1
IMAGE_ID_MAX_LENGTH = 512
FILENAME_MAX_LENGTH = 768

LATENT_TYPE_MIN_LENGTH = 1
LATENT_TYPE_MAX_LENGTH = 128
RELATED_IMAGE_TYPE_MAX_LENGTH = 128

MAX_LATENT_TYPES = 250
MAX_ATTRIBUTES_FIELDS = 100

# duplication params
DUPLICATE_FINDER_NUMBER_OF_SIMILARS = 30
DUPLICATE_FINDER_SIMILARITY_THRESHOLD = 0.98
DUPLICATE_FINDER_EXCLUDED_SOURCES = []
DUPLICATE_DELETE_TASK_INCLUDED_SOURCES = []

# page size used in django views
DEFAULT_PAGINATE_BY = 100

# cache timeout
API_CACHE_DEFAULT_TTL = 60 * 5  # 5 minutes
API_CACHE_MAX_TTL = 60 * 60  # 1 hour

# API

# Use this to turn off all writes in the API during maintenance
API_DISABLE_IMAGE_WRITES = env.bool('API_DISABLE_IMAGE_WRITES', default=False)

# thumbnail image size
THUMBNAIL_SIZE = (400, 400)

# Number of workers for MDSWriter in dataset_save_shards
MDS_WRITER_MAX_WORKERS = env.int('MDS_WRITER_MAX_WORKERS', default=6)

# Task runner API
TASK_RUNNER_STATS_API = env.str('TASK_RUNNER_STATS_API', default=None)

# OpenSearch
AWS_OPEN_SEARCH_UNAUTHENTICATED_REQUESTS = True
AWS_OPEN_SEARCH_URL = env('AWS_OPEN_SEARCH_URL', default='http://localhost:9200')

OPENSEARCH_IMAGES_INDEX_NAME = env('OPENSEARCH_IMAGES_INDEX_NAME', default='images')
OPENSEARCH_DEFAULT_REFRESH = True

OPENSEARCH_SNAPSHOT_REPOSITORY_NAME = env('OPENSEARCH_SNAPSHOT_REPOSITORY_NAME', default=None)
OPENSEARCH_SNAPSHOT_NAME = env('OPENSEARCH_SNAPSHOT_NAME', default=None)
OPENSEARCH_SNAPSHOT_BUCKET = env('OPENSEARCH_SNAPSHOT_BUCKET', default=None)
OPENSEARCH_SNAPSHOT_ROLE_ARN = env('OPENSEARCH_SNAPSHOT_ROLE_ARN', default=None)

# Embedding API

FETCH_EMBEDDING_FOR_IMAGE_API_URL = env('FETCH_EMBEDDING_FOR_IMAGE_API_URL', default=None)
FETCH_EMBEDDING_FOR_IMAGE_HEADER_KEY = env('FETCH_EMBEDDING_FOR_IMAGE_HEADER_KEY', default=None)
FETCH_EMBEDDING_FOR_IMAGE_HEADER_VALUE = env('FETCH_EMBEDDING_FOR_IMAGE_HEADER_VALUE', default=None)

FETCH_EMBEDDING_FOR_TEXT_API_URL = env('FETCH_EMBEDDING_FOR_TEXT_API_URL', default=None)
FETCH_EMBEDDING_FOR_TEXT_HEADER_KEY = env('FETCH_EMBEDDING_FOR_TEXT_HEADER_KEY', default=None)
FETCH_EMBEDDING_FOR_TEXT_HEADER_VALUE = env('FETCH_EMBEDDING_FOR_TEXT_HEADER_VALUE', default=None)

FETCH_TEXT_FOR_IMAGE_API_URL = env('FETCH_TEXT_FOR_IMAGE_API_URL', default=None)
FETCH_TEXT_FOR_IMAGE_HEADER_KEY = env('FETCH_TEXT_FOR_IMAGE_HEADER_KEY', default=None)
FETCH_TEXT_FOR_IMAGE_HEADER_VALUE = env('FETCH_TEXT_FOR_IMAGE_HEADER_VALUE', default=None)
