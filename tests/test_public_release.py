"""Regression tests for the public 0.4 Visual Evidence Gateway release contract."""
from __future__ import annotations

import json
import os
import re
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests import make_cfg, make_image


class PublicReleaseDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.tmp_obj = tempfile.TemporaryDirectory(prefix="vb-public-")
        self.tmp = Path(self.tmp_obj.name)

    def tearDown(self):
        self.tmp_obj.cleanup()

    def test_public_default_is_subscription_luna_without_packaged_credentials(self):
        from visual_evidence_gateway.router.config import Config, DEFAULTS

        primary = DEFAULTS["backends"]["primary"]
        self.assertTrue(primary["enabled"])
        self.assertFalse(primary["require_probe"])
        self.assertEqual(primary["via"], "codex_cli")
        self.assertEqual(primary["model"], "gpt-5.6-luna")
        self.assertEqual(primary["auth_mode"], "chatgpt")
        self.assertEqual(primary["min_cli_version"], "0.146.0")
        self.assertEqual(primary["pass_env"], [])
        self.assertIn("--ephemeral", primary["extra_args"])
        self.assertIn("--ignore-user-config", primary["extra_args"])

        for name in ("verifier", "fallback"):
            self.assertFalse(DEFAULTS["backends"][name]["enabled"])

        cfg = Config(DEFAULTS, Path(__file__).resolve().parents[1])
        self.assertTrue(cfg.backend_ready("primary"))
        self.assertEqual(cfg.model_id("primary"), "gpt-5.6-luna")

        repo = Path(__file__).resolve().parents[1]
        env_example = (repo / ".env.example").read_text(encoding="utf-8")
        self.assertNotIn("OPENAI_API_KEY=", env_example)
        self.assertNotIn("CODEX_API_KEY=", env_example)

    def test_version_is_consistent(self):
        from visual_evidence_gateway import __version__

        project = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version = "([^"]+)"', project, re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml must declare a version")
        self.assertEqual(__version__, match.group(1))

    def test_all_roles_may_use_codex_cli(self):
        from visual_evidence_gateway.router.config import load_config

        for name in ("primary", "verifier", "fallback"):
            path = self.tmp / f"{name}.json"
            path.write_text(
                json.dumps(
                    {
                        "allowed_roots": [str(self.tmp)],
                        "backends": {
                            name: {
                                "enabled": True,
                                "healthy": True,
                                "require_probe": False,
                                "via": "codex_cli",
                                "model": f"{name}-model",
                                "command": "codex",
                                "auth_mode": "existing",
                                "extra_args": ["--ephemeral"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            cfg = load_config(config_path=path)
            self.assertEqual(cfg.backend(name)["via"], "codex_cli")

    def test_cli_auth_fields_are_validated_and_api_billing_env_is_rejected(self):
        from visual_evidence_gateway.router.config import load_config

        good = self.tmp / "good.json"
        good.write_text(
            json.dumps(
                {
                    "allowed_roots": [str(self.tmp)],
                    "backends": {
                        "primary": {
                            "via": "codex_cli",
                            "auth_mode": "chatgpt",
                            "min_cli_version": "0.146.0",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        cfg = load_config(config_path=good)
        self.assertEqual(cfg.backend("primary")["auth_mode"], "chatgpt")

        bad = self.tmp / "bad.json"
        bad.write_text(
            json.dumps(
                {
                    "allowed_roots": [str(self.tmp)],
                    "backends": {
                        "primary": {
                            "via": "codex_cli",
                            "auth_mode": "chatgpt",
                            "pass_env": ["OPENAI_API_KEY"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "API billing/alternate-provider variables"):
            load_config(config_path=bad)

    def test_cli_command_is_read_only_subscription_pinned_and_environment_is_explicit(self):
        import visual_evidence_gateway.backends.codex_cli as cli

        cfg = make_cfg(self.tmp)
        cfg.backends["primary"].update(
            {
                "via": "codex_cli",
                "model": "gpt-5.6-luna",
                "auth_mode": "chatgpt",
                "min_cli_version": "0.146.0",
                "extra_args": ["--ephemeral", "--ignore-user-config"],
                "pass_env": [],
            }
        )
        job = self.tmp / "job"
        job.mkdir()
        image = make_image(job / "input.png")
        norm = types.SimpleNamespace(
            job_dir=job,
            paths=[image],
            staged=[image],
            mode="general",
            query="What is visible?",
            query_norm="What is visible?",
            hashes=["h"],
            rigor="normal",
            cache_key="k",
        )
        payload = {
            "status": "ok",
            "answer": "A visible test image.",
            "evidence": [{"finding": "test image", "location": "center", "confidence": 0.9, "image_index": 0}],
            "relevant_text": [],
            "uncertainty": [],
            "confidence": 0.9,
            "model_id": "ignored-self-report",
            "images_seen": 1,
        }
        captured = {}

        def fake_run(command, env, cwd, timeout, stdout_cap, stderr_cap, stdin_data=None):
            captured.update(command=command, env=env, cwd=cwd, timeout=timeout, stdin_data=stdin_data)
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps(payload), encoding="utf-8")
            return 0, b"", b"", False

        with mock.patch.object(cli, "_find_codex", return_value="codex"), mock.patch.object(
            cli, "_check_minimum_version", return_value=(True, "")
        ), mock.patch.object(cli, "_run_bounded", side_effect=fake_run), mock.patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "synthetic-not-real",
                "CODEX_API_KEY": "synthetic-not-real",
                "UNRELATED_SECRET": "synthetic-not-real",
            },
            clear=False,
        ):
            result = cli.run_codex_cli("primary", norm, cfg)

        self.assertTrue(result.ok, result.error)
        command = captured["command"]
        self.assertEqual(command[0:2], ["codex", "exec"])
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-luna")
        self.assertIn('forced_login_method="chatgpt"', command)
        self.assertIn('model_reasoning_effort="medium"', command)
        for override in (
            "features.shell_tool=false",
            "features.shell_snapshot=false",
            "features.skill_mcp_dependency_install=false",
            "features.remote_plugin=false",
            "features.multi_agent=false",
            "features.hooks=false",
            "features.goals=false",
            'web_search="disabled"',
            'history.persistence="none"',
            "feedback.enabled=false",
            "analytics.enabled=false",
            'otel.metrics_exporter="none"',
            'otel.trace_exporter="none"',
            "otel.log_user_prompt=false",
        ):
            self.assertIn(override, command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn('approval_policy="never"', command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertEqual(command[-1], "-")
        self.assertIsInstance(captured["stdin_data"], bytes)
        self.assertNotIn("OPENAI_API_KEY", captured["env"])
        self.assertNotIn("CODEX_API_KEY", captured["env"])
        self.assertNotIn("UNRELATED_SECRET", captured["env"])
        self.assertEqual(captured["env"]["VISUAL_EVIDENCE_GATEWAY_CHILD"], "1")

    def test_cli_rejects_policy_relaxation(self):
        import visual_evidence_gateway.backends.codex_cli as cli

        self.assertEqual(
            cli._safe_extra_args(["--ephemeral", "--ignore-user-config"], "primary"),
            ["--ephemeral", "--ignore-user-config"],
        )
        with self.assertRaises(ValueError):
            cli._safe_extra_args(["--ignore-rules"], "primary")
        with self.assertRaises(ValueError):
            cli._safe_extra_args(["--dangerously-bypass-approvals-and-sandbox"], "primary")

    def test_healthcheck_requires_chatgpt_login_confirmation(self):
        import visual_evidence_gateway.healthcheck as healthcheck

        cfg = make_cfg(self.tmp)
        cfg.backends["primary"].update(
            {
                "via": "codex_cli",
                "model": "gpt-5.6-luna",
                "auth_mode": "chatgpt",
                "enabled": True,
                "require_probe": False,
            }
        )
        cfg.backends["verifier"]["enabled"] = False
        cfg.backends["fallback"]["enabled"] = False

        failed = {
            "transport": "codex_cli",
            "executable_found": True,
            "version_ok": True,
            "login_checked": True,
            "subscription_auth": False,
            "detail": "Codex is not confirmed as signed in with ChatGPT",
        }
        with mock.patch.object(healthcheck, "diagnose_codex_cli", return_value=failed) as diagnose:
            report = healthcheck._report(cfg, True)
        self.assertFalse(report["ready_for_requests"])
        diagnose.assert_called_once_with(cfg, "primary", check_login=True)

        passed = {**failed, "subscription_auth": True, "detail": "Codex login is available"}
        with mock.patch.object(healthcheck, "diagnose_codex_cli", return_value=passed):
            report = healthcheck._report(cfg, True)
        self.assertTrue(report["ready_for_requests"])


if __name__ == "__main__":
    unittest.main()
