#!/bin/bash
set -e

# Update uv.lock after changing dependencies in pyproject.toml.
# uv.lock is platform-independent (it resolves for all platforms), so unlike
# the old poetry flow this can run directly on the host — no container needed.

echo "Updating uv.lock..."
uv lock
echo "✓ uv.lock updated successfully!"
