"""Verifier backend using either Responses API or the shared Codex CLI adapter."""
from __future__ import annotations

from visual_evidence_gateway.backends.base import call_responses_api, result_from_payload
from visual_evidence_gateway.backends.codex_cli import run_codex_cli
from visual_evidence_gateway.router.models import BackendResult
from visual_evidence_gateway.router.prompts import build_prompt


def run_verifier(norm, cfg, prior_summary=None, retry_crop=None) -> BackendResult:
    backend = cfg.backend("verifier")
    via = str(backend.get("via") or "responses_api").strip().lower()
    if via == "codex_cli":
        return run_codex_cli("verifier", norm, cfg, prior_summary=prior_summary, retry_crop=retry_crop)
    if via != "responses_api":
        return BackendResult(
            backend="verifier", ok=False, operational_failure=True, error=f"unsupported verifier transport: {via}"
        )

    model = cfg.model_id("verifier")
    if not model:
        return BackendResult(backend="verifier", ok=False, operational_failure=True, error="verifier model is not configured")
    images = retry_crop or norm.staged
    prompt = build_prompt(
        norm,
        cfg,
        prior_summary=prior_summary,
        backend="verifier",
        focus="enhanced crop or tiles" if retry_crop else "",
    )
    ok, body, error = call_responses_api(
        cfg,
        model,
        prompt,
        images,
        reasoning_effort=backend.get("reasoning_effort"),
        backend_name="verifier",
    )
    return result_from_payload(
        "verifier",
        ok,
        body,
        error,
        model,
        len(images),
        norm.mode,
        require_resolved_model=bool(cfg.gateway.get("require_resolved_model", True)),
        accepted_model_ids=backend.get("accepted_model_ids", []),
    )


def _run_codex_cli(norm, cfg, prior_summary=None, retry_crop=None) -> BackendResult:
    """Compatibility wrapper retained for pre-0.3 integrations."""
    return run_codex_cli("verifier", norm, cfg, prior_summary=prior_summary, retry_crop=retry_crop)
