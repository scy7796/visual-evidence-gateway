"""Configuration loading and path policy for Visual Evidence Gateway.

Runtime configuration is user-owned and lives outside the installed package.
The package never ships mutable health state, credentials, machine-specific
paths, or provider account details.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

APP_NAME = "visual-evidence-gateway"
CONFIG_ENV = "VISUAL_EVIDENCE_GATEWAY_CONFIG"
MAX_CONFIG_BYTES = 1 << 20


def _is_link_or_reparse(path: Path) -> bool:
    try:
        st = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _has_path_indirection(path: Path) -> bool:
    """Return true when an existing component is a symlink/junction/reparse point."""
    absolute = Path(os.path.abspath(str(path)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.exists() or current.is_symlink():
            if _is_link_or_reparse(current):
                return True
    return False


def _absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(str(path)))


def _is_filesystem_root(path: Path) -> bool:
    anchor = path.anchor
    return bool(anchor) and path == Path(anchor)


def _user_config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def _user_cache_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / APP_NAME


def default_config_path() -> Path:
    return _user_config_dir() / "config.yaml"


def default_health_path() -> Path:
    return _user_config_dir() / "health.json"


DEFAULTS: Dict[str, Any] = {
    "policy_version": 2,
    "prompt_version": 3,
    "project_root": None,
    "cache_dir": None,
    "health_file": None,
    "cache": {
        "store_raw": False,
        "store_full_text": False,
        "expose_local_refs": False,
    },
    "gateway": {
        "endpoint": "http://127.0.0.1:10100",
        "responses_path": "/v1/responses",
        "timeout_sec": 180,
        "api_key_env": None,
        "allow_remote_endpoint": False,
        "allowed_remote_hosts": [],
        "require_resolved_model": True,
        "use_environment_proxy": False,
    },
    "backends": {
        "primary": {
            # Subscription-first public default. Authentication remains in the
            # operator-owned Codex credential store; no credential is packaged.
            "enabled": True,
            "healthy": False,
            "require_probe": False,
            "model": "gpt-5.6-luna",
            "accepted_model_ids": [],
            "reasoning_effort": "medium",
            "via": "codex_cli",
            "command": "codex",
            "auth_mode": "chatgpt",
            "min_cli_version": "0.146.0",
            "extra_args": ["--ephemeral", "--ignore-user-config"],
            "pass_env": [],
            "allow_cli_default_model": False,
        },
        "verifier": {
            "enabled": False,
            "healthy": False,
            "require_probe": True,
            "model": "",
            "accepted_model_ids": [],
            "reasoning_effort": "medium",
            "via": "responses_api",
            "command": "codex",
            "auth_mode": "existing",
            "min_cli_version": "",
            "extra_args": [],
            "pass_env": [],
            "allow_cli_default_model": False,
        },
        "fallback": {
            "enabled": False,
            "healthy": False,
            "require_probe": True,
            "model": "",
            "accepted_model_ids": [],
            "reasoning_effort": "medium",
            "vision_verified": False,
            "via": "responses_api",
            "command": "codex",
            "auth_mode": "existing",
            "min_cli_version": "",
            "extra_args": [],
            "pass_env": [],
            "allow_cli_default_model": False,
        },
    },
    # Tokens are expanded at load time. Public defaults intentionally avoid a
    # user's whole home directory or the system-wide temporary directory.
    # Additional roots must be granted explicitly by the operator.
    "allowed_roots": ["{cwd}"],
    "forbidden_roots": [
        "{config_dir}",
        "{cache_dir}",
        "{home}/.ssh",
        "{home}/.aws",
        "{home}/.kube",
        "{home}/.gnupg",
        "{home}/.docker",
        "{home}/.config/gcloud",
        "{home}/.azure",
        "{home}/.npmrc",
        "{home}/.pypirc",
        "{home}/.git-credentials",
    ],
    "limits": {
        "max_images": 4,
        "max_image_bytes": 20 * 1024 * 1024,
        "max_side_px": 8000,
        "max_pixels": 64_000_000,
        "max_staged_bytes": 16 * 1024 * 1024,
    },
    "prompt_settings": {
        "answer_max_cjk": 120,
        "answer_max_words": 100,
        "max_evidence": 5,
        "max_relevant_lines": 20,
        "max_uncertainty": 3,
        "semantic_confidence_threshold": 0.72,
        "retry_crop": True,
    },
    "budget_tokens": {"normal": 350, "critical": 600},
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def plugin_root_env() -> Path:
    """Compatibility alias retained for callers from the pre-package layout."""
    return package_root()


def _read_mapping(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    if not path.is_file():
        raise ValueError(f"configuration path is not a regular file: {path}")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_CONFIG_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"configuration file could not be read: {path}") from exc
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError(f"configuration file exceeds 1 MiB: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"configuration file is not valid UTF-8: {path}") from exc
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read YAML configuration")
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"configuration root must be an object: {path}")
    return data


def _merge_health(data: Dict[str, Any], health_path: Path, cfg: "Config") -> Dict[str, Any]:
    # Health state is mutable and must never be trusted through filesystem
    # indirection. Unsafe state is ignored, which keeps every probe gate closed.
    if _has_path_indirection(health_path):
        return data
    try:
        health = _read_mapping(health_path) if health_path.exists() else {}
    except (ValueError, RuntimeError, OSError):
        # Mutable probe state must never make the server unavailable. Invalid,
        # oversized, or unreadable state simply leaves every probe gate closed.
        return data
    states = health.get("backends", {}) if isinstance(health, dict) else {}
    if not isinstance(states, dict):
        return data
    merged = copy.deepcopy(data)
    for name, state in states.items():
        if name not in merged.get("backends", {}) or not isinstance(state, dict):
            continue
        # Probe readiness is valid only for the exact transport/model/prompt
        # configuration that produced it. Static config cannot self-assert
        # health, and stale health from a previous model or endpoint is ignored.
        if state.get("config_fingerprint") != cfg.probe_fingerprint(name):
            continue
        allowed: Dict[str, Any] = {}
        for key in ("healthy", "vision_verified"):
            if type(state.get(key)) is bool:
                allowed[key] = state[key]
        for key in ("detail", "checked_at"):
            if isinstance(state.get(key), str):
                allowed[key] = state[key][:1000]
        elapsed_ms = state.get("elapsed_ms")
        if (
            not isinstance(elapsed_ms, bool)
            and isinstance(elapsed_ms, (int, float))
            and 0 <= elapsed_ms <= 3_600_000
        ):
            allowed["elapsed_ms"] = round(float(elapsed_ms), 1)
        merged["backends"][name].update(allowed)
    return merged


def _runtime_path(raw: Any, selected: Path, *, project_root: Any = None) -> Path:
    text = str(raw)
    project_root_text = str(project_root) if project_root is not None else None
    replacements = {
        "{cwd}": str(Path.cwd()),
        "{home}": str(Path.home()),
        "{temp}": tempfile.gettempdir(),
        "{config_dir}": str(_user_config_dir()),
        "{cache_dir}": str(_user_cache_dir()),
        "{project_root}": project_root_text or str(Path.cwd()),
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    text = os.path.expandvars(os.path.expanduser(text))
    path = Path(text)
    if not path.is_absolute():
        path = selected.parent / path
    return _absolute_without_resolving(path)


def _reset_probe_state(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove mutable readiness assertions from static operator configuration."""
    cleaned = copy.deepcopy(data)
    backends = cleaned.get("backends", {})
    if isinstance(backends, dict):
        for backend in backends.values():
            if isinstance(backend, dict):
                backend["healthy"] = False
                backend["vision_verified"] = False
                backend.pop("detail", None)
                backend.pop("checked_at", None)
                backend.pop("elapsed_ms", None)
    return cleaned


def load_config(plugin_root: Optional[Path] = None, config_path: Optional[Path] = None) -> "Config":
    # plugin_root is retained for test compatibility and resource resolution;
    # configuration itself is no longer read from the package directory.
    root = Path(plugin_root) if plugin_root else package_root()
    selected = _absolute_without_resolving(
        Path(config_path) if config_path else Path(os.environ.get(CONFIG_ENV, default_config_path()))
    )
    configured = _deep_merge(DEFAULTS, _read_mapping(selected) if selected.exists() else {})
    health_raw = configured.get("health_file")
    health_path = (
        _runtime_path(health_raw, selected, project_root=configured.get("project_root"))
        if health_raw
        else _absolute_without_resolving(default_health_path())
    )
    if health_path == selected:
        raise ValueError("health_file must not overwrite the configuration file")
    data = _reset_probe_state(configured)
    base_cfg = Config(data, root, config_path=selected, health_path=health_path)
    merged = _merge_health(data, health_path, base_cfg)
    return Config(merged, root, config_path=selected, health_path=health_path)


def _require_bool(mapping: Dict[str, Any], key: str, label: str) -> None:
    if key in mapping and type(mapping[key]) is not bool:
        raise ValueError(f"{label}.{key} must be a boolean")


def _require_string(mapping: Dict[str, Any], key: str, label: str, *, allow_none: bool = False) -> None:
    value = mapping.get(key)
    if value is None and allow_none:
        return
    if key in mapping and not isinstance(value, str):
        raise ValueError(f"{label}.{key} must be a string")


def _reject_unknown(mapping: Dict[str, Any], allowed: set[str], label: str) -> None:
    extra = sorted(str(key) for key in set(mapping) - allowed)
    if extra:
        raise ValueError(f"{label} contains unknown fields: {', '.join(extra)}")


class Config:
    """Validated runtime configuration with typed accessors."""

    def __init__(
        self,
        data: Dict[str, Any],
        plugin_root: Path,
        *,
        config_path: Optional[Path] = None,
        health_path: Optional[Path] = None,
    ):
        if not isinstance(data, dict):
            raise ValueError("configuration root must be an object")
        _reject_unknown(
            data,
            {
                "policy_version", "prompt_version", "project_root", "cache_dir", "health_file",
                "cache", "gateway", "backends", "allowed_roots", "forbidden_roots", "limits",
                "prompt_settings", "budget_tokens",
            },
            "configuration",
        )
        self.data = copy.deepcopy(data)
        self.plugin_root = Path(plugin_root).resolve()
        self.config_path = Path(config_path).resolve() if config_path else None
        self.health_path = (
            _absolute_without_resolving(Path(health_path))
            if health_path
            else _absolute_without_resolving(default_health_path())
        )
        policy_version = data.get("policy_version", 2)
        prompt_version = data.get("prompt_version", 3)
        if isinstance(policy_version, bool) or not isinstance(policy_version, int) or not 1 <= policy_version <= 1_000_000:
            raise ValueError("policy_version must be a positive bounded integer")
        if isinstance(prompt_version, bool) or not isinstance(prompt_version, int) or not 1 <= prompt_version <= 1_000_000:
            raise ValueError("prompt_version must be a positive bounded integer")
        self.policy_version = policy_version
        self.prompt_version = prompt_version

        project = data.get("project_root")
        self.project_root = self._expand_path(project) if project else Path.cwd().resolve()

        cache = data.get("cache_dir")
        self.cache_dir = (
            self._expand_path(cache, resolve=False)
            if cache
            else _absolute_without_resolving(_user_cache_dir() / "cache")
        )

        gateway = data.get("gateway", {})
        backends = data.get("backends", {})
        if not isinstance(gateway, dict):
            raise ValueError("gateway must be an object")
        if not isinstance(backends, dict):
            raise ValueError("backends must be an object")
        _reject_unknown(
            gateway,
            {
                "endpoint", "responses_path", "timeout_sec", "api_key_env", "allow_remote_endpoint",
                "allowed_remote_hosts", "require_resolved_model", "use_environment_proxy",
            },
            "gateway",
        )
        _reject_unknown(backends, {"primary", "verifier", "fallback"}, "backends")
        self.gateway = copy.deepcopy(gateway)
        self.backends = copy.deepcopy(backends)
        cache_settings = data.get("cache", {})
        if not isinstance(cache_settings, dict):
            raise ValueError("cache must be an object")
        _reject_unknown(cache_settings, {"store_raw", "store_full_text", "expose_local_refs"}, "cache")
        self.cache_settings = copy.deepcopy(cache_settings)

        for key in ("allow_remote_endpoint", "require_resolved_model", "use_environment_proxy"):
            _require_bool(self.gateway, key, "gateway")
        for key in ("endpoint", "responses_path"):
            _require_string(self.gateway, key, "gateway")
            if len(str(self.gateway.get(key, ""))) > 2048:
                raise ValueError(f"gateway.{key} is too long")
        _require_string(self.gateway, "api_key_env", "gateway", allow_none=True)
        api_key_env = self.gateway.get("api_key_env")
        if api_key_env is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env):
            raise ValueError("gateway.api_key_env must be an environment variable name")
        remote_hosts = self.gateway.get("allowed_remote_hosts", [])
        if not isinstance(remote_hosts, list) or not all(isinstance(v, str) for v in remote_hosts):
            raise ValueError("gateway.allowed_remote_hosts must be an array of hostnames")
        if len(remote_hosts) > 100:
            raise ValueError("gateway.allowed_remote_hosts has too many entries")
        if any(
            not value.strip()
            or len(value) > 253
            or re.search(r"[\r\n\x00\s/@*?]", value)
            or value.startswith("[")
            or value.endswith("]")
            for value in remote_hosts
        ):
            raise ValueError("gateway.allowed_remote_hosts contains an invalid hostname")
        gateway_timeout = self.gateway.get("timeout_sec", 180)
        if (
            isinstance(gateway_timeout, bool)
            or not isinstance(gateway_timeout, (int, float))
            or not 0 < gateway_timeout <= 3600
        ):
            raise ValueError("gateway.timeout_sec must be between 0 and 3600 seconds")

        for key in ("store_raw", "store_full_text", "expose_local_refs"):
            _require_bool(self.cache_settings, key, "cache")

        for name in ("primary", "verifier", "fallback"):
            backend = self.backends.get(name)
            if not isinstance(backend, dict):
                raise ValueError(f"backends.{name} must be an object")
            allowed_backend = {
                "enabled", "healthy", "require_probe", "model", "accepted_model_ids", "reasoning_effort",
                "via", "timeout_sec", "vision_verified", "detail", "checked_at", "elapsed_ms",
                "command", "auth_mode", "min_cli_version", "extra_args", "pass_env",
                "allow_cli_default_model",
            }
            _reject_unknown(backend, allowed_backend, f"backends.{name}")
            for key in ("enabled", "healthy", "require_probe"):
                _require_bool(backend, key, f"backends.{name}")
            if "vision_verified" in backend:
                _require_bool(backend, "vision_verified", f"backends.{name}")
            elapsed_ms = backend.get("elapsed_ms")
            if elapsed_ms is not None and (
                isinstance(elapsed_ms, bool)
                or not isinstance(elapsed_ms, (int, float))
                or not 0 <= elapsed_ms <= 3_600_000
            ):
                raise ValueError(f"backends.{name}.elapsed_ms must be between 0 and 3600000")
            if "allow_cli_default_model" in backend:
                _require_bool(backend, "allow_cli_default_model", f"backends.{name}")
            for key in ("model", "via", "command", "auth_mode", "min_cli_version"):
                _require_string(backend, key, f"backends.{name}")
            _require_string(backend, "reasoning_effort", f"backends.{name}", allow_none=True)
            reasoning_effort = backend.get("reasoning_effort")
            if reasoning_effort not in (None, "") and str(reasoning_effort).strip().lower() not in {
                "none", "low", "medium", "high", "xhigh", "max"
            }:
                raise ValueError(
                    f"backends.{name}.reasoning_effort must be none, low, medium, high, xhigh, or max"
                )
            for key in ("model", "via", "reasoning_effort", "command", "auth_mode", "min_cli_version"):
                value = backend.get(key)
                if isinstance(value, str) and (len(value) > 512 or re.search(r"[\r\n\x00]", value)):
                    raise ValueError(f"backends.{name}.{key} is invalid or too long")
            accepted = backend.get("accepted_model_ids", [])
            if not isinstance(accepted, list) or not all(isinstance(v, str) and v.strip() for v in accepted):
                raise ValueError(f"backends.{name}.accepted_model_ids must be a string array")
            if len(accepted) > 50 or any(len(v) > 512 or re.search(r"[\r\n\x00]", v) for v in accepted):
                raise ValueError(f"backends.{name}.accepted_model_ids is too large or invalid")
            if "timeout_sec" in backend:
                timeout = backend["timeout_sec"]
                if (
                    isinstance(timeout, bool)
                    or not isinstance(timeout, (int, float))
                    or not 0 < timeout <= 3600
                ):
                    raise ValueError(f"backends.{name}.timeout_sec must be between 0 and 3600 seconds")

            via = str(backend.get("via", "responses_api")).strip().lower()
            if via not in {"responses_api", "codex_cli"}:
                raise ValueError(f"backends.{name}.via must be responses_api or codex_cli")
            auth_mode = str(backend.get("auth_mode") or "existing").strip().lower()
            if auth_mode not in {"chatgpt", "api", "existing"}:
                raise ValueError(f"backends.{name}.auth_mode must be chatgpt, api, or existing")
            minimum = str(backend.get("min_cli_version") or "").strip()
            if minimum and not re.fullmatch(r"\d+\.\d+\.\d+", minimum):
                raise ValueError(f"backends.{name}.min_cli_version must use MAJOR.MINOR.PATCH")
            for key in ("extra_args", "pass_env"):
                values = backend.get(key, [])
                if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                    raise ValueError(f"backends.{name}.{key} must be a string array")
                if len(values) > 50 or any(
                    len(v) > 512 or "\x00" in v or "\n" in v or "\r" in v for v in values
                ):
                    raise ValueError(f"backends.{name}.{key} is too large or invalid")
            pass_env = backend.get("pass_env", [])
            if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) for value in pass_env):
                raise ValueError(f"backends.{name}.pass_env entries must be environment variable names")
            if auth_mode == "chatgpt":
                forbidden_api_env = {
                    "OPENAI_API_KEY",
                    "OPENAI_BASE_URL",
                    "OPENAI_ORG_ID",
                    "OPENAI_PROJECT_ID",
                    "ANTHROPIC_API_KEY",
                    "GEMINI_API_KEY",
                    "CODEX_API_KEY",
                }
                inherited = sorted(forbidden_api_env.intersection(pass_env))
                if inherited:
                    raise ValueError(
                        f"backends.{name}.pass_env cannot inherit API billing/alternate-provider variables in chatgpt auth mode: "
                        + ", ".join(inherited)
                    )

        allowed = data.get("allowed_roots", [])
        forbidden = data.get("forbidden_roots", [])
        if not isinstance(allowed, list) or not all(isinstance(v, (str, os.PathLike)) for v in allowed):
            raise ValueError("allowed_roots must be an array of paths")
        if not isinstance(forbidden, list) or not all(isinstance(v, (str, os.PathLike)) for v in forbidden):
            raise ValueError("forbidden_roots must be an array of paths")
        if len(allowed) > 100 or len(forbidden) > 200:
            raise ValueError("allowed_roots or forbidden_roots has too many entries")
        if any(len(str(value)) > 4096 or "\x00" in str(value) for value in [*allowed, *forbidden]):
            raise ValueError("allowed_roots or forbidden_roots contains an invalid path")
        self.allowed_roots = [self._expand_path(p) for p in allowed]
        self.forbidden_roots = [self._expand_path(p) for p in forbidden]
        cache_root = self.cache_dir.resolve()
        if cache_root not in self.forbidden_roots:
            self.forbidden_roots.append(cache_root)
        if not self.allowed_roots:
            raise ValueError("allowed_roots must not be empty")
        if any(_is_filesystem_root(path) for path in self.allowed_roots):
            raise ValueError("allowed_roots must not include a filesystem root; choose a narrower project directory")

        limits = data.get("limits", {})
        if not isinstance(limits, dict):
            raise ValueError("limits must be an object")
        _reject_unknown(
            limits,
            {"max_images", "max_image_bytes", "max_side_px", "max_pixels", "max_staged_bytes"},
            "limits",
        )
        for key in ("max_images", "max_image_bytes", "max_side_px", "max_pixels", "max_staged_bytes"):
            value = limits.get(key)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"limits.{key} must be an integer")
            if value <= 0:
                raise ValueError(f"limits.{key} must be positive")
        if limits["max_images"] > 4:
            raise ValueError("limits.max_images must not exceed the public contract of 4")
        if limits["max_image_bytes"] > (64 << 20) or limits["max_staged_bytes"] > (64 << 20):
            raise ValueError("image byte limits must not exceed 64 MiB")
        if limits["max_side_px"] > 32_000 or limits["max_pixels"] > 64_000_000:
            raise ValueError("image dimensions exceed the decoder safety ceiling")
        self.limits = copy.deepcopy(limits)

        prompt_settings = data.get("prompt_settings", {})
        budget_tokens = data.get("budget_tokens", {})
        if not isinstance(prompt_settings, dict):
            raise ValueError("prompt_settings must be an object")
        if not isinstance(budget_tokens, dict):
            raise ValueError("budget_tokens must be an object")
        _reject_unknown(
            prompt_settings,
            {
                "answer_max_cjk", "answer_max_words", "max_evidence", "max_relevant_lines",
                "max_uncertainty", "semantic_confidence_threshold", "retry_crop",
            },
            "prompt_settings",
        )
        _reject_unknown(budget_tokens, {"normal", "critical"}, "budget_tokens")
        self.prompt_settings = copy.deepcopy(prompt_settings)
        self.budget_tokens = copy.deepcopy(budget_tokens)
        _require_bool(self.prompt_settings, "retry_crop", "prompt_settings")
        prompt_bounds = {
            "answer_max_cjk": (20, 100_000),
            "answer_max_words": (20, 100_000),
            "max_evidence": (1, 5),
            "max_relevant_lines": (1, 100),
            "max_uncertainty": (1, 3),
        }
        for key, (minimum, maximum) in prompt_bounds.items():
            value = self.prompt_settings.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(
                    f"prompt_settings.{key} must be an integer between {minimum} and {maximum}"
                )
        threshold = self.prompt_settings.get("semantic_confidence_threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
            raise ValueError("prompt_settings.semantic_confidence_threshold must be between 0 and 1")
        for key in ("normal", "critical"):
            value = self.budget_tokens.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 10_000:
                raise ValueError(f"budget_tokens.{key} must be an integer between 100 and 10000")

        self.prompt_dir = package_root() / "prompts"
        self.schema_path = package_root() / "schemas" / "vision-result.schema.json"

    def _expand_path(self, raw: Any, *, resolve: bool = True) -> Path:
        text = str(raw)
        replacements = {
            "{cwd}": str(Path.cwd()),
            "{home}": str(Path.home()),
            "{temp}": tempfile.gettempdir(),
            "{config_dir}": str(_user_config_dir()),
            "{cache_dir}": str(_user_cache_dir()),
            "{project_root}": str(getattr(self, "project_root", Path.cwd())),
        }
        for token, value in replacements.items():
            text = text.replace(token, value)
        text = os.path.expandvars(os.path.expanduser(text))
        path = Path(text)
        if not path.is_absolute():
            base = self.config_path.parent if self.config_path else self.plugin_root
            path = base / path
        absolute = _absolute_without_resolving(path)
        return absolute.resolve() if resolve else absolute

    def probe_fingerprint(self, name: str) -> str:
        """Bind mutable probe health to one exact backend configuration."""
        backend = self.backend(name)
        payload = {
            "format": 1,
            "role": name,
            "policy_version": self.policy_version,
            "prompt_version": self.prompt_version,
            "gateway": {
                key: self.gateway.get(key)
                for key in (
                    "endpoint", "responses_path", "timeout_sec", "api_key_env",
                    "require_resolved_model", "allow_remote_endpoint", "allowed_remote_hosts",
                    "use_environment_proxy",
                )
            },
            "backend": {
                key: backend.get(key)
                for key in (
                    "enabled", "require_probe", "model", "accepted_model_ids", "reasoning_effort",
                    "via", "timeout_sec", "command", "auth_mode", "min_cli_version", "extra_args", "pass_env", "allow_cli_default_model",
                )
                if key in backend
            },
            "limits": self.limits,
            "prompt_settings": self.prompt_settings,
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def cache_fingerprint(self) -> str:
        """Hash result-affecting configuration without exposing it in cache names."""
        roles = {}
        for name in ("primary", "verifier", "fallback"):
            backend = self.backend(name)
            roles[name] = {
                key: backend.get(key)
                for key in (
                    "model",
                    "accepted_model_ids",
                    "via",
                    "reasoning_effort",
                    "command",
                    "auth_mode",
                    "min_cli_version",
                    "extra_args",
                    "pass_env",
                    "allow_cli_default_model",
                )
                if key in backend
            }
        payload = {
            "format": 2,
            "project_root": str(self.project_root),
            "gateway": {
                key: self.gateway.get(key)
                for key in (
                    "endpoint", "responses_path", "require_resolved_model",
                    "allow_remote_endpoint", "allowed_remote_hosts", "use_environment_proxy",
                )
            },
            "roles": roles,
            "prompt_settings": self.prompt_settings,
            "budget_tokens": self.budget_tokens,
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def backend(self, name: str) -> Dict[str, Any]:
        value = self.backends.get(name, {})
        return value if isinstance(value, dict) else {}

    def backend_ready(self, name: str) -> bool:
        backend = self.backend(name)
        if not backend.get("enabled", False):
            return False
        if backend.get("require_probe", True) and not backend.get("healthy", False):
            return False
        if backend.get("via", "responses_api") == "responses_api" and not str(backend.get("model", "")).strip():
            return False
        if (
            backend.get("via") == "codex_cli"
            and not str(backend.get("model", "")).strip()
            and not backend.get("allow_cli_default_model", False)
        ):
            return False
        if name == "fallback" and backend.get("require_probe", True) and not backend.get("vision_verified", False):
            return False
        return True

    def model_id(self, name: str) -> str:
        return str(self.backend(name).get("model", "")).strip()

    def timeout(self, name: str) -> int:
        raw = self.backend(name).get("timeout_sec") or self.gateway.get("timeout_sec", 180)
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 180
