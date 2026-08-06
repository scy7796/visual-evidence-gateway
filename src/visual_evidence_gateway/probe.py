"""Deterministic backend vision probe with separate runtime health state."""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from visual_evidence_gateway.backends import run_fallback, run_primary, run_verifier
from visual_evidence_gateway.backends.base import mask_secrets
from visual_evidence_gateway.probe_image import generate
from visual_evidence_gateway.router.config import _has_path_indirection, load_config
from visual_evidence_gateway.router.models import NormalizedRequest
from visual_evidence_gateway.router.validator import _normalize

PROBE_TOKEN = "VISION_PROBE_7319"
_NUM_WORDS = {
    "1": 1, "one": 1, "一": 1,
    "2": 2, "two": 2, "二": 2, "两": 2,
    "3": 3, "three": 3, "三": 3,
    "4": 4, "four": 4, "四": 4,
}
RUNNERS = {"primary": run_primary, "verifier": run_verifier, "fallback": run_fallback}


def _count_near(search_text: str, keywords, count: int) -> bool:
    clauses = re.split(r"(?i)\b(?:and|while|plus)\b|[，,;；。.!?]", search_text)
    for clause in clauses:
        compact = re.sub(r"\s+", " ", clause)
        tokens = list(re.finditer(r"\d+|[a-zA-Z]+|[一二两三四]", compact))
        for keyword in keywords:
            for match in re.finditer(re.escape(keyword), compact, re.IGNORECASE):
                nearest = None
                distance = 1 << 30
                for token in tokens:
                    value = _NUM_WORDS.get(token.group(0).lower())
                    if value is None:
                        continue
                    current = min(abs(token.start() - match.end()), abs(token.start() - match.start()))
                    if current < distance:
                        distance = current
                        nearest = value
                if nearest == count:
                    return True
    return False


def probe_prompt(token: str = PROBE_TOKEN) -> str:
    # ``token`` is accepted for API compatibility but intentionally never
    # interpolated. Ground truth must exist only in pixels, not in the prompt.
    del token
    return (
        "Read the supplied image as visual evidence only. "
        "State the exact uppercase token shown at the top, the number of red circles, "
        "and the number of blue squares. Use exactly the phrases `red circles: <number>` "
        "and `blue squares: <number>` in your answer. Return only the configured JSON schema."
    )


def _canonical_count(answer: str, label: str) -> int | None:
    match = re.search(rf"{re.escape(label)}\s*[:：]\s*(\d+)", answer, re.IGNORECASE)
    return int(match.group(1)) if match else None


def check_probe_json(
    data,
    token: str = PROBE_TOKEN,
    *,
    red_count: int = 1,
    blue_count: int = 2,
) -> List[str]:
    issues: List[str] = []
    if not isinstance(data, dict):
        return ["output is not a JSON object"]
    if data.get("status") not in ("ok", "partial"):
        issues.append(f"unexpected status: {data.get('status')!r}")
    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        issues.append("answer is missing")
        answer = ""
    relevant = data.get("relevant_text")
    if not isinstance(relevant, list) or any(not isinstance(item, str) for item in (relevant or [])):
        issues.append("relevant_text must be a string array")
        relevant = []
    evidence = data.get("evidence")
    if not isinstance(evidence, list) or any(not isinstance(item, dict) for item in (evidence or [])):
        issues.append("evidence must be an object array")
    combined = answer + " " + " ".join(relevant or [])
    if token not in combined:
        issues.append(f"未读到 {token}")
    seen = data.get("images_seen")
    if isinstance(seen, bool) or not isinstance(seen, int) or seen != 1:
        issues.append(f"images_seen={seen!r}")
    normalized = _normalize(answer)
    if any(marker in normalized for marker in ("cannot", "unable", "无法", "不能")):
        issues.append("answer claims the image could not be read")
    canonical_red = _canonical_count(answer, "red circles")
    if canonical_red is None and not _count_near(answer, ["red circle", "red circles", "红色圆", "红圆", "红色圆形"], red_count):
        issues.append(f"未确认红色圆数量={red_count}")
    elif canonical_red is not None and canonical_red != red_count:
        issues.append(f"红色圆数量={red_count} 与回答不一致")
    canonical_blue = _canonical_count(answer, "blue squares")
    if canonical_blue is None and not _count_near(answer, ["blue square", "blue squares", "蓝色方块", "蓝方块", "蓝色方形", "蓝方形", "蓝色正方形", "蓝正方形"], blue_count):
        issues.append(f"未确认蓝色方块数量={blue_count}")
    elif canonical_blue is not None and canonical_blue != blue_count:
        issues.append(f"蓝色方块数量={blue_count} 与回答不一致")
    return issues


def _probe_backend(name: str, cfg, image: Path, token: str, red_count: int, blue_count: int) -> dict:
    backend = cfg.backend(name)
    if not backend.get("enabled", False):
        return {"healthy": False, "vision_verified": False, "detail": "backend is disabled"}
    via = str(backend.get("via", "responses_api")).strip().lower()
    model = cfg.model_id(name)
    if via == "responses_api" and not model:
        return {"healthy": False, "vision_verified": False, "detail": "model is not configured"}
    if via == "codex_cli" and not model and not backend.get("allow_cli_default_model", False):
        return {"healthy": False, "vision_verified": False, "detail": "model is not configured"}

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="visual-evidence-gateway-probe-") as directory:
        job_dir = Path(directory)
        staged = job_dir / "probe.png"
        staged.write_bytes(image.read_bytes())
        norm = NormalizedRequest(
            paths=[image],
            staged=[staged],
            hashes=["probe"],
            query=probe_prompt(token),
            query_norm=probe_prompt(token),
            mode="general",
            rigor="normal",
            job_dir=job_dir,
        )
        try:
            result = RUNNERS[name](norm, cfg)
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            return {
                "healthy": False,
                "vision_verified": False,
                "detail": mask_secrets(f"probe failed: {exc}")[:500],
                "elapsed_ms": elapsed_ms,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    issues = check_probe_json(result.raw, token, red_count=red_count, blue_count=blue_count) if result.ok else [result.error or result.status]
    passed = result.ok and not result.model_mismatch and not issues
    detail = "probe passed" if passed else "; ".join(str(issue) for issue in issues if issue)[:500]
    return {
        "healthy": bool(passed),
        "vision_verified": bool(passed),
        "detail": mask_secrets(detail),
        "elapsed_ms": elapsed_ms,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }



def _read_health_bytes(path: Path, limit: int = 1 << 20) -> Optional[bytes]:
    """Read one stable regular health-state file without following links."""
    try:
        if _has_path_indirection(path):
            return None
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > limit:
            return None
        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            data = handle.read(limit + 1)
            after_open = os.fstat(handle.fileno())
        after = path.lstat()
        changed = (
            len(data) > limit
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or (opened.st_dev, opened.st_ino) != (after_open.st_dev, after_open.st_ino)
            or (after_open.st_dev, after_open.st_ino) != (after.st_dev, after.st_ino)
            or before.st_size != after_open.st_size
            or after_open.st_size != after.st_size
            or getattr(before, "st_mtime_ns", None) != getattr(after_open, "st_mtime_ns", None)
            or getattr(after_open, "st_mtime_ns", None) != getattr(after, "st_mtime_ns", None)
            or _has_path_indirection(path)
        )
        return None if changed else data
    except OSError:
        return None


def _existing_states(path: Path, expected_fingerprints: Optional[dict[str, str]] = None) -> dict:
    raw = _read_health_bytes(path)
    if raw is None:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        return {}
    states = data.get("backends", {}) if isinstance(data, dict) else {}
    if not isinstance(states, dict):
        return {}
    sanitized = {}
    for name in RUNNERS:
        state = states.get(name)
        if not isinstance(state, dict):
            continue
        expected = (expected_fingerprints or {}).get(name)
        fingerprint = state.get("config_fingerprint")
        if expected is not None and fingerprint != expected:
            continue
        clean = {}
        for key in ("healthy", "vision_verified"):
            if type(state.get(key)) is bool:
                clean[key] = state[key]
        for key in ("detail", "checked_at"):
            if isinstance(state.get(key), str):
                clean[key] = state[key][:500]
        elapsed_ms = state.get("elapsed_ms")
        if (
            not isinstance(elapsed_ms, bool)
            and isinstance(elapsed_ms, (int, float))
            and 0 <= elapsed_ms <= 3_600_000
        ):
            clean["elapsed_ms"] = round(float(elapsed_ms), 1)
        if isinstance(fingerprint, str) and len(fingerprint) == 64 and all(ch in "0123456789abcdef" for ch in fingerprint):
            clean["config_fingerprint"] = fingerprint
        if clean:
            sanitized[name] = clean
    return sanitized


def _atomic_write_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(encoded) > (1 << 20):
        raise OSError("health state exceeds 1 MiB")
    path = Path(path)
    if _has_path_indirection(path):
        raise OSError("health state path must not traverse a symlink, junction, or reparse point")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _has_path_indirection(path):
        raise OSError("health state path became unsafe")
    if path.exists() or path.is_symlink():
        current = path.lstat()
        if not stat.S_ISREG(current.st_mode) or _has_path_indirection(path):
            raise OSError("health state path is not a regular file")

    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(temporary, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        written = temporary.lstat()
        if not stat.S_ISREG(written.st_mode) or written.st_size != len(encoded) or _has_path_indirection(temporary):
            raise OSError("health state temporary file changed during write")
        if path.exists() or path.is_symlink():
            current = path.lstat()
            if not stat.S_ISREG(current.st_mode) or _has_path_indirection(path):
                raise OSError("health state target changed before replace")
        os.replace(temporary, path)
        final = path.lstat()
        if not stat.S_ISREG(final.st_mode) or final.st_size != len(encoded) or _has_path_indirection(path):
            raise OSError("health state target changed after replace")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Visual Evidence Gateway backend probes")
    parser.add_argument("--config", type=Path, default=None, help="Path to YAML or JSON configuration")
    parser.add_argument("--backend", action="append", choices=sorted(RUNNERS), help="Probe only the selected backend; repeatable")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(config_path=args.config)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": mask_secrets(str(exc))}, ensure_ascii=False))
        return 1

    selected = args.backend or [name for name in RUNNERS if cfg.backend(name).get("enabled", False)]
    if not selected:
        print("No enabled backend was selected.")
        return 2

    token = f"VISION_PROBE_{uuid.uuid4().hex[:10].upper()}"
    red_count = 1 + secrets.randbelow(4)
    blue_count = 1 + secrets.randbelow(4)
    with tempfile.TemporaryDirectory(prefix="visual-evidence-gateway-probe-image-") as directory:
        image = generate(
            Path(directory) / "probe.png",
            token,
            red_count=red_count,
            blue_count=blue_count,
        )
        states = {
            name: _probe_backend(name, cfg, image, token, red_count, blue_count)
            for name in selected
        }
        for name, state in states.items():
            state["config_fingerprint"] = cfg.probe_fingerprint(name)

    expected_fingerprints = {name: cfg.probe_fingerprint(name) for name in RUNNERS}
    merged_states = _existing_states(cfg.health_path, expected_fingerprints)
    merged_states.update(states)
    payload = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backends": merged_states,
    }
    try:
        _atomic_write_json(cfg.health_path, payload)
    except OSError as exc:
        error = mask_secrets(f"failed to write health state: {exc}")
        print(json.dumps({"status": "error", "error": error}, ensure_ascii=False))
        return 1
    passed = all(state.get("healthy") for state in states.values())
    output = {"status": "ok" if passed else "failed", "health_path": str(cfg.health_path), "backends": states}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for name, state in states.items():
            elapsed = state.get("elapsed_ms")
            timing = f" ({elapsed:.1f} ms)" if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) else ""
            print(f"{name}: {'PASS' if state['healthy'] else 'FAIL'}{timing} - {state['detail']}")
        print(f"health state: {cfg.health_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
