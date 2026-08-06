"""Codex CLI transport for subscription-backed visual inspection.

The adapter is role-neutral: primary, verifier, and fallback may all use it.
It deliberately inherits only the minimum environment needed to locate the
Codex installation and the user's existing Codex authentication/configuration.
"""
from __future__ import annotations

import functools
import os
import re
import shutil
import signal
import stat
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from visual_evidence_gateway.backends.base import mask_error, mask_secrets, mask_tree
from visual_evidence_gateway.router.models import BackendResult
from visual_evidence_gateway.router.prompts import build_prompt
from visual_evidence_gateway.router.validator import detect_injection, extract_json, validate_backend_payload

_ALLOWED_EXTRA_ARGS = {"--ephemeral", "--ignore-user-config"}
_MAX_CLI_RESULT_BYTES = 1 << 20
_MAX_PROMPT_BYTES = 128 << 10
_VERSION_RE = re.compile(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)")

# The vision bridge supplies images directly and does not need Codex agent tools.
# These non-user-configurable overrides reduce the prompt-injection blast radius,
# suppress transcript persistence, and prevent unrelated network/plugin activity.
_MANDATORY_CONFIG_OVERRIDES = (
    'features.shell_tool=false',
    'features.shell_snapshot=false',
    'features.skill_mcp_dependency_install=false',
    'features.remote_plugin=false',
    'features.multi_agent=false',
    'features.hooks=false',
    'features.goals=false',
    'web_search="disabled"',
    'history.persistence="none"',
    'feedback.enabled=false',
    'analytics.enabled=false',
    'otel.metrics_exporter="none"',
    'otel.trace_exporter="none"',
    'otel.log_user_prompt=false',
)


def _safe_extra_args(values: Iterable[Any], role: str = "backend") -> list[str]:
    """Allow only documented, argument-free hardening flags."""
    out: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError(f"invalid {role} extra_args entry")
        if value not in _ALLOWED_EXTRA_ARGS:
            raise ValueError(f"unsupported {role} extra_args entry: {value}")
        if value not in out:
            out.append(value)
    return out


def _find_codex(cfg, role: str) -> str:
    command = str(cfg.backend(role).get("command") or "codex").strip()
    if not command:
        return ""
    path = Path(command)
    if path.is_absolute():
        return str(path) if path.is_file() else ""
    return shutil.which(command) or ""


def _sanitized_child_env(pass_env: Iterable[str], *, auth_mode: str = "existing") -> Dict[str, str]:
    # CODEX_HOME is intentionally retained: it contains the user's selected
    # Codex/OpenCodex catalog and login location. API-key variables are not in
    # the baseline, so a subscription-first backend cannot silently inherit
    # OPENAI_API_KEY and switch to usage-based billing.
    baseline = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "CODEX_HOME",
        "CODEX_CA_CERTIFICATE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "TMP",
        "TEMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "TERM",
    }
    requested = {str(name) for name in pass_env}
    if (auth_mode or "existing").strip().lower() == "chatgpt":
        # Subscription mode must not inherit ANY API-billing or alternate-provider
        # credential/base-url variable, even when pass_env requests it.
        requested -= {
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_ORG_ID",
            "OPENAI_PROJECT_ID",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "CODEX_API_KEY",
        }
    allowed = baseline | requested
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env["VISUAL_EVIDENCE_GATEWAY_CHILD"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _images_within_limits(images, cfg) -> bool:
    total = 0
    max_one = int(cfg.limits.get("max_image_bytes", 20 << 20))
    max_total = int(cfg.limits.get("max_staged_bytes", 16 << 20))
    try:
        for image in images:
            size = Path(image).stat().st_size
            if size <= 0 or size > max_one:
                return False
            total += size
            if total > max_total:
                return False
    except OSError:
        return False
    return True


def _parse_version(text: str) -> Tuple[int, int, int] | None:
    match = _VERSION_RE.search(text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _required_version(raw: Any) -> Tuple[int, int, int] | None:
    if raw in (None, ""):
        return None
    if not isinstance(raw, str) or not re.fullmatch(r"\d+\.\d+\.\d+", raw.strip()):
        raise ValueError("min_cli_version must use MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in raw.strip().split("."))


@functools.lru_cache(maxsize=16)
def _codex_version(executable: str, codex_home: str) -> tuple[Tuple[int, int, int] | None, str]:
    env = _sanitized_child_env(["CODEX_HOME"] if codex_home else [])
    if codex_home:
        env["CODEX_HOME"] = codex_home
    rc, stdout, stderr, overflow = _run_bounded(
        [executable, "--version"],
        env,
        str(Path.cwd()),
        timeout=10,
        stdout_cap=64 << 10,
        stderr_cap=64 << 10,
    )
    if rc is None:
        return None, "Codex CLI could not be started"
    if overflow:
        return None, "Codex CLI version output exceeded safety limits"
    text = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
    version = _parse_version(text)
    if rc != 0 or version is None:
        return None, mask_error(f"unable to determine Codex CLI version: {text[-300:]}")
    return version, ""


def _check_minimum_version(executable: str, backend: dict) -> tuple[bool, str]:
    try:
        required = _required_version(backend.get("min_cli_version"))
    except ValueError as exc:
        return False, str(exc)
    if required is None:
        return True, ""
    codex_home = os.environ.get("CODEX_HOME", "")
    actual, error = _codex_version(executable, codex_home)
    if actual is None:
        return False, error
    if actual < required:
        current = ".".join(str(part) for part in actual)
        minimum = ".".join(str(part) for part in required)
        return False, f"Codex CLI {current} is older than required {minimum}"
    return True, ""


def _auth_override(auth_mode: str) -> list[str]:
    normalized = (auth_mode or "existing").strip().lower()
    if normalized == "existing":
        return []
    if normalized not in {"chatgpt", "api"}:
        raise ValueError("auth_mode must be chatgpt, api, or existing")
    return ["-c", f'forced_login_method="{normalized}"']


def _mandatory_security_overrides() -> list[str]:
    out: list[str] = []
    for value in _MANDATORY_CONFIG_OVERRIDES:
        out.extend(["-c", value])
    return out


def _reasoning_override(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, str):
        raise ValueError("reasoning_effort must be a string")
    normalized = raw.strip().lower()
    if normalized not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("reasoning_effort must be none, low, medium, high, xhigh, or max")
    return ["-c", f'model_reasoning_effort="{normalized}"']


def diagnose_codex_cli(cfg, role: str, *, check_login: bool = False) -> dict:
    """Return bounded diagnostics without exposing credential material."""
    backend = cfg.backend(role)
    executable = _find_codex(cfg, role)
    result = {
        "transport": "codex_cli",
        "executable_found": bool(executable),
        "version_ok": False,
        "login_checked": bool(check_login),
        "subscription_auth": None,
        "detail": "",
    }
    if not executable:
        result["detail"] = "Codex CLI was not found"
        return result
    version_ok, detail = _check_minimum_version(executable, backend)
    result["version_ok"] = version_ok
    if not version_ok:
        result["detail"] = mask_secrets(detail)[:500]
        return result
    if not check_login:
        result["detail"] = "Codex CLI found; login not checked"
        return result

    auth_mode = str(backend.get("auth_mode") or "existing").strip().lower()
    env = _sanitized_child_env(backend.get("pass_env", []), auth_mode=auth_mode)
    rc, stdout, stderr, overflow = _run_bounded(
        [executable, "login", "status"],
        env,
        str(Path.cwd()),
        timeout=min(30, cfg.timeout(role)),
        stdout_cap=256 << 10,
        stderr_cap=256 << 10,
    )
    if rc is None:
        result["detail"] = "Codex login status could not be started"
        return result
    if overflow:
        result["detail"] = "Codex login status output exceeded safety limits"
        return result
    text = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
    normalized = text.casefold()
    subscription = rc == 0 and re.search(r"(?m)^\s*logged\s+in\s+using\s+chatgpt\b", normalized) is not None
    result["subscription_auth"] = subscription if auth_mode == "chatgpt" else None
    if rc != 0:
        result["detail"] = mask_error(f"Codex login status failed: {text[-300:]}")
    elif auth_mode == "chatgpt" and not subscription:
        result["detail"] = "Codex is not confirmed as signed in with ChatGPT"
    else:
        result["detail"] = "Codex login is available"
    return result


def run_codex_cli(role: str, norm, cfg, prior_summary=None, retry_crop=None) -> BackendResult:
    backend = cfg.backend(role)
    model = cfg.model_id(role)
    if not model and not backend.get("allow_cli_default_model", False):
        return BackendResult(
            backend=role,
            ok=False,
            operational_failure=True,
            error=f"Codex CLI {role} requires an explicit model unless allow_cli_default_model is enabled",
        )
    executable = _find_codex(cfg, role)
    if not executable:
        return BackendResult(backend=role, ok=False, operational_failure=True, error="Codex CLI was not found")
    version_ok, version_error = _check_minimum_version(executable, backend)
    if not version_ok:
        return BackendResult(backend=role, ok=False, operational_failure=True, error=version_error)

    images = retry_crop or norm.staged
    if not _images_within_limits(images, cfg):
        return BackendResult(
            backend=role,
            ok=False,
            operational_failure=True,
            error=f"{role} image payload exceeded configured safety limits",
        )
    prompt = build_prompt(
        norm,
        cfg,
        prior_summary=prior_summary,
        backend=role,
        focus="enhanced crop or tiles" if retry_crop else "",
    )
    output_file = norm.job_dir / f"{role}-result.json"
    command = [
        executable,
        "exec",
        "--sandbox",
        "read-only",
        "-c",
        'approval_policy="never"',
        "--skip-git-repo-check",
        "--color",
        "never",
    ]
    try:
        command.extend(_auth_override(str(backend.get("auth_mode") or "existing")))
        command.extend(_reasoning_override(backend.get("reasoning_effort")))
        command.extend(_mandatory_security_overrides())
        command.extend(_safe_extra_args(backend.get("extra_args", []), role))
    except ValueError as exc:
        return BackendResult(backend=role, ok=False, operational_failure=True, error=str(exc))
    if model:
        command += ["--model", model]
    for image in images:
        command += ["--image", str(image)]
    command += [
        "--output-schema",
        str(cfg.schema_path),
        "--output-last-message",
        str(output_file),
        "-",
    ]
    prompt_bytes = prompt.encode("utf-8")
    if len(prompt_bytes) > _MAX_PROMPT_BYTES:
        return BackendResult(
            backend=role,
            ok=False,
            operational_failure=True,
            error=f"Codex CLI {role} prompt exceeded the 128 KiB safety limit",
        )

    auth_mode = str(backend.get("auth_mode") or "existing").strip().lower()
    env = _sanitized_child_env(backend.get("pass_env", []), auth_mode=auth_mode)
    rc, stdout, stderr, overflow = _run_bounded(
        command,
        env,
        str(norm.job_dir),
        timeout=cfg.timeout(role),
        stdout_cap=8 << 20,
        stderr_cap=1 << 20,
        stdin_data=prompt_bytes,
    )
    if rc is None:
        return BackendResult(backend=role, ok=False, operational_failure=True, error="Codex CLI could not be started")
    if overflow:
        return BackendResult(backend=role, ok=False, operational_failure=True, error="Codex CLI output exceeded safety limits")
    if rc != 0:
        detail = stderr.decode("utf-8", errors="replace")[-500:]
        return BackendResult(
            backend=role,
            ok=False,
            operational_failure=True,
            error=mask_error(f"Codex CLI exited with code {rc}: {detail}"),
        )

    text, read_error = _read_cli_result(output_file)
    if read_error:
        return BackendResult(backend=role, ok=False, operational_failure=True, error=read_error)
    if not text:
        text = stdout.decode("utf-8", errors="replace")
    data = extract_json(text)
    if not isinstance(data, dict):
        return BackendResult(
            backend=role,
            ok=False,
            semantic_insufficient=True,
            status="failed",
            error="Codex CLI output was not a JSON object",
            raw={"stdout": mask_error(text[:2000])},
        )

    valid, issues = validate_backend_payload(data, len(images), norm.mode)
    if detect_injection(data):
        valid = False
        issues.append("answer claimed to execute instructions contained in the image")
    # The `codex exec` transcript header reports the model the CLI actually
    # resolved. The model's own payload claim is NOT authoritative (it can be
    # spoofed by the image); the CLI header is the transport-level ground truth.
    transcript = stdout.decode("utf-8", errors="replace")
    resolved_model = None
    header_match = re.search(r"(?m)^model:\s*([A-Za-z0-9._:/-]+)\s*$", transcript)
    if header_match:
        resolved_model = header_match.group(1)
    model_mismatch = bool(model and resolved_model and resolved_model != model)
    if model_mismatch:
        issues.append(f"resolved model {resolved_model} does not match configured model {model}")
    verified_model = resolved_model or model or "codex-cli-default"
    return BackendResult(
        backend=role,
        ok=valid,
        operational_failure=False,
        semantic_insufficient=not valid,
        model_mismatch=model_mismatch,
        status=str(data.get("status", "failed")),
        answer=str(data.get("answer", "")),
        evidence=data.get("evidence", []),
        relevant_text=data.get("relevant_text", []),
        uncertainty=data.get("uncertainty", []),
        confidence=_safe_float(data.get("confidence")),
        verified_model=verified_model,
        raw=mask_tree(data),
        error="; ".join(issues),
    )


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _read_cli_result(path: Path) -> tuple[str, str]:
    path = Path(path)
    try:
        if _is_link_or_reparse(path):
            return "", "Codex CLI result file exceeded safety limits or was indirect"
        before = path.lstat()
    except FileNotFoundError:
        return "", ""
    except OSError:
        return "", "Codex CLI result file could not be read safely"

    if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > _MAX_CLI_RESULT_BYTES:
        return "", "Codex CLI result file exceeded safety limits or was indirect"

    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                return "", "Codex CLI result file exceeded safety limits or was indirect"
            data = handle.read(_MAX_CLI_RESULT_BYTES + 1)
            after_open = os.fstat(handle.fileno())
        after = path.lstat()
    except OSError:
        return "", "Codex CLI result file could not be read safely"

    changed = (
        len(data) > _MAX_CLI_RESULT_BYTES
        or _is_link_or_reparse(path)
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        or (opened.st_dev, opened.st_ino) != (after_open.st_dev, after_open.st_ino)
        or (after_open.st_dev, after_open.st_ino) != (after.st_dev, after.st_ino)
        or before.st_size != after_open.st_size
        or after_open.st_size != after.st_size
        or getattr(before, "st_mtime_ns", None) != getattr(after_open, "st_mtime_ns", None)
        or getattr(after_open, "st_mtime_ns", None) != getattr(after, "st_mtime_ns", None)
    )
    if changed:
        return "", "Codex CLI result file changed during read or exceeded safety limits"
    try:
        return data.decode("utf-8"), ""
    except UnicodeError:
        return "", "Codex CLI result file was not valid UTF-8"


def _kill_process_tree(process) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        elif os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        else:
            process.kill()
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _run_bounded(cmd, env, cwd, timeout, stdout_cap, stderr_cap, stdin_data: bytes | None = None):
    """Run a child process with hard timeout and bounded stdin/stdout/stderr."""
    popen_kwargs = {
        "cwd": cwd,
        "env": env,
        "stdin": subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    elif os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        process = subprocess.Popen(cmd, **popen_kwargs)
    except OSError:
        return None, b"", b"", False

    overflow = threading.Event()
    sinks = {"out": [], "err": []}
    caps = {"out": stdout_cap, "err": stderr_cap}

    def _pump(stream, name):
        assert stream is not None
        total = 0
        while True:
            reader = getattr(stream, "read1", stream.read)
            chunk = reader(65536)
            if not chunk:
                break
            remaining = caps[name] - total
            if remaining <= 0:
                overflow.set()
                _kill_process_tree(process)
                break
            sinks[name].append(chunk[:remaining])
            total += min(len(chunk), remaining)
            if len(chunk) > remaining:
                overflow.set()
                _kill_process_tree(process)
                break

    def _feed_stdin():
        stream = process.stdin
        if stream is None:
            return
        try:
            stream.write(stdin_data or b"")
            stream.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    threads = [
        threading.Thread(target=_pump, args=(process.stdout, "out"), daemon=True),
        threading.Thread(target=_pump, args=(process.stderr, "err"), daemon=True),
    ]
    if stdin_data is not None:
        threads.append(threading.Thread(target=_feed_stdin, daemon=True))
    for thread in threads:
        thread.start()
    try:
        rc = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                pass
            process.wait()
        rc = -1
    finally:
        for thread in threads:
            thread.join(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
    return rc, b"".join(sinks["out"]), b"".join(sinks["err"]), overflow.is_set()



def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default
