"""Regression tests for the subscription-first Luna default."""
from __future__ import annotations

import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests import make_cfg, make_image


class LunaSubscriptionDefaultTest(unittest.TestCase):
    def setUp(self):
        self.tmp_obj = tempfile.TemporaryDirectory(prefix="vr-luna-")
        self.tmp = Path(self.tmp_obj.name)

    def tearDown(self):
        self.tmp_obj.cleanup()

    def test_public_default_is_subscription_luna(self):
        from visual_evidence_gateway.router.config import Config, DEFAULTS

        primary = DEFAULTS["backends"]["primary"]
        self.assertTrue(primary["enabled"])
        self.assertEqual(primary["via"], "codex_cli")
        self.assertEqual(primary["model"], "gpt-5.6-luna")
        self.assertEqual(primary["auth_mode"], "chatgpt")
        self.assertEqual(primary["min_cli_version"], "0.146.0")
        self.assertFalse(primary["require_probe"])
        self.assertIn("--ephemeral", primary["extra_args"])
        self.assertIn("--ignore-user-config", primary["extra_args"])

        data = dict(DEFAULTS)
        cfg = Config(DEFAULTS, Path(__file__).resolve().parents[1])
        self.assertTrue(cfg.backend_ready("primary"))
        self.assertEqual(cfg.model_id("primary"), "gpt-5.6-luna")
        del data  # Keep the assertion focused on validated defaults.

    def test_primary_dispatches_to_codex_cli(self):
        import visual_evidence_gateway.backends.primary as primary

        cfg = make_cfg(self.tmp)
        cfg.backends["primary"].update({"via": "codex_cli", "model": "gpt-5.6-luna", "auth_mode": "chatgpt"})
        sentinel = object()
        with mock.patch.object(primary, "run_codex_cli", return_value=sentinel) as run:
            result = primary.run_primary(object(), cfg, prior_summary={"a": 1}, retry_crop=[Path("x")])
        self.assertIs(result, sentinel)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], "primary")

    def test_cli_command_forces_chatgpt_luna_and_strips_api_billing_env(self):
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
                "OPENAI_API_KEY": "sk-synthetic-not-real",
                "OPENAI_BASE_URL": "https://api.example.com/v1",
                "CODEX_API_KEY": "synthetic",
                "OPENAI_ORG_ID": "org-synthetic",
                "OPENAI_PROJECT_ID": "proj-synthetic",
                "ANTHROPIC_API_KEY": "sk-ant-synthetic",
                "GEMINI_API_KEY": "ai-synthetic",
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
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn('approval_policy="never"', command)
        self.assertIn("--image", command)
        for key in (
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "CODEX_API_KEY",
            "OPENAI_ORG_ID",
            "OPENAI_PROJECT_ID",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
        ):
            self.assertNotIn(key, captured["env"])
        self.assertEqual(captured["env"]["VISUAL_EVIDENCE_GATEWAY_CHILD"], "1")
        self.assertIsInstance(captured["stdin_data"], bytes)
        self.assertEqual(command[-1], "-")

    def test_config_rejects_api_billing_env_for_chatgpt_auth(self):
        from visual_evidence_gateway.router.config import load_config

        path = self.tmp / "config.json"
        path.write_text(
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
            load_config(config_path=path)

    def test_cli_verifies_resolved_model_from_transcript_header(self):
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
        job = self.tmp / "job-model"
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
            "model_id": "self-reported-alias",
            "images_seen": 1,
        }

        def fake_run(stdout_text):
            def _run(command, env, cwd, timeout, stdout_cap, stderr_cap, stdin_data=None):
                output = Path(command[command.index("--output-last-message") + 1])
                output.write_text(json.dumps(payload), encoding="utf-8")
                return 0, stdout_text, b"", False

            return _run

        with mock.patch.object(cli, "_find_codex", return_value="codex"), mock.patch.object(
            cli, "_check_minimum_version", return_value=(True, "")
        ):
            with mock.patch.object(cli, "_run_bounded", side_effect=fake_run(b"\nmodel: gpt-5.6-luna\nprovider: openai\n")):
                matched = cli.run_codex_cli("primary", norm, cfg)
            with mock.patch.object(cli, "_run_bounded", side_effect=fake_run(b"\nmodel: gpt-4.1\nprovider: openai\n")):
                mismatched = cli.run_codex_cli("primary", norm, cfg)

        self.assertTrue(matched.ok, matched.error)
        self.assertFalse(matched.model_mismatch)
        self.assertEqual(matched.verified_model, "gpt-5.6-luna")
        # The payload itself is valid; the mismatch is flagged separately so the
        # orchestrator can refuse to use the result (same contract as the
        # Responses API path).
        self.assertTrue(mismatched.ok)
        self.assertTrue(mismatched.model_mismatch)
        self.assertEqual(mismatched.verified_model, "gpt-4.1")
        self.assertIn("does not match configured model", mismatched.error)

    def test_config_rejects_invalid_auth_and_version(self):
        from visual_evidence_gateway.router.config import load_config

        for index, backend in enumerate(
            (
                {"auth_mode": "automatic"},
                {"min_cli_version": "0.144"},
            )
        ):
            path = self.tmp / f"bad-{index}.json"
            path.write_text(
                json.dumps({"allowed_roots": [str(self.tmp)], "backends": {"primary": backend}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_config(config_path=path)

    def test_gpt56_reasoning_efforts_are_forwarded(self):
        import visual_evidence_gateway.backends.codex_cli as cli

        for effort in ("none", "low", "medium", "high", "xhigh", "max"):
            self.assertEqual(cli._reasoning_override(effort), ["-c", f'model_reasoning_effort="{effort}"'])

    def test_legacy_minimal_reasoning_effort_is_rejected_for_luna_contract(self):
        import visual_evidence_gateway.backends.codex_cli as cli

        with self.assertRaisesRegex(ValueError, "reasoning_effort"):
            cli._reasoning_override("minimal")

    def test_invalid_reasoning_effort_is_rejected(self):
        from visual_evidence_gateway.router.config import load_config

        path = self.tmp / "bad-reasoning.json"
        path.write_text(
            json.dumps(
                {
                    "allowed_roots": [str(self.tmp)],
                    "backends": {"primary": {"reasoning_effort": "maximum"}},
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "reasoning_effort"):
            load_config(config_path=path)

    def test_minimum_cli_version_fails_closed(self):
        import visual_evidence_gateway.backends.codex_cli as cli

        backend = {"min_cli_version": "0.146.0"}
        with mock.patch.object(cli, "_codex_version", return_value=((0, 143, 9), "")):
            ok, detail = cli._check_minimum_version("codex", backend)
        self.assertFalse(ok)
        self.assertIn("older than required", detail)

    def test_healthcheck_does_not_claim_runtime_readiness_without_connectivity_check(self):
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
        missing = {
            "transport": "codex_cli",
            "executable_found": False,
            "version_ok": False,
            "login_checked": False,
            "subscription_auth": None,
            "detail": "Codex CLI was not found",
        }
        with mock.patch.object(healthcheck, "diagnose_codex_cli", return_value=missing):
            report = healthcheck._report(cfg, False)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["configuration_ready"])
        self.assertFalse(report["transport_checks_requested"])
        self.assertIsNone(report["ready_for_requests"])

    def test_healthcheck_requires_confirmed_subscription_when_requested(self):
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
            "detail": "not ChatGPT",
        }
        with mock.patch.object(healthcheck, "diagnose_codex_cli", return_value=failed):
            report = healthcheck._report(cfg, True)
        self.assertFalse(report["ready_for_requests"])
        self.assertEqual(report["status"], "error")
        self.assertFalse(report["gateway"]["connectivity_checked"])

        passed = {**failed, "subscription_auth": True, "detail": "ChatGPT login available"}
        with mock.patch.object(healthcheck, "diagnose_codex_cli", return_value=passed):
            report = healthcheck._report(cfg, True)
        self.assertTrue(report["ready_for_requests"])
        self.assertEqual(report["status"], "ok")


if __name__ == "__main__":
    unittest.main()
