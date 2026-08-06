#!/usr/bin/env python3
"""Reproducible benchmark for Visual Evidence Gateway's local orchestration overhead.

This intentionally replaces the remote visual model with a deterministic stub.
It measures path checks, stable image reading, decoding/normalization, private
staging, cache lookup/write, result reduction, and cleanup. It does not measure
network or Luna inference latency; use ``visual-evidence-gateway-probe --json`` for the
live end-to-end probe time on the operator's own account and network.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import statistics
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

from visual_evidence_gateway.router.config import Config, DEFAULTS, package_root
from visual_evidence_gateway.router.models import BackendResult
from visual_evidence_gateway.router.orchestrator import inspect


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * fraction))
    return ordered[index]


def make_config(root: Path) -> Config:
    data = copy.deepcopy(DEFAULTS)
    data["project_root"] = str(root)
    data["cache_dir"] = str(root / "cache")
    data["health_file"] = str(root / "health.json")
    data["allowed_roots"] = [str(root)]
    data["forbidden_roots"] = [str(root / "forbidden")]
    data["backends"]["primary"].update(
        {
            "enabled": True,
            "healthy": True,
            "require_probe": False,
            "via": "responses_api",
            "model": "benchmark-stub",
        }
    )
    for role in ("verifier", "fallback"):
        data["backends"][role].update({"enabled": False, "healthy": False, "model": ""})
    return Config(data, package_root(), health_path=root / "health.json")


def make_screenshot(path: Path, width: int, height: int) -> None:
    image = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    rows = max(1, min(80, height // 18))
    for index in range(rows):
        draw.text(
            (20, 10 + index * 17),
            f"row {index}: sample terminal or UI text {index * index}",
            fill=(20, 20, 20),
        )
    image.save(path, "PNG", optimize=True)


def run(iterations: int, cache_iterations: int, width: int, height: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="visual-evidence-gateway-benchmark-") as directory:
        root = Path(directory)
        image = root / "screen.png"
        make_screenshot(image, width, height)
        cfg = make_config(root)
        calls = 0

        def primary(norm, config, prior_summary=None, retry_crop=None):  # noqa: ARG001
            nonlocal calls
            calls += 1
            return BackendResult(
                backend="primary",
                ok=True,
                status="ok",
                answer="The benchmark image contains sample interface text.",
                evidence=[
                    {
                        "finding": "sample interface text is visible",
                        "location": "center",
                        "confidence": 0.95,
                        "image_index": 0,
                    }
                ],
                relevant_text=["sample terminal or UI text"],
                uncertainty=[],
                confidence=0.95,
                verified_model="benchmark-stub",
            )

        runners = {"primary": primary, "verifier": primary, "fallback": primary}
        inspect(
            {"paths": [str(image)], "query": "warmup", "mode": "ui", "rigor": "normal"},
            cfg,
            runners,
        )

        uncached: list[float] = []
        for index in range(iterations):
            started = time.perf_counter_ns()
            result = inspect(
                {
                    "paths": [str(image)],
                    "query": f"unique benchmark question {index}",
                    "mode": "ui",
                    "rigor": "normal",
                },
                cfg,
                runners,
            )
            if result.get("status") != "ok":
                raise RuntimeError(f"unexpected benchmark result: {result}")
            uncached.append((time.perf_counter_ns() - started) / 1_000_000)

        fixed_query = "fixed cache benchmark question"
        inspect(
            {"paths": [str(image)], "query": fixed_query, "mode": "ui", "rigor": "normal"},
            cfg,
            runners,
        )
        before_hits = calls
        cached: list[float] = []
        for _ in range(cache_iterations):
            started = time.perf_counter_ns()
            result = inspect(
                {"paths": [str(image)], "query": fixed_query, "mode": "ui", "rigor": "normal"},
                cfg,
                runners,
            )
            if result.get("status") != "ok":
                raise RuntimeError(f"unexpected cache benchmark result: {result}")
            cached.append((time.perf_counter_ns() - started) / 1_000_000)

        return {
            "scope": "local orchestration only; excludes network and model inference",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "image": {"width": width, "height": height, "bytes": image.stat().st_size},
            "uncached": {
                "iterations": len(uncached),
                "median_ms": round(statistics.median(uncached), 3),
                "p95_ms": round(percentile(uncached, 0.95), 3),
                "max_ms": round(max(uncached), 3),
            },
            "cache_hit": {
                "iterations": len(cached),
                "median_ms": round(statistics.median(cached), 3),
                "p95_ms": round(percentile(cached, 0.95), 3),
                "max_ms": round(max(cached), 3),
                "backend_calls": calls - before_hits,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=80)
    parser.add_argument("--cache-iterations", type=int, default=300)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10_000 or not 1 <= args.cache_iterations <= 100_000:
        parser.error("iteration counts are outside the supported range")
    if not 16 <= args.width <= 16_384 or not 16 <= args.height <= 16_384:
        parser.error("image dimensions are outside the supported range")
    print(json.dumps(run(args.iterations, args.cache_iterations, args.width, args.height), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
