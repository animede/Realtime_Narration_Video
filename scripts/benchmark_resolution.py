#!/usr/bin/env python3
"""Run a controlled, alternating resolution benchmark against the Gateway."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import datetime
from pathlib import Path
from time import perf_counter

from app.config import settings
from app.gateway import GatewayClient


PROFILES = {
    "A": "16fps-portrait-3x4",
    "B": "16fps-portrait-3x4-fast",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5, help="Runs per resolution")
    parser.add_argument("--seed", type=int, default=1004)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--modality-scale", type=float)
    parser.add_argument("--prompt", default="A character speaks naturally to the supplied audio.")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    if not args.image.is_file() or not args.audio.is_file():
        raise SystemExit("The image and audio files must exist")

    gateway = GatewayClient(settings.gateway_url, settings.gateway_preset, settings.poll_interval)
    image_id, audio_id = await asyncio.gather(
        gateway.upload(args.image), gateway.upload(args.audio)
    )
    rows: list[dict] = []
    # Reverse the first pair every other cycle to balance slow drift while keeping
    # neighboring A/B measurements close in time.
    order = [label for cycle in range(args.runs) for label in (("A", "B") if cycle % 2 == 0 else ("B", "A"))]
    for sequence, label in enumerate(order, 1):
        profile = PROFILES[label]
        started = perf_counter()
        result = await gateway.generate(
            image_id, audio_id, args.prompt, args.seed, profile, args.steps, 81,
            args.modality_scale,
        )
        elapsed = perf_counter() - started
        server_seconds = result.get("result", {}).get("generation_seconds")
        row = {
            "sequence": sequence,
            "variant": label,
            "profile": profile,
            "elapsed_seconds": round(elapsed, 3),
            "generation_seconds": server_seconds,
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    summaries = {}
    for label in PROFILES:
        selected = [row for row in rows if row["variant"] == label]
        elapsed = [row["elapsed_seconds"] for row in selected]
        generated = [float(row["generation_seconds"]) for row in selected if row["generation_seconds"] is not None]
        summaries[label] = {
            "profile": PROFILES[label],
            "runs": len(selected),
            "elapsed_mean": round(statistics.mean(elapsed), 3),
            "elapsed_median": round(statistics.median(elapsed), 3),
            "generation_mean": round(statistics.mean(generated), 3) if generated else None,
            "generation_median": round(statistics.median(generated), 3) if generated else None,
        }
    report = {
        "created_at": datetime.now().astimezone().isoformat(),
        "conditions": {
            "runs_per_variant": args.runs,
            "seed": args.seed,
            "steps": args.steps,
            "frames": 81,
            "modality_scale": args.modality_scale,
            "same_image_audio_prompt": True,
        },
        "summary": summaries,
        "runs": rows,
    }
    print(json.dumps({"summary": summaries}, ensure_ascii=False), flush=True)
    output = args.output or Path("data/benchmarks") / f"resolution-{datetime.now():%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"report={output}")


if __name__ == "__main__":
    asyncio.run(main())
