"""The default compute backend: every step runs in the run pod."""

from typing import Any

from dataroom.classifier import assets


def run(step: str, payload: dict[str, Any], client, env: str, log) -> dict[str, Any]:
    if step == "train":
        return assets.train_classifier(
            client,
            env,
            payload["slug_version"],
            assets.Examples(**payload["examples"]),
            assets.DataroomTrainConfig(**payload["config"]),
            log,
        )
    if step == "embed":
        return {"embedded": assets.embed_missing(client, payload["params"], payload["backbone"], payload["image_size"], log)}
    raise ValueError(f"unknown step {step!r}")


def run_step(step: str, payload: dict[str, Any], dataroom, run_id: str, log) -> dict[str, Any]:
    return run(step, payload, dataroom.client(), dataroom.env, log)
