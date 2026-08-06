"""Fallback vision backend using Responses API or the shared Codex CLI adapter."""
from __future__ import annotations

from visual_evidence_gateway.backends.base import call_responses_api, result_from_payload
from visual_evidence_gateway.backends.codex_cli import run_codex_cli
from visual_evidence_gateway.router.models import BackendResult
from visual_evidence_gateway.router.prompts import build_prompt


def run_fallback(norm, cfg, prior_summary=None, retry_crop=None) -> BackendResult:
    backend = cfg.backend("fallback")
    via = str(backend.get("via") or "responses_api").strip().lower()
    if via == "codex_cli":
        return run_codex_cli("fallback", norm, cfg, prior_summary=prior_summary, retry_crop=retry_crop)
    if via != "responses_api":
        return BackendResult(backend="fallback", ok=False, operational_failure=True, error=f"unsupported fallback transport: {via}")

    model = cfg.model_id("fallback")
    if not model:
        return BackendResult(backend="fallback", ok=False, operational_failure=True, error="fallback model is not configured")
    images = retry_crop or norm.staged
    prompt = build_prompt(
        norm,
        cfg,
        prior_summary=prior_summary,
        backend="fallback",
        focus="enhanced crop or tiles" if retry_crop else "",
    )
    ok, body, error = call_responses_api(
        cfg,
        model,
        prompt,
        images,
        reasoning_effort=backend.get("reasoning_effort"),
        backend_name="fallback",
    )
    return result_from_payload(
        "fallback",
        ok,
        body,
        error,
        model,
        len(images),
        norm.mode,
        require_resolved_model=bool(cfg.gateway.get("require_resolved_model", True)),
        accepted_model_ids=backend.get("accepted_model_ids", []),
    )
