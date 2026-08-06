"""Shared data shapes for the visual-evidence-gateway plugin."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BackendResult:
    """Normalized result of one vision backend call."""

    backend: str = "unknown"
    ok: bool = False
    operational_failure: bool = False
    semantic_insufficient: bool = False
    model_mismatch: bool = False
    status: str = "failed"
    answer: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    relevant_text: List[str] = field(default_factory=list)
    uncertainty: List[str] = field(default_factory=list)
    confidence: float = 0.0
    verified_model: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class NormalizedRequest:
    """Validated, normalized vision request with staged local images."""

    paths: List[Path] = field(default_factory=list)
    staged: List[Path] = field(default_factory=list)
    hashes: List[str] = field(default_factory=list)
    query: str = ""
    query_norm: str = ""
    mode: str = "general"
    rigor: str = "normal"
    job_dir: Optional[Path] = None
    cache_key: str = ""
