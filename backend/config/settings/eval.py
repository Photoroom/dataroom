from .deployed import *  # noqa: F403

# Settings for the eval environment.
# Everything shared with the other deployed environments lives in deployed.py.

# STORAGES
# ------------------------------------------------------------------------------
STORAGES["default"] = s3_storage(use_r2_default=True)
