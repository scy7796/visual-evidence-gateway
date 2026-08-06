"""unittest suite for visual-evidence-gateway (spec acceptance tests T1-T10)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def make_cfg(tmp: Path, **overrides: Any) -> Any:
    from visual_evidence_gateway.router.config import Config, DEFAULTS, _deep_merge

    data = _deep_merge(
        DEFAULTS,
        {
            "project_root": str(tmp),
            "cache_dir": str(tmp / "cache"),
            "allowed_roots": [str(tmp)],
            "forbidden_roots": [str(tmp / "forbidden")],
            "backends": {
                "primary": {"healthy": True, "enabled": True, "model": "primary-model", "via": "responses_api"},
                "verifier": {"healthy": True, "enabled": True, "model": "verifier-model", "via": "responses_api"},
                "fallback": {"healthy": True, "enabled": True, "vision_verified": True, "model": "fallback-model", "via": "responses_api"},
            },
        },
    )
    data = _deep_merge(data, overrides)
    return Config(data, PLUGIN_ROOT)


def make_image(path: Path, color=(200, 30, 30), size=(64, 48), text: str | None = None) -> Path:
    img = Image.new("RGB", size, color)
    if text:
        draw = ImageDraw.Draw(img)
        draw.text((4, 4), text, fill=(0, 0, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    return path
