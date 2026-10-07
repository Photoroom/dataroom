import os

MODELS_BUCKET = os.environ.get("CLASSIFIER_MODELS_BUCKET", "")
# Key prefix, for sharing one bucket between services; the store keeps
# <prefix>/<env>/classifiers/models/<model id>/ under it.
_prefix = os.environ.get("CLASSIFIER_MODELS_PREFIX", "").strip("/")
MODELS_PREFIX = f"{_prefix}/" if _prefix else ""

S3_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "")

# The image installs CPU-only torch wheels, so this stays "cpu".
DEVICE = os.environ.get("CLASSIFIER_DEVICE", "cpu")

# The assets.ComputeBackend that runs training and embedding: "local", a
# private backend's short name, or a module path.
COMPUTE = os.environ.get("CLASSIFIER_COMPUTE", "local")
