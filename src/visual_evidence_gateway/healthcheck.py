"""Configuration and transport diagnostics for Visual Evidence Gateway."""
from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from visual_evidence_gateway.backends.base import _check_endpoint, mask_secrets
from visual_evidence_gateway.backends.codex_cli import diagnose_codex_cli
from visual_evidence_gateway.router.config import load_config
from visual_evidence_gateway.router.health import summary


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def parse_endpoint(endpoint: str, *, allow_remote: bool = False, allowed_remote_hosts=None):
    normalized = _check_endpoint(
        endpoint,
        allow_remote=allow_remote,
        allowed_remote_hosts=allowed_remote_hosts or [],
    )
    parts = urlsplit(normalized)
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError(f"invalid endpoint port: {parts.netloc!r}") from exc
    return parts.hostname or "", port


def _report(cfg, check_connectivity: bool) -> dict:
    enabled_responses = [
        name
        for name in ("primary", "verifier", "fallback")
        if cfg.backend(name).get("enabled", False)
        and str(cfg.backend(name).get("via") or "responses_api").strip().lower() == "responses_api"
    ]
    endpoint = str(cfg.gateway.get("endpoint", "http://127.0.0.1:10100"))
    host, port = parse_endpoint(
        endpoint,
        allow_remote=bool(cfg.gateway.get("allow_remote_endpoint", False)),
        allowed_remote_hosts=cfg.gateway.get("allowed_remote_hosts", []),
    )
    gateway_checked = bool(check_connectivity and enabled_responses)
    gateway_reachable = port_open(host, port) if gateway_checked else None

    backend_states = summary(cfg)
    diagnostics = {}
    transport_ok = True
    for name in ("primary", "verifier", "fallback"):
        backend = cfg.backend(name)
        if not backend.get("enabled", False):
            continue
        via = str(backend.get("via") or "responses_api").strip().lower()
        if via == "codex_cli":
            diagnostic = diagnose_codex_cli(cfg, name, check_login=check_connectivity)
            diagnostics[name] = diagnostic
            if check_connectivity:
                role_ok = bool(diagnostic.get("executable_found") and diagnostic.get("version_ok"))
                if str(backend.get("auth_mode") or "existing").strip().lower() == "chatgpt":
                    role_ok = role_ok and diagnostic.get("subscription_auth") is True
                transport_ok = transport_ok and role_ok

    if gateway_checked:
        transport_ok = transport_ok and bool(gateway_reachable)
    config_ready = any(state.get("ready") for state in backend_states)
    ready_for_requests = bool(config_ready and transport_ok) if check_connectivity else None
    status_ok = bool(config_ready and (ready_for_requests if check_connectivity else True))
    return {
        "status": "ok" if status_ok else "error",
        "configuration_ready": bool(config_ready),
        "transport_checks_requested": bool(check_connectivity),
        "ready_for_requests": ready_for_requests,
        "config_path": str(cfg.config_path) if cfg.config_path else None,
        "health_path": str(cfg.health_path),
        "gateway": {
            "endpoint": endpoint,
            "required_by_enabled_backends": enabled_responses,
            "host": host,
            "port": port,
            "connectivity_checked": gateway_checked,
            "reachable": gateway_reachable,
        },
        "allowed_roots": [str(path) for path in cfg.allowed_roots],
        "forbidden_roots": [str(path) for path in cfg.forbidden_roots],
        "backends": backend_states,
        "transport_diagnostics": diagnostics,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Visual Evidence Gateway configuration and transports")
    parser.add_argument("--config", type=Path, default=None, help="Path to YAML or JSON configuration")
    parser.add_argument(
        "--check-connectivity",
        action="store_true",
        help="Check gateway reachability and Codex CLI login/version state",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(config_path=args.config)
        report = _report(cfg, args.check_connectivity)
    except Exception as exc:  # noqa: BLE001
        report = {
            "status": "error",
            "configuration_ready": False,
            "transport_checks_requested": bool(args.check_connectivity),
            "ready_for_requests": False,
            "error": mask_secrets(str(exc)),
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {report['error']}")
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        gateway = report["gateway"]
        reachability = (
            "not required"
            if not gateway["required_by_enabled_backends"]
            else "not checked"
            if gateway["reachable"] is None
            else "reachable"
            if gateway["reachable"]
            else "unreachable"
        )
        print(f"configuration: {report['config_path'] or '(defaults)'}")
        print(f"health state: {report['health_path']}")
        print(f"gateway: {gateway['endpoint']} ({reachability})")
        for state in report["backends"]:
            print(
                f"{state['name']}: enabled={state['enabled']} ready={state['ready']} "
                f"healthy={state['healthy']} via={state['via']} model_configured={state['model_configured']} "
                f"vision_verified={state['vision_verified']}"
            )
        for name, diagnostic in report["transport_diagnostics"].items():
            print(
                f"{name} Codex CLI: executable={diagnostic['executable_found']} "
                f"version_ok={diagnostic['version_ok']} subscription_auth={diagnostic['subscription_auth']} "
                f"detail={diagnostic['detail']}"
            )
        readiness = report["ready_for_requests"]
        print(f"configuration_ready: {report['configuration_ready']}")
        print(f"ready_for_requests: {'not checked' if readiness is None else readiness}")
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
