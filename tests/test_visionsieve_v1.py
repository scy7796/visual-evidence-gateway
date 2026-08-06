from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from visionsieve_mcp import __version__
from visionsieve_mcp import cli, setup_cli
from visionsieve_mcp._compat import CONFIG_ENV, LEGACY_CONFIG_ENV, bridge_config_env


def test_public_version_is_1_0_0() -> None:
    assert __version__ == "1.0.0"


def test_new_config_env_is_bridged_to_hardened_core(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_ENV, "/tmp/visionsieve-config.yaml")
    monkeypatch.delenv(LEGACY_CONFIG_ENV, raising=False)

    bridge_config_env()

    assert __import__("os").environ[LEGACY_CONFIG_ENV] == "/tmp/visionsieve-config.yaml"


def test_legacy_config_env_remains_usable_during_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LEGACY_CONFIG_ENV, "/tmp/legacy-config.yaml")
    monkeypatch.delenv(CONFIG_ENV, raising=False)

    bridge_config_env()

    assert __import__("os").environ[CONFIG_ENV] == "/tmp/legacy-config.yaml"


def test_cli_reports_visionsieve_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "visionsieve 1.0.0"


def test_frozen_server_command_registers_same_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    executable = Path("/opt/visionsieve/visionsieve").absolute()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert setup_cli._server_command() == [str(executable), "serve"]


def test_registration_replaces_old_public_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        timeout: int = 60,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        del timeout, check
        calls.append(args)
        if args[-2:] == ["mcp", "list"]:
            return subprocess.CompletedProcess(args, 0, "visual-evidence-gateway\nvisionsieve\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(setup_cli.legacy, "_run", fake_run)
    monkeypatch.setattr(setup_cli, "_server_command", lambda: ["/abs/visionsieve", "serve"])

    config_path = tmp_path / "config.yaml"
    setup_cli._register("codex", config_path)

    assert ["codex", "mcp", "remove", "visionsieve"] in calls
    assert ["codex", "mcp", "remove", "visual-evidence-gateway"] in calls
    assert calls[-1] == [
        "codex",
        "mcp",
        "add",
        "visionsieve",
        "--env",
        f"VISIONSIEVE_CONFIG={config_path}",
        "--env",
        f"VISUAL_EVIDENCE_GATEWAY_CONFIG={config_path}",
        "--",
        "/abs/visionsieve",
        "serve",
    ]
