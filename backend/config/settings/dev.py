from .deployed import *  # noqa: F403

# Settings for the development deployment (dataroom-dev ECS).
# Everything shared with the other deployed environments lives in deployed.py.

# STORAGES
# ------------------------------------------------------------------------------
# Dev serves images straight from S3 rather than R2.
STORAGES["default"] = s3_storage(use_r2_default=False)


# DataRoom
# ------------------------------------------------------------------------------
OPENSEARCH_KNN_ENGINE = 's3vector'


# LOGGING
# ------------------------------------------------------------------------------
# More verbose than the other environments.
LOGGING = console_logging(level="DEBUG", opensearch_level="INFO")
