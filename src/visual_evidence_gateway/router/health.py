"""Backend health registry. Runtime never guesses: only healthy backends are used."""
from __future__ import annotations

from typing import Dict, List

from visual_evidence_gateway.backends.base import mask_secrets


def describe(cfg, name: str) -> Dict[str, object]:
    b = cfg.backend(name)
    return {
        "name": name,
        "ready": cfg.backend_ready(name),
        "healthy": b.get("healthy", False),
        "enabled": b.get("enabled", True),
        "model_configured": bool(str(b.get("model", "")).strip()),
        "via": b.get("via", ""),
        "vision_verified": b.get("vision_verified", False),
        "detail": mask_secrets(str(b.get("detail", "")))[:500],
        "elapsed_ms": b.get("elapsed_ms"),
    }


def summary(cfg) -> List[Dict[str, object]]:
    return [describe(cfg, name) for name in ("primary", "fallback", "verifier")]
