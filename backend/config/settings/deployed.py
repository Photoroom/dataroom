"""Settings shared by every deployed environment (dev, eval, production).

Deliberately not merged into base.py. base.py has to stay importable with a
completely empty environment, because local.py and test.py rely on that - the
test suite runs without a single environment variable set. Everything below
either *requires* an environment variable or hardens a default, which is exactly
what should not apply when running tests or working locally.

The pieces that genuinely differ between environments are exposed as the
`s3_storage()` and `console_logging()` helpers rather than as settings, so each
environment module stays a handful of lines. Django only treats UPPERCASE names
as settings, so lowercase helpers here are invisible to it.
"""

from .base import *  # noqa: F403

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")


# SECURITY
# ------------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")

# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-seconds
# https://docs.djangoproject.com/en/dev/ref/middleware/#http-strict-transport-security
# Refuse to connect to your domain name via an insecure connection for a given period of time
SECURE_HSTS_SECONDS = env.bool("DJANGO_SECURE_HSTS_SECONDS", default=518400)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-include-subdomains
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-preload
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
# https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
SECURE_CONTENT_TYPE_NOSNIFF = env.bool("DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", default=True)


# STORAGES
# ------------------------------------------------------------------------------
# https://django-storages.readthedocs.io/en/latest/#installation
INSTALLED_APPS += ["storages"]


def cloudfront_key():
    """The CloudFront signing key, repaired if AWS Secrets Manager mangled it.

    Secrets Manager does not allow newlines in a secret value, so the key comes
    back with spaces where the newlines should be.
    """
    key = env("AWS_CLOUDFRONT_KEY")

    if '-----BEGIN PRIVATE KEY----- ' in key:
        raw = key.split('-----BEGIN PRIVATE KEY----- ')[1].split(' -----END PRIVATE KEY-----')[0]
        key = '-----BEGIN PRIVATE KEY-----\n' + raw.replace(' ', '\n') + '\n-----END PRIVATE KEY-----'

    return key


def s3_storage(*, use_r2_default, aws_keys_required=False):
    """Build STORAGES["default"] for a deployed environment.

    Cloudflare R2 and AWS S3 are both S3-compatible, so the same backend serves
    both; USE_CLOUDFLARE_R2 picks between them. Its default differs per
    environment, hence `use_r2_default`.

    `aws_keys_required` controls whether the AWS credentials must be present when
    S3 is used. Production requires them; the other environments fall back to
    empty strings so boto can pick up an instance role instead.
    """
    shared_options = {
        "querystring_auth": True,
        "querystring_expire": 60 * 60 * 24,
        "file_overwrite": True,
        "signature_version": "s3v4",
    }

    if env.bool("USE_CLOUDFLARE_R2", default=use_r2_default):
        return {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "endpoint_url": env('CLOUDFLARE_R2_ENDPOINT_URL'),
                "access_key": env('CLOUDFLARE_S3_ACCESS_KEY_ID'),
                "secret_key": env('CLOUDFLARE_S3_SECRET_ACCESS_KEY'),
                "bucket_name": env("CLOUDFLARE_R2_BUCKET_NAME"),
                "region_name": env("CLOUDFLARE_R2_REGION_NAME"),
                **shared_options,
            },
        }

    key_kwargs = {} if aws_keys_required else {"default": ""}
    options = {
        "access_key": env('AWS_S3_ACCESS_KEY_ID', **key_kwargs),
        "secret_key": env('AWS_S3_SECRET_ACCESS_KEY', **key_kwargs),
        "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
        "region_name": env("AWS_S3_REGION_NAME"),
        **shared_options,
    }

    if env.bool("USE_CLOUDFRONT", default=False):
        options["custom_domain"] = env("AWS_CLOUDFRONT_DOMAIN")
        options["cloudfront_key_id"] = env("AWS_CLOUDFRONT_KEY_ID")
        options["cloudfront_key"] = cloudfront_key()

    return {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage", "OPTIONS": options}


# DATABASES
# ------------------------------------------------------------------------------
DATABASES["default"] = env.db("DATABASE_URL")


# Google
# ------------------------------------------------------------------------------

GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET")


# Allauth Social Accounts
# ------------------------------------------------------------------------------

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        "APP": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "secret": GOOGLE_OAUTH_CLIENT_SECRET,
        },
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'OAUTH_PKCE_ENABLED': True,
    },
}


# DataRoom
# ------------------------------------------------------------------------------

OPENSEARCH_IMAGES_INDEX_NAME = env('OPENSEARCH_IMAGES_INDEX_NAME')

# OpenSearch
AWS_OPEN_SEARCH_UNAUTHENTICATED_REQUESTS = False
AWS_OPEN_SEARCH_URL = env('AWS_OPEN_SEARCH_URL')
AWS_OPEN_SEARCH_REGION_NAME = env('AWS_OPEN_SEARCH_REGION_NAME')

# task params
DUPLICATE_DELETE_TASK_INCLUDED_SOURCES = env.list('DUPLICATE_DELETE_TASK_INCLUDED_SOURCES', default='')


# LOGGING
# ------------------------------------------------------------------------------


def console_logging(*, level="INFO", opensearch_level="WARNING"):
    """Log everything to the console, which is what ECS collects.

    `level` applies to the handler and to our own loggers; `opensearch_level` is
    separate because the client is chatty at INFO.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "level": level,
                "class": "logging.StreamHandler",
            },
        },
        "root": {"level": "INFO", "handlers": ["console"]},
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "django.utils.autoreload": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "task_runner": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "dataroom": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "opensearch": {
                "handlers": ["console"],
                "level": opensearch_level,
                "propagate": False,
            },
        },
    }
