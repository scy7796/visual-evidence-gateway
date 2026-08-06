"""Tests for the idempotent one-command setup path."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class SetupCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp_obj = tempfile.TemporaryDirectory(prefix="vb-setup-")
        self.tmp = Path(self.tmp_obj.name)

    def tearDown(self):
        self.tmp_obj.cleanup()

    def test_write_config_is_private_and_idempotent(self):
        from visual_evidence_gateway import setup_cli

        path = self.tmp / "nested" / "config.yaml"
        setup_cli._write_config(path, force=False)
        first = path.read_text(encoding="utf-8")
        self.assertIn('model: "gpt-5.6-luna"', first)
        self.assertIn("auth_mode: chatgpt", first)
        self.assertNotIn("OPENAI_API_KEY", first)
        path.write_text(first + "# local change\n", encoding="utf-8")
        setup_cli._write_config(path, force=False)
        self.assertTrue(path.read_text(encoding="utf-8").endswith("# local change\n"))
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_registration_uses_official_codex_mcp_shape_and_unified_server(self):
        from visual_evidence_gateway import setup_cli

        config = self.tmp / "config.yaml"
        config.write_text("{}", encoding="utf-8")
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(list(args))
            if args[-2:] == ["mcp", "list"]:
                return subprocess.CompletedProcess(args, 0, stdout="visual-evidence-gateway\n", stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        server_command = [str(self.tmp / "visual-evidence-gateway"), "serve"]
        with mock.patch.object(setup_cli, "_run", side_effect=fake_run), mock.patch.object(
            setup_cli, "_server_command", return_value=server_command
        ):
            setup_cli._register("/usr/bin/codex", config)

        self.assertEqual(calls[0], ["/usr/bin/codex", "mcp", "list"])
        self.assertEqual(calls[1], ["/usr/bin/codex", "mcp", "remove", "visual-evidence-gateway"])
        add = calls[2]
        self.assertEqual(add[:4], ["/usr/bin/codex", "mcp", "add", "visual-evidence-gateway"])
        self.assertIn("--env", add)
        self.assertIn(f"VISUAL_EVIDENCE_GATEWAY_CONFIG={config}", add)
        self.assertEqual(add[-3:], ["--", *server_command])
        self.assertNotIn("shell=True", " ".join(add))

    def test_frozen_binary_registers_itself_with_serve_subcommand(self):
        from visual_evidence_gateway import setup_cli

        with mock.patch.object(setup_cli.sys, "frozen", True, create=True), mock.patch.object(
            setup_cli.sys, "executable", str(self.tmp / "visual-evidence-gateway")
        ):
            self.assertEqual(
                setup_cli._server_command(),
                [str((self.tmp / "visual-evidence-gateway").absolute()), "serve"],
            )

    def test_noninteractive_login_fails_closed(self):
        from visual_evidence_gateway import setup_cli

        with mock.patch.object(setup_cli, "_chatgpt_login_confirmed", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "codex login"):
                setup_cli._ensure_login("codex", non_interactive=True)

    def test_main_stops_when_codex_is_missing(self):
        from visual_evidence_gateway import setup_cli

        with mock.patch.object(setup_cli.shutil, "which", return_value=None):
            self.assertEqual(setup_cli.main(["--non-interactive"]), 2)

    def test_repository_installers_download_one_binary_without_python_bootstrap(self):
        root = Path(__file__).resolve().parents[1]
        shell = (root / "install.sh").read_text(encoding="utf-8")
        powershell = (root / "install.ps1").read_text(encoding="utf-8")
        for text in (shell, powershell):
            folded = text.casefold()
            self.assertIn("releases/latest/download", folded)
            self.assertIn("visual-evidence-gateway", folded)
            self.assertIn("setup", folded)
            self.assertIn("sha256", folded)
            self.assertNotIn("python -m venv", folded)
            self.assertNotIn("pip install", folded)
            self.assertNotIn("chatgpt.com/codex/install", folded)
            self.assertNotIn("openai_api_key", folded)


if __name__ == "__main__":
    unittest.main()
