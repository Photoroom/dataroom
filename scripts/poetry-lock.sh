#!/bin/bash
set -e

# Update poetry lock inside the docker container and copy to local machine
# This ensures the lock file is generated in the same Linux environment as production

echo "Running poetry lock inside docker container and copying to local..."
docker compose run --rm -v "$(pwd)/poetry.lock:/app/poetry.lock" dataroom_django poetry lock
echo "✓ poetry.lock updated successfully!"