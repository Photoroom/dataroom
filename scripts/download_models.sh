#!/usr/bin/env bash
set -euo pipefail

# Download pre-built ML model artifacts from S3.
#
# Usage:
#   ./scripts/download_models.sh              # download models
#   ./scripts/download_models.sh --check      # exit 0 if models exist, 1 otherwise
#
# Requires: AWS CLI with valid credentials (aws configure).

S3_BUCKET="s3://dataroom-models"
MODELS_DIR="$(cd "$(dirname "$0")/.." && pwd)/models"

COCA_DIR="$MODELS_DIR/coca_text_encoder"
COCA_FILES=(
  "text_encoder_q8.onnx"
  "bpe_simple_vocab_16e6.txt.gz"
  "config.json"
)

check_models() {
  for f in "${COCA_FILES[@]}"; do
    if [ ! -f "$COCA_DIR/$f" ]; then
      return 1
    fi
  done
  return 0
}

if [ "${1:-}" = "--check" ]; then
  if check_models; then
    echo "All model files present in $COCA_DIR"
    exit 0
  else
    echo "Missing model files in $COCA_DIR"
    exit 1
  fi
fi

if check_models; then
  echo "Models already present in $COCA_DIR, skipping download."
  echo "To force re-download, remove the directory: rm -rf $COCA_DIR"
  exit 0
fi

echo "Downloading CoCa text encoder model from $S3_BUCKET ..."
mkdir -p "$COCA_DIR"

for f in "${COCA_FILES[@]}"; do
  echo "  $f"
  aws s3 cp "$S3_BUCKET/coca_text_encoder/$f" "$COCA_DIR/$f"
done

echo "Done. Models saved to $COCA_DIR"
