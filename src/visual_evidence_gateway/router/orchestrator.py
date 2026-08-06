"""Single-entry vision routing orchestrator (spec section 19)."""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional

from visual_evidence_gateway.router.cache import VisionCache
from visual_evidence_gateway.backends.base import mask_error
from visual_evidence_gateway.router.config import Config
from visual_evidence_gateway.router.models import BackendResult, NormalizedRequest
from visual_evidence_gateway.router.preprocess import (
    ImageRejected,
    check_path,
    crop_zoom,
    file_sha256,
    make_job_dir,
    make_tiles,
    region_hint,
    safe_cleanup,
    stage_images,
)
from visual_evidence_gateway.router.policy import is_semantic_insufficient
from visual_evidence_gateway.router.reducer import build_compact
from visual_evidence_gateway.router.validator import detect_injection

REFUSAL_ANSWER = "视觉材料当前不可访问，因此未进行视觉验收。"

_LABELS = {"primary": "主视觉后端", "fallback": "备用后端", "verifier": "复核后端"}


def _label(backend: str) -> str:
    return _LABELS.get(backend, backend)


def _injected(r: BackendResult) -> bool:
    """Injection check that works even when raw payload is empty."""
    return detect_injection(r.raw if r.raw else {"answer": r.answer})


def refusal(reason: str) -> dict:
    return {
        "status": "failed",
        "answer": REFUSAL_ANSWER,
        "evidence": [],
        "relevant_text": [],
        "uncertainty": [],
        "verified_by": [],
        "detail_ref": None,
        "full_text_ref": None,
        "trimmed": False,
        "reason": mask_error(reason),
    }


def _invalid_unicode(value: str) -> bool:
    try:
        value.encode("utf-8")
        return False
    except UnicodeEncodeError:
        return True


def _normalize(request: dict, cfg: Config) -> NormalizedRequest:
    if not isinstance(request, dict):
        raise ImageRejected("请求必须是 JSON 对象")
    extra_fields = set(request) - {"paths", "query", "mode", "rigor"}
    if extra_fields:
        raise ImageRejected("请求包含未声明字段: " + ", ".join(sorted(str(v) for v in extra_fields)))
    paths_in = request.get("paths")
    if not isinstance(paths_in, list) or not paths_in:
        raise ImageRejected("缺少 paths（1～4 张绝对路径图片）")
    if len(paths_in) > cfg.limits.get("max_images", 4):
        raise ImageRejected(f"paths 最多 {cfg.limits.get('max_images', 4)} 张")
    if any(
        not isinstance(value, str)
        or not value.strip()
        or "\x00" in value
        or len(value) > 4096
        or _invalid_unicode(value)
        for value in paths_in
    ):
        raise ImageRejected("paths 只能包含长度受限且不含 NUL 的非空字符串")

    query_value = request.get("query")
    if not isinstance(query_value, str):
        raise ImageRejected("query 必须是字符串")
    query = query_value.strip()
    if not query:
        raise ImageRejected("缺少 query")
    if "\x00" in query or len(query) > 800 or _invalid_unicode(query):
        raise ImageRejected("query 非法或过长（>800 字符）")

    mode_value = request.get("mode", "auto")
    if not isinstance(mode_value, str):
        raise ImageRejected("mode 必须是字符串")
    mode = mode_value.strip() or "auto"
    if mode == "auto":
        mode = "compare" if len(paths_in) == 2 else "general"
    if mode not in {"ui", "text", "chart", "diagram", "compare", "general"}:
        raise ImageRejected(f"mode 非法: {mode}")
    if mode == "compare" and len(paths_in) != 2:
        raise ImageRejected("compare 模式必须恰好提供 2 张图片（before/after）")

    rigor_value = request.get("rigor", "normal")
    if not isinstance(rigor_value, str):
        raise ImageRejected("rigor 必须是字符串")
    rigor = rigor_value.strip() or "normal"
    if rigor not in {"normal", "critical", "cheap"}:
        raise ImageRejected(f"rigor 非法: {rigor}")
    paths = [check_path(value, cfg) for value in paths_in]
    return NormalizedRequest(
        paths=paths,
        hashes=[],
        query=query,
        query_norm=" ".join(query.split()),
        mode=mode,
        rigor=rigor,
    )


def _compact_prior(result: BackendResult) -> dict:
    return {
        "status": result.status,
        "answer": result.answer[:200],
        "evidence": result.evidence[:3],
        "uncertainty": result.uncertainty[:2],
    }


def _finish(results: List[BackendResult], norm: NormalizedRequest, cfg: Config, cache: VisionCache) -> dict:
    compact, raws = build_compact(results, norm.rigor, norm.cache_key, cache, cfg)
    for r in results:
        if r.model_mismatch:
            note = f"{_label(r.backend)} 返回模型 {r.verified_model} 与配置不符，结果未作为正式验收证据"
            if note not in compact["uncertainty"]:
                compact["uncertainty"] = compact["uncertainty"][:2] + [note]
    sufficient = [
        r
        for r in results
        if r.ok and not r.model_mismatch and not is_semantic_insufficient(r, norm.mode, cfg)
    ]
    if not sufficient:
        if compact["status"] == "ok":
            compact["status"] = "partial"
        best = max((r for r in results if r.ok and not r.model_mismatch), key=lambda r: r.confidence, default=None)
        if best is not None:
            note = f"{_label(best.backend)} 结果置信度不足（{best.confidence:.2f}）且复核后端不可用，结论仅供参考"
            if note not in compact["uncertainty"]:
                compact["uncertainty"] = (compact["uncertainty"] + [note])[:3]
    if compact["status"] != "ok" and not compact["uncertainty"]:
        suffix = "，详见 detail_ref" if compact.get("detail_ref") else ""
        compact["uncertainty"] = [f"结论状态为 {compact['status']}，证据不完整{suffix}"]
    if norm.rigor == "critical" and len(results) == 1:
        note = "critical 复核后端不可用，仅单后端验证"
        if note not in compact["uncertainty"]:
            compact["uncertainty"] = (compact["uncertainty"] + [note])[:3]
    # Notes appended above must not break the hard token budget.
    from visual_evidence_gateway.router.reducer import estimate_tokens

    budget = cfg.budget_tokens.get("critical" if norm.rigor == "critical" else "normal", 350)
    while estimate_tokens(compact) > budget and compact["uncertainty"]:
        compact["uncertainty"].pop()
        compact["trimmed"] = True
    meta = {
        "query_hash": norm.cache_key[:16],
        "mode": norm.mode,
        "rigor": norm.rigor,
        "images": [h[:12] for h in norm.hashes],
        "backends": [r.backend for r in results],
        "status": compact["status"],
    }
    # Do not cache transient or total backend failures. A failed entry would
    # otherwise pin a temporary outage to this image/query until manual cache
    # removal. Partial evidence remains cacheable when at least one backend
    # produced a schema-valid, model-verified result.
    if compact["status"] in {"ok", "partial"} and any(
        result.ok and not result.model_mismatch for result in results
    ):
        cache.store(norm.cache_key, compact, raws, meta)
    return compact


def _retry_files_within_limits(paths, cfg: Config) -> bool:
    total = 0
    max_one = int(cfg.limits.get("max_image_bytes", 20 << 20))
    max_total = int(cfg.limits.get("max_staged_bytes", 40 << 20))
    try:
        for path in paths:
            size = path.stat().st_size
            if size <= 0 or size > max_one:
                return False
            total += size
            if total > max_total:
                return False
    except OSError:
        return False
    return True


def _discard_retry_files(paths) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _retry_enhance(norm: NormalizedRequest, cfg: Config, runner, primary_result: BackendResult) -> Optional[BackendResult]:
    if not cfg.prompt_settings.get("retry_crop", True) or not norm.staged or len(norm.paths) != 1:
        return None
    hint = region_hint(primary_result)
    if hint:
        crop = norm.job_dir / "enhanced-1.png"
        if crop_zoom(norm.staged[0], crop, hint):
            if _retry_files_within_limits([crop], cfg):
                return runner(norm, cfg, retry_crop=[crop])
            _discard_retry_files([crop])
    tiles = make_tiles(norm.staged[0], norm.job_dir)
    if tiles:
        if _retry_files_within_limits(tiles, cfg):
            return runner(norm, cfg, retry_crop=tiles)
        _discard_retry_files(tiles)
    return None


def _route_operational_failure(norm: NormalizedRequest, cfg: Config, runners, primary: BackendResult) -> List[BackendResult]:
    # Degradation order: verifier first (strongest verifier), fallback as fallback.
    verifier = runners["verifier"](norm, cfg, prior_summary=_compact_prior(primary)) if cfg.backend_ready("verifier") else None
    if verifier and verifier.ok and not verifier.model_mismatch:
        return [verifier]
    fallback = runners["fallback"](norm, cfg) if cfg.backend_ready("fallback") else None
    if fallback and fallback.ok and not fallback.model_mismatch:
        return [fallback]
    return [primary, verifier] if verifier and verifier.ok else [primary]


def default_runners() -> Dict[str, Callable]:
    from visual_evidence_gateway.backends.verifier import run_verifier
    from visual_evidence_gateway.backends.primary import run_primary
    from visual_evidence_gateway.backends.fallback import run_fallback

    return {"primary": run_primary, "verifier": run_verifier, "fallback": run_fallback}


def inspect(request: dict, cfg: Config, runners: Optional[Dict[str, Callable]] = None) -> dict:
    """Single entry point. Never guesses; refuses when no valid evidence exists."""
    if os.environ.get("VISUAL_EVIDENCE_GATEWAY_CHILD") == "1":
        return refusal("递归保护：视觉子进程内禁止再次调用 vision.inspect")
    runners = runners or default_runners()
    try:
        norm = _normalize(request, cfg)
    except ImageRejected as e:
        return refusal(e.reason)

    try:
        cache = VisionCache(
            cfg.cache_dir,
            store_raw=bool(cfg.cache_settings.get("store_raw", False)),
            store_full_text=bool(cfg.cache_settings.get("store_full_text", False)),
            expose_local_refs=bool(cfg.cache_settings.get("expose_local_refs", False)),
        )
        job_dir = make_job_dir()
    except (OSError, ValueError, TypeError) as exc:
        return refusal(f"运行时隔离目录不可用：{type(exc).__name__}")
    norm.job_dir = job_dir
    try:
        try:
            norm.staged = stage_images(norm.paths, job_dir, cfg)
        except ImageRejected as e:
            return refusal(e.reason)
        # Cache the exact normalized bytes sent to providers. Hashing the source
        # before staging would allow a source-file race to poison the cache key.
        norm.hashes = [file_sha256(path) for path in norm.staged]
        norm.cache_key = cache.key(norm, cfg)
        hit = cache.get(norm.cache_key)
        if hit is not None:
            if detect_injection(hit):
                return refusal("缓存命中内容未通过注入终检，已忽略缓存")
            from visual_evidence_gateway.router.reducer import estimate_tokens

            budget = cfg.budget_tokens.get("critical" if norm.rigor == "critical" else "normal", 350)
            if estimate_tokens(hit) <= budget:
                return hit
            # Over-budget cache entries are treated as misses and rebuilt.
        if cfg.backend_ready("primary"):
            primary = runners["primary"](norm, cfg)
        else:
            # Health gate: a backend marked unhealthy (e.g. quota-exhausted) is
            # skipped instead of paying a failing round-trip on every request.
            primary = BackendResult(
                backend="primary",
                ok=False,
                operational_failure=True,
                error="primary 未通过健康检查，已跳过",
            )

        if norm.rigor == "cheap":
            if primary.operational_failure or is_semantic_insufficient(primary, norm.mode, cfg):
                verifier = runners["verifier"](norm, cfg, prior_summary=_compact_prior(primary)) if cfg.backend_ready("verifier") else None
                if verifier and verifier.ok and not verifier.model_mismatch:
                    results = [verifier]
                else:
                    fallback = runners["fallback"](norm, cfg) if cfg.backend_ready("fallback") else None
                    results = [fallback] if (fallback and fallback.ok and not fallback.model_mismatch) else [primary]
            else:
                results = [primary]
        elif primary.operational_failure:
            results = _route_operational_failure(norm, cfg, runners, primary)
        elif norm.rigor == "critical":
            verifier = (
                runners["verifier"](norm, cfg, prior_summary=_compact_prior(primary))
                if cfg.backend_ready("verifier")
                else None
            )
            results = [primary, verifier] if verifier and verifier.ok else [primary]
        elif primary.model_mismatch:
            verifier = (
                runners["verifier"](norm, cfg, prior_summary=_compact_prior(primary))
                if cfg.backend_ready("verifier")
                else None
            )
            results = [primary, verifier] if verifier and verifier.ok else [primary]
        elif is_semantic_insufficient(primary, norm.mode, cfg):
            if _injected(primary):
                # 注入不是视觉质量问题，重试无意义；直接进入最终闸口。
                results = [primary]
            else:
                enhanced = _retry_enhance(norm, cfg, runners["primary"], primary)
                if (
                    enhanced
                    and enhanced.ok
                    and not enhanced.model_mismatch
                    and not is_semantic_insufficient(enhanced, norm.mode, cfg)
                ):
                    results = [enhanced]
                else:
                    candidate = enhanced if (enhanced and enhanced.ok and not enhanced.model_mismatch) else primary
                    verifier = (
                        runners["verifier"](norm, cfg, prior_summary=_compact_prior(candidate))
                        if cfg.backend_ready("verifier")
                        else None
                    )
                    results = [candidate, verifier] if verifier and verifier.ok else [candidate]
        else:
            results = [primary]

        # Final deterministic gate: an answer claiming to execute image
        # instructions is never valid evidence, regardless of backend flags.
        before_gate = list(results)
        results = [r for r in results if r is not None and not _injected(r)]
        ok_results = [r for r in results if r.ok and not r.model_mismatch]
        if not ok_results:
            rejected_for_injection = any(r is not None and _injected(r) for r in before_gate)
            reasons = "; ".join(f"{_label(r.backend)}: {r.error or r.status}" for r in results)
            if rejected_for_injection:
                reasons = (reasons + "; " if reasons else "") + "one or more backend results failed the prompt-injection gate"
            return refusal(f"所有视觉后端均未能产生有效证据（{reasons or 'no usable backend result'}）")
        return _finish(results, norm, cfg, cache)
    finally:
        safe_cleanup(job_dir)
