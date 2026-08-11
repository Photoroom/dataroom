#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "open_clip_torch>=2.24",
#     "torch>=2.0",
#     "onnx>=1.14",
#     "onnxscript",
#     "onnxruntime>=1.16",
#     "numpy",
# ]
# ///
"""
Export the text encoder from CoCa ViT-L-14 (mscoco_finetuned) to ONNX and benchmark.

Creates an ONNX model that maps tokenized text [batch, 76] to L2-normalized
768-dim embeddings for text-to-image similarity search.

Usage:
    uv run scripts/export_coca_text_encoder_onnx.py
    uv run scripts/export_coca_text_encoder_onnx.py --quantize
    uv run scripts/export_coca_text_encoder_onnx.py --benchmark-only

Output:
    models/coca_text_encoder/text_encoder.onnx   ONNX model (fp32)
    models/coca_text_encoder/text_encoder_q8.onnx ONNX model (int8, with --quantize)
    models/coca_text_encoder/config.json          Model metadata
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

MODEL_NAME = "coca_ViT-L-14"
PRETRAINED = "mscoco_finetuned_laion2B-s13B-b90k"


class TextEncoderForExport(nn.Module):
    """Wraps CoCa's text tower for clean ONNX export.

    Replicates CoCa.encode_text(text, normalize=True):
    1. Run through TextTransformer (appends CLS token, causal+padding attention, pools from CLS)
    2. L2-normalize the output embedding

    Input:  int64 [batch_size, 76]   — tokenized text from open_clip tokenizer
    Output: float32 [batch_size, 768] — L2-normalized text embedding
    """

    def __init__(self, text_tower: nn.Module):
        super().__init__()
        self.text_tower = text_tower

    def forward(self, text: torch.Tensor) -> torch.Tensor:
        text_latent, _ = self.text_tower(text)
        return F.normalize(text_latent, dim=-1)


def export(output_dir: Path, quantize: bool = False, opset: int = 17):
    import onnx
    import onnxruntime as ort
    import open_clip

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Load model ---
    print(f"Loading {MODEL_NAME} / {PRETRAINED} ...")
    model, _, _ = open_clip.create_model_and_transforms(
        MODEL_NAME, pretrained=PRETRAINED
    )
    model.eval()

    tokenizer = open_clip.get_tokenizer(MODEL_NAME)

    # --- Build wrapper and verify it matches model.encode_text ---
    wrapper = TextEncoderForExport(model.text)
    wrapper.eval()

    sample = tokenizer(["a photo of a cat", "shoes on a table"])
    context_length = sample.shape[1]

    with torch.no_grad():
        ref = model.encode_text(sample, normalize=True)
        wrapped = wrapper(sample)
        cos = F.cosine_similarity(ref, wrapped, dim=-1)
        print(f"Wrapper vs encode_text cosine sim: {cos.tolist()}")
        if cos.min() < 0.9999:
            raise RuntimeError(
                f"Wrapper output diverges from encode_text (min cos={cos.min():.6f}). "
                "The CoCa internals may have changed — check open_clip version."
            )

    embed_dim = int(ref.shape[1])
    print(f"Context length: {context_length}  Embedding dim: {embed_dim}")

    # --- Export to ONNX ---
    onnx_path = output_dir / "text_encoder.onnx"
    print(f"\nExporting to {onnx_path} ...")

    with torch.no_grad():
        torch.onnx.export(
            wrapper,
            sample,
            str(onnx_path),
            input_names=["input_ids"],
            output_names=["text_embedding"],
            dynamic_axes={
                "input_ids": {0: "batch_size"},
                "text_embedding": {0: "batch_size"},
            },
            opset_version=opset,
            do_constant_folding=True,
        )

    # --- Consolidate into single file (dynamo exporter splits weights out) ---
    onnx_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(onnx_model)
    external_data_path = Path(str(onnx_path) + ".data")
    if external_data_path.exists():
        print("Consolidating external data into single ONNX file ...")
        for init in onnx_model.graph.initializer:
            init.ClearField("data_location")
        onnx.save_model(onnx_model, str(onnx_path), save_as_external_data=False)
        external_data_path.unlink()
        # Re-load to verify
        onnx_model = onnx.load(str(onnx_path))
        onnx.checker.check_model(onnx_model)
    print("ONNX model validation passed")

    # --- Compare PyTorch vs ONNX outputs ---
    session = ort.InferenceSession(
        str(onnx_path), providers=["CPUExecutionProvider"]
    )

    test_texts = [
        "shoes",
        "a red car on a highway",
        "person wearing sunglasses",
        "giraffe in the wild",
    ]
    test_tokens = tokenizer(test_texts)

    with torch.no_grad():
        pt_embs = model.encode_text(test_tokens, normalize=True).numpy()

    ort_embs = session.run(None, {"input_ids": test_tokens.numpy()})[0]

    print("\nPyTorch vs ONNX validation:")
    for i, t in enumerate(test_texts):
        cos = float(np.dot(pt_embs[i], ort_embs[i]))
        maxd = float(np.abs(pt_embs[i] - ort_embs[i]).max())
        print(f"  '{t}': cosine={cos:.6f}  max_diff={maxd:.2e}")

    # --- Optional INT8 quantization ---
    if quantize:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        q_path = output_dir / "text_encoder_q8.onnx"
        quantize_dynamic(str(onnx_path), str(q_path), weight_type=QuantType.QInt8)
        q_size = q_path.stat().st_size / (1024 * 1024)
        print(f"\nQuantized model: {q_path} ({q_size:.1f} MB)")

        # Validate quantized model
        q_session = ort.InferenceSession(
            str(q_path), providers=["CPUExecutionProvider"]
        )
        q_embs = q_session.run(None, {"input_ids": test_tokens.numpy()})[0]
        print("Quantized model validation:")
        for i, t in enumerate(test_texts):
            cos = float(np.dot(pt_embs[i], q_embs[i]))
            print(f"  '{t}': cosine={cos:.6f} (vs PyTorch)")

    # --- Copy BPE tokenizer vocab ---
    import shutil

    from open_clip.tokenizer import default_bpe

    bpe_src = default_bpe()
    bpe_dst = output_dir / "bpe_simple_vocab_16e6.txt.gz"
    shutil.copy2(bpe_src, bpe_dst)
    print(f"\nTokenizer vocab: {bpe_dst} ({bpe_dst.stat().st_size / 1024:.0f} KB)")

    # --- Save config ---
    config = {
        "model_name": MODEL_NAME,
        "pretrained": PRETRAINED,
        "context_length": context_length,
        "embed_dim": embed_dim,
        "normalize": True,
        "onnx_file": "text_encoder.onnx",
    }
    if quantize:
        config["onnx_file_quantized"] = "text_encoder_q8.onnx"
    (output_dir / "config.json").write_text(json.dumps(config, indent=2))

    size_mb = onnx_path.stat().st_size / (1024 * 1024)
    print(f"\nExport complete!")
    print(f"  Model: {onnx_path} ({size_mb:.1f} MB)")
    print(f"  Input:  int64 [batch, {context_length}]")
    print(f"  Output: float32 [batch, {embed_dim}] (L2-normalized)")

    return onnx_path, config


def benchmark(output_dir: Path, config: dict):
    """Benchmark ONNX text encoder inference on CPU."""
    import onnxruntime as ort
    import open_clip

    tokenizer = open_clip.get_tokenizer(MODEL_NAME)

    models = [("fp32", output_dir / config["onnx_file"])]
    if "onnx_file_quantized" in config:
        models.append(("int8", output_dir / config["onnx_file_quantized"]))

    for label, model_path in models:
        if not model_path.exists():
            print(f"Skipping {label}: {model_path} not found")
            continue

        print(f"\n{'=' * 60}")
        print(f"Benchmark: {label}  ({model_path.name})")
        print(f"{'=' * 60}")

        sess = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )

        # --- Single-text latency ---
        single = tokenizer(["a photo of a cat"]).numpy()
        for _ in range(20):  # warmup
            sess.run(None, {"input_ids": single})

        latencies = []
        for _ in range(200):
            t0 = time.perf_counter()
            sess.run(None, {"input_ids": single})
            latencies.append((time.perf_counter() - t0) * 1000)

        latencies.sort()
        print(f"\n  Single text (200 runs):")
        print(f"    p50  {latencies[99]:.2f} ms")
        print(f"    p95  {latencies[189]:.2f} ms")
        print(f"    p99  {latencies[197]:.2f} ms")
        print(f"    mean {np.mean(latencies):.2f} ms")

        # --- Batch throughput ---
        print(f"\n  Batch throughput (50 runs each):")
        for bs in [1, 4, 8, 16, 32]:
            tokens = tokenizer([f"query number {i}" for i in range(bs)]).numpy()
            for _ in range(10):  # warmup
                sess.run(None, {"input_ids": tokens})

            times = []
            for _ in range(50):
                t0 = time.perf_counter()
                sess.run(None, {"input_ids": tokens})
                times.append((time.perf_counter() - t0) * 1000)

            mean = np.mean(times)
            print(f"    batch={bs:>2}:  {mean:6.2f} ms total  ({mean / bs:.2f} ms/text)")


def main():
    parser = argparse.ArgumentParser(
        description="Export CoCa ViT-L-14 text encoder to ONNX and benchmark"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models/coca_text_encoder"),
    )
    parser.add_argument(
        "--quantize",
        action="store_true",
        help="Also produce an INT8 dynamically-quantized model",
    )
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument(
        "--benchmark-only",
        action="store_true",
        help="Skip export, benchmark existing model(s)",
    )
    args = parser.parse_args()

    if args.benchmark_only:
        config = json.loads((args.output_dir / "config.json").read_text())
        benchmark(args.output_dir, config)
    else:
        onnx_path, config = export(
            args.output_dir, quantize=args.quantize, opset=args.opset
        )
        benchmark(args.output_dir, config)


if __name__ == "__main__":
    main()
