# CoCa Text Encoder (ONNX)

Local text-to-embedding model for text-to-image similarity search, replacing the
external `FETCH_EMBEDDING_FOR_TEXT` API with on-device inference.

Model: `coca_ViT-L-14 / mscoco_finetuned_laion2B-s13B-b90k` (text encoder only)

## Quick start (local development)

Download the pre-built model files from S3:

```bash
./scripts/download_models.sh
```

Requires AWS CLI with valid credentials (`aws configure`). The script is
idempotent — it skips the download if model files are already present.

## Generate model files from scratch

Only needed when updating the model. This downloads the pretrained weights from
HuggingFace (~2.5 GB) and re-exports to ONNX:

```bash
uv run scripts/export_coca_text_encoder_onnx.py --quantize
```

After exporting, upload to S3 so CI and other developers can use the pre-built files:

```bash
aws s3 cp models/coca_text_encoder/text_encoder_q8.onnx s3://dataroom-models/coca_text_encoder/
aws s3 cp models/coca_text_encoder/bpe_simple_vocab_16e6.txt.gz s3://dataroom-models/coca_text_encoder/
aws s3 cp models/coca_text_encoder/config.json s3://dataroom-models/coca_text_encoder/
```

## Output files

```
models/coca_text_encoder/
  text_encoder.onnx              # fp32 model (473 MB) — reference only
  text_encoder_q8.onnx           # int8 quantized (120 MB) — use this
  bpe_simple_vocab_16e6.txt.gz   # BPE tokenizer vocabulary (1.3 MB)
  config.json                    # model metadata
```

The `models/` directory is gitignored. These files are baked into the Docker
image at build time via `COPY . .` in the Dockerfile. The CI workflow
downloads them from S3 before building.

## Enable in production

Set the environment variable (already configured in Terraform):

```
COCA_TEXT_ENCODER_MODEL_PATH=/app/models/coca_text_encoder/text_encoder_q8.onnx
```

If not set, the app falls back to the external text embedding API
(`FETCH_EMBEDDING_FOR_TEXT_API_URL`).

## Performance

Benchmarked on Apple M-series CPU (single core):

| Model | Size  | Latency (p50) | Cosine vs PyTorch |
|-------|-------|---------------|-------------------|
| fp32  | 473 MB | 14 ms        | 1.000             |
| int8  | 120 MB | 10 ms        | 0.998             |

## Re-benchmarking

```bash
uv run scripts/export_coca_text_encoder_onnx.py --benchmark-only
```
