from .deployed import *  # noqa: F403

# Settings for the production ECS deployment.
# Everything shared with the other deployed environments lives in deployed.py.

# STORAGES
# ------------------------------------------------------------------------------
# Unlike the other environments, the AWS credentials are required rather than
# optional when S3 is in use.
STORAGES["default"] = s3_storage(use_r2_default=True, aws_keys_required=True)


# DataRoom
# ------------------------------------------------------------------------------
OPENSEARCH_KNN_ENGINE = 's3vector'
# group_ids/memberships were dynamically mapped as text + .keyword on this index, so
# exact-match filters must target the keyword sub-field.
# TODO: fix after reindexing on prod — drop once these are plain keyword again.
OPENSEARCH_GROUP_FIELD_SUFFIX = '.keyword'


# LOGGING
# ------------------------------------------------------------------------------
LOGGING = console_logging()
