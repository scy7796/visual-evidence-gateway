"""Backend adapters for primary, verifier, and fallback roles."""

from visual_evidence_gateway.backends.fallback import run_fallback
from visual_evidence_gateway.backends.primary import run_primary
from visual_evidence_gateway.backends.verifier import run_verifier

__all__ = ["run_primary", "run_verifier", "run_fallback"]
