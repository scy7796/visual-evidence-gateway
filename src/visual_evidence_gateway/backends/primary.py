"""Primary vision backend using Responses API or the shared Codex CLI adapter."""
from __future__ import annotations

from visual_evidence_gateway.backends.base import call_responses_api, result_from_payload
from visual_evidence_gateway.backends.codex_cli import run_codex_cli
from visual_evidence_gateway.router.models import BackendResult
from visual_evidence_gateway.router.prompts import build_prompt


def run_primary(norm, cfg, prior_summary=None, retry_crop=None) -> BackendResult:
    backend = cfg.backend("primary")
    via = str(backend.get("via") or "responses_api").strip().lower()
    if via == "codex_cli":
        return run_codex_cli("primary", norm, cfg, prior_summary=prior_summary, retry_crop=retry_crop)
    if via != "responses_api":
        return BackendResult(backend="primary", ok=False, operational_failure=True, error=f"unsupported primary transport: {via}")

    model = cfg.model_id("primary")
    if not model:
        return BackendResult(backend="primary", ok=False, operational_failure=True, error="primary model is not configured")
    images = retry_crop or norm.staged
    prompt = build_prompt(
        norm,
        cfg,
        prior_summary=prior_summary,
        backend="primary",
        focus="enhanced crop or tiles" if retry_crop else "",
    )
    ok, body, error = call_responses_api(
        cfg,
        model,
        prompt,
        images,
        reasoning_effort=backend.get("reasoning_effort"),
        backend_name="primary",
    )
    return result_from_payload(
        "primary",
        ok,
        body,
        error,
        model,
        len(images),
        norm.mode,
        require_resolved_model=bool(cfg.gateway.get("require_resolved_model", True)),
        accepted_model_ids=backend.get("accepted_model_ids", []),
    )
