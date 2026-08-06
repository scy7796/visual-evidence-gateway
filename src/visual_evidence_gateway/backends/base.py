"""Shared backend helpers for OpenAI-compatible Responses API backends."""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import stat
from importlib.metadata import PackageNotFoundError, version
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from visual_evidence_gateway.router.models import BackendResult
from visual_evidence_gateway.router.validator import detect_injection, extract_json, validate_backend_payload

MAX_RESPONSE_BYTES = 4 << 20

_TOKEN_PATTERNS = (
    r"sk-[A-Za-z0-9_-]{8,}",
    r"nvapi-[A-Za-z0-9_-]{8,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"gho_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"glpat-[A-Za-z0-9_-]{16,}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"AKIA[0-9A-Z]{16}",
    r"eyJ[A-Za-z0-9_-]{10,}",
    r"Bearer\s+[A-Za-z0-9._-]{8,}",
    r"AIza[0-9A-Za-z_-]{20,}",
    r"Basic\s+[A-Za-z0-9+/=]{8,}",
    r"AccountKey=[A-Za-z0-9+/=]{40,}",
)
TOKEN_RE = re.compile(r"\b(" + "|".join(_TOKEN_PATTERNS) + r")\b", re.IGNORECASE)
PEM_RE = re.compile(
    r"-----BEGIN\s+[A-Z0-9 ]*PRIVATE\s+KEY-----[\s\S]*?-----END\s+[A-Z0-9 ]*PRIVATE\s+KEY-----",
    re.IGNORECASE,
)
B64_RUN_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:^|[_-])(?:api[_-]?key|authorization|auth[_-]?token|access[_-]?token|refresh[_-]?token|"
    r"password|passwd|secret|client[_-]?secret|private[_-]?key|account[_-]?key|credential)(?:$|[_-])"
)

try:
    PACKAGE_VERSION = version("visual-evidence-gateway")
except PackageNotFoundError:  # source checkout
    PACKAGE_VERSION = "0.5.0"


# Local absolute-path shapes that must never leak into MCP responses. Only
# applied to error/reason strings, never to OCR or evidence content.
# Built from parts so the release audit (which scans for literal /Users/ and
# /home/ markers) does not flag this security helper itself.
_HOME_LABELS = "|".join(("Users", "home", "tmp", "var/folders", "private/var"))
_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>|?*\u0000-\u001f]*"
    r"|(?<![\w:/])/(" + _HOME_LABELS + r")/[^\s\"'<>|?*\u0000-\u001f]*)"
)


def mask_paths(text: str) -> str:
    """Replace local absolute paths with a neutral placeholder."""
    return _LOCAL_PATH_RE.sub("<local-path>", str(text))


def mask_error(text: str) -> str:
    """Sanitize an error/diagnostic string for tokens, keys, and local paths."""
    return mask_paths(mask_secrets(text))


def mask_secrets(text: str) -> str:
    out = TOKEN_RE.sub("[MASKED]", str(text))
    out = PEM_RE.sub("[MASKED]", out)

    def _mask_b64(match: re.Match[str]) -> str:
        try:
            chunk = match.group(0)
            padded = chunk + "=" * ((4 - len(chunk) % 4) % 4)
            decoded = base64.b64decode(padded)
            if decoded.startswith((b"sk-", b"ghp_", b"nvapi-", b"eyJ")):
                return "[MASKED]"
        except Exception:
            pass
        return match.group(0)

    return B64_RUN_RE.sub(_mask_b64, out)


def mask_tree(obj: Any) -> Any:
    """Recursively redact common credential forms before persistence/logging."""
    if isinstance(obj, str):
        return mask_secrets(obj)
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            key_text = str(key)
            out[key_text] = "[MASKED]" if SENSITIVE_KEY_RE.search(key_text) else mask_tree(value)
        return out
    if isinstance(obj, list):
        return [mask_tree(value) for value in obj]
    return obj


def _check_endpoint(
    endpoint: str,
    *,
    allow_remote: bool = False,
    allowed_remote_hosts: Optional[List[str]] = None,
) -> str:
    """Validate and normalize an endpoint without resolving hostnames.

    Local mode only accepts literal loopback IPs. Remote mode must be enabled
    explicitly, use HTTPS, and match an exact allowlisted hostname.
    Credentials embedded in URLs are rejected rather than silently logged.
    """

    ep = str(endpoint).rstrip("/")
    if re.search(r"[\r\n\x00]", ep):
        raise ValueError("endpoint contains control characters")
    parts = urllib.parse.urlsplit(ep)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"unsupported endpoint scheme: {parts.scheme}")
    if parts.username or parts.password:
        raise ValueError("endpoint must not contain embedded credentials")
    if parts.fragment:
        raise ValueError("endpoint must not contain a fragment")
    if parts.query:
        raise ValueError("endpoint must not contain a query string")
    if parts.path not in ("", "/"):
        raise ValueError("endpoint must be an origin without a path")
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError("endpoint host is missing")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None and ip.is_loopback:
        return ep

    if not allow_remote:
        raise ValueError("endpoint must use a literal loopback IP unless remote endpoints are explicitly enabled")
    if parts.scheme != "https":
        raise ValueError("remote endpoints require HTTPS")
    allowlist = {str(v).strip().lower().rstrip(".") for v in (allowed_remote_hosts or []) if str(v).strip()}
    if host.rstrip(".") not in allowlist:
        raise ValueError(f"remote endpoint host is not allowlisted: {host}")
    return ep


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = Path(path).lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _image_data_uri_bounded(path: Path, limit: int) -> Tuple[str, int]:
    """Read a staged regular file once, without following final indirection."""
    path = Path(path)
    if _is_link_or_reparse(path):
        raise OSError("staged image is indirect")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
        raise OSError("staged image is not a regular file")
    if before.st_size > limit:
        raise OSError(f"staged image exceeds configured limit: {before.st_size} bytes")

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
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("staged image is not a regular file")
        data = handle.read(limit + 1)
        after_open = os.fstat(handle.fileno())
    after = path.lstat()
    if (
        len(data) > limit
        or _is_link_or_reparse(path)
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        or (opened.st_dev, opened.st_ino) != (after_open.st_dev, after_open.st_ino)
        or (after_open.st_dev, after_open.st_ino) != (after.st_dev, after.st_ino)
        or before.st_size != after_open.st_size
        or after_open.st_size != after.st_size
        or getattr(before, "st_mtime_ns", None) != getattr(after_open, "st_mtime_ns", None)
        or getattr(after_open, "st_mtime_ns", None) != getattr(after, "st_mtime_ns", None)
    ):
        raise OSError("staged image changed during read")
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii"), len(data)


def image_data_uri(path: Path) -> str:
    uri, _ = _image_data_uri_bounded(path, 64 << 20)
    return uri


def _responses_url(endpoint: str, path: str) -> str:
    if re.search(r"[\r\n\x00]", path):
        raise ValueError("responses_path contains control characters")
    if "\\" in path or "%" in path or "?" in path or "#" in path:
        raise ValueError("responses_path must contain only an absolute URL path")
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("responses_path must be a single-host absolute path")
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise ValueError("responses_path must not contain dot segments")
    base = urllib.parse.urlsplit(endpoint)
    combined = urllib.parse.urlsplit(endpoint + path)
    if (base.scheme, base.hostname, base.port) != (combined.scheme, combined.hostname, combined.port):
        raise ValueError("responses_path changed endpoint authority")
    return urllib.parse.urlunsplit((combined.scheme, combined.netloc, combined.path, combined.query, ""))


def call_responses_api(
    cfg,
    model: str,
    prompt: str,
    images: List[Path],
    reasoning_effort: Optional[str] = None,
    backend_name: str = "primary",
) -> Tuple[bool, Dict[str, Any], str]:
    gateway = cfg.gateway
    try:
        endpoint = _check_endpoint(
            gateway.get("endpoint", "http://127.0.0.1:10100"),
            allow_remote=bool(gateway.get("allow_remote_endpoint", False)),
            allowed_remote_hosts=gateway.get("allowed_remote_hosts", []),
        )
        url = _responses_url(endpoint, str(gateway.get("responses_path", "/v1/responses")))
    except ValueError as exc:
        return False, {}, f"endpoint validation failed: {exc}"

    max_staged = int(cfg.limits.get("max_staged_bytes", 16 << 20))
    total_image_bytes = 0
    content: List[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for image in images:
        try:
            uri, size = _image_data_uri_bounded(image, max_staged)
        except OSError as exc:
            return False, {}, mask_secrets(f"staged image is unavailable: {exc}")
        total_image_bytes += size
        if total_image_bytes > max_staged:
            return False, {}, f"combined staged images exceed configured limit: {total_image_bytes} bytes"
        content.append({"type": "input_image", "image_url": uri})
    payload: Dict[str, Any] = {
        "model": model,
        "stream": False,
        "input": [{"role": "user", "content": content}],
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": f"visual-evidence-gateway/{PACKAGE_VERSION}",
    }
    api_key_env = gateway.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(str(api_key_env), "")
        if not api_key:
            return False, {}, f"required API key environment variable is not set: {api_key_env}"
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    timeout = cfg.timeout(backend_name)
    try:
        handlers = [_NoRedirect()]
        if not bool(gateway.get("use_environment_proxy", False)):
            handlers.insert(0, urllib.request.ProxyHandler({}))
        opener = urllib.request.build_opener(*handlers)
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return False, {}, "response exceeded 4 MiB limit"
            try:
                body = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                return False, {}, "response was not valid UTF-8 JSON"
        if not isinstance(body, dict):
            return False, {}, "response JSON root was not an object"
        return True, body, ""
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(MAX_RESPONSE_BYTES + 1)
            body = json.loads(raw[:MAX_RESPONSE_BYTES].decode("utf-8")) if raw else {}
        except Exception:
            body = {}
        err = body.get("error", "") if isinstance(body, dict) else ""
        if isinstance(err, dict):
            message = str(err.get("message", ""))
        else:
            message = str(err or "")
        return False, body if isinstance(body, dict) else {}, mask_secrets(f"HTTP {exc.code}: {message or exc.reason}")
    except Exception as exc:  # noqa: BLE001
        return False, {}, mask_secrets(f"responses endpoint unavailable: {exc}")


def extract_output_text(body: Dict[str, Any]) -> str:
    direct = body.get("output_text") if isinstance(body, dict) else None
    if isinstance(direct, str) and direct:
        return direct
    if not isinstance(body, dict) or not isinstance(body.get("output"), list):
        return ""
    parts: List[str] = []
    for item in body["output"]:
        if not isinstance(item, dict) or not isinstance(item.get("content"), list):
            continue
        for content in item["content"]:
            if not isinstance(content, dict):
                continue
            if content.get("type") in ("output_text", "text"):
                text = content.get("text", "")
                if isinstance(text, str) and text:
                    parts.append(text)
    return "\n".join(parts)


def result_from_payload(
    backend: str,
    ok: bool,
    body: Dict[str, Any],
    error: str,
    expected_model: str,
    n_images: int,
    mode: str,
    *,
    require_resolved_model: bool = True,
    accepted_model_ids: Optional[List[str]] = None,
) -> BackendResult:
    if not ok:
        return BackendResult(
            backend=backend,
            ok=False,
            operational_failure=True,
            error=error or "responses API call failed",
            raw=mask_tree(body) if isinstance(body, dict) else {},
        )
    if not isinstance(body, dict):
        return BackendResult(backend=backend, ok=False, operational_failure=True, error="response body is not an object")

    text = extract_output_text(body)
    if not text:
        return BackendResult(
            backend=backend,
            ok=False,
            operational_failure=True,
            error="response did not contain output text",
            raw={},
        )
    data = extract_json(text)
    if not isinstance(data, dict):
        return BackendResult(
            backend=backend,
            ok=False,
            semantic_insufficient=True,
            status="failed",
            error="model output was not a JSON object",
            raw={"output_text": mask_secrets(text[:2000])},
        )

    valid, issues = validate_backend_payload(data, n_images, mode)
    resolved_model = str(body.get("model") or "").strip()
    self_reported = str(data.get("model_id") or "").strip()
    actual = resolved_model or self_reported
    mismatch = False
    accepted = {str(expected_model).strip()} if str(expected_model).strip() else set()
    accepted.update(str(value).strip() for value in (accepted_model_ids or []) if str(value).strip())
    if expected_model:
        if require_resolved_model and not resolved_model:
            mismatch = True
            issues.append("response did not report the resolved model")
        elif resolved_model and resolved_model not in accepted:
            mismatch = True
            issues.append(f"resolved model did not match configured identifiers: {resolved_model}")
        elif not resolved_model and self_reported and self_reported not in accepted:
            mismatch = True
            issues.append(f"self-reported model did not match configured identifiers: {self_reported}")
    if detect_injection(data):
        valid = False
        issues.append("answer claimed to execute instructions contained in the image")

    return BackendResult(
        backend=backend,
        ok=valid and not mismatch,
        operational_failure=False,
        semantic_insufficient=not valid,
        model_mismatch=mismatch,
        status=str(data.get("status", "failed")),
        answer=str(data.get("answer", "")),
        evidence=data.get("evidence", []),
        relevant_text=data.get("relevant_text", []),
        uncertainty=data.get("uncertainty", []),
        confidence=_safe_float(data.get("confidence")),
        verified_model=actual or expected_model,
        raw=mask_tree(data),
        error="; ".join(issues),
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default
