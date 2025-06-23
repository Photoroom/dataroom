from .base import *  # noqa: F403

# Settings for production
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


if env.bool("USE_CLOUDFLARE_R2", default=True):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "endpoint_url": env('CLOUDFLARE_R2_ENDPOINT_URL'),
            "access_key": env('CLOUDFLARE_S3_ACCESS_KEY_ID'),
            "secret_key": env('CLOUDFLARE_S3_SECRET_ACCESS_KEY'),
            "bucket_name": env("CLOUDFLARE_R2_BUCKET_NAME"),
            "region_name": env("CLOUDFLARE_R2_REGION_NAME"),
            "querystring_auth": True,
            "querystring_expire": 60 * 60 * 24,
            "file_overwrite": True,
            "signature_version": "s3v4",
        },
    }
else:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "access_key": env('AWS_S3_ACCESS_KEY_ID'),
            "secret_key": env('AWS_S3_SECRET_ACCESS_KEY'),
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
            "region_name": env("AWS_S3_REGION_NAME"),
            "querystring_auth": True,
            "querystring_expire": 60 * 60 * 24,
            "file_overwrite": True,
            "signature_version": "s3v4",
        },
    }

    # CloudFront
    if env.bool("USE_CLOUDFRONT", default=False):
        STORAGES["default"]["OPTIONS"]["custom_domain"] = env("AWS_CLOUDFRONT_DOMAIN")
        STORAGES["default"]["OPTIONS"]["cloudfront_key_id"] = env("AWS_CLOUDFRONT_KEY_ID")
        AWS_CLOUDFRONT_KEY = env("AWS_CLOUDFRONT_KEY")

        if '-----BEGIN PRIVATE KEY----- ' in AWS_CLOUDFRONT_KEY:
            # the private key is using spaces instead of newlines, fix it
            # this happens because the AWS Secrets Manager doesn't allow newlines in the secret value
            cf_raw_key = AWS_CLOUDFRONT_KEY.split('-----BEGIN PRIVATE KEY----- ')[1].split(
                ' -----END PRIVATE KEY-----'
            )[0]
            AWS_CLOUDFRONT_KEY = (
                '-----BEGIN PRIVATE KEY-----\n' + cf_raw_key.replace(' ', '\n') + '\n-----END PRIVATE KEY-----'
            )

        STORAGES["default"]["OPTIONS"]["cloudfront_key"] = AWS_CLOUDFRONT_KEY


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
AWS_OPEN_SEARCH_ACCESS_KEY_ID = env('AWS_OPEN_SEARCH_ACCESS_KEY_ID')
AWS_OPEN_SEARCH_SECRET_ACCESS_KEY = env('AWS_OPEN_SEARCH_SECRET_ACCESS_KEY')
AWS_OPEN_SEARCH_REGION_NAME = env('AWS_OPEN_SEARCH_REGION_NAME')

# task params
DUPLICATE_DELETE_TASK_INCLUDED_SOURCES = env.list('DUPLICATE_DELETE_TASK_INCLUDED_SOURCES', default='')
