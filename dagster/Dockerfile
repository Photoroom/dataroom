# The dataroom code location, run by ml-platform's Dagster chart. Context is the repo root.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
# Copied rather than pulled from the index: a SkyPilot job ships this directory
# and installs the client from it, and the published client lags this repo.
COPY dataroom_client ./client
COPY dagster/pyproject.toml ./
COPY dagster/dataroom ./dataroom

# "[dev]" from compose adds the webserver for `dagster dev`; CI builds none
ARG EXTRAS=""

# torch on PyPI is the CUDA build, ~2.5GB, and nothing here requests a GPU.
# unsafe-best-match is required: uv otherwise stops at the first index holding
# the package, which is PyPI, and the CPU index is never consulted.
RUN POETRY_DYNAMIC_VERSIONING_BYPASS=0.0.0 uv pip install --system --no-cache \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --index-strategy unsafe-best-match \
    ./client ".$EXTRAS"

# The default backbone's weights and the torch.hub checkout of the dinov2
# repo they load through, so a run pod embeds without fetching either first.
ENV TORCH_HOME=/opt/torch
RUN python -c "from dataroom.classifier.ml.embedders import DEFAULT_BACKBONE; \
from dataroom.classifier.ml.embedders.dino import DinoV2Backbones; \
DinoV2Backbones(DEFAULT_BACKBONE).backbone"

# The gRPC port the chart's deployment expects (port: 3030 in values.yaml).
EXPOSE 3030
