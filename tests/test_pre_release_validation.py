"""Contract tests for the operator-side pre-release validation pack."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


class PreReleaseValidationTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.validation = self.root / "pre_release_validation"

    def test_required_validation_files_exist(self):
        for name in (
            "README.md",
            "CODEX_TASK.md",
            "REAL_WORLD_TEST_REPORT.template.md",
            "claims-matrix.md",
            "run_validation.py",
        ):
            self.assertTrue((self.validation / name).is_file(), name)

    def test_readme_separates_local_and_live_claims(self):
        text = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("哪些卖点已经有证据", text)
        self.assertIn("当前不能宣称", text)
        self.assertIn("run_validation.py --runs 5 --host-mcp", text)
        self.assertIn("缓存命中时后端调用数为 0", text)
        self.assertNotIn("视觉准确率全面超过官方", text.split("当前不能宣称", 1)[0])

    def test_validation_runner_generates_credential_free_config_and_fixtures(self):
        script = self.validation / "run_validation.py"
        spec = importlib.util.spec_from_file_location("visual_evidence_release_validation", script)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix="vb-release-validation-") as directory:
            root = Path(directory)
            fixtures = root / "fixtures"
            specs = module.generate_fixtures(fixtures)
            self.assertEqual(set(specs), {"text", "ui", "chart", "compare", "long", "injection"})
            config = root / "config.yaml"
            module.write_config(config, fixtures, root)
            text = config.read_text(encoding="utf-8")
            self.assertIn('model: "gpt-5.6-luna"', text)
            self.assertIn("auth_mode: chatgpt", text)
            self.assertNotIn("OPENAI_API_KEY", text)
            self.assertNotIn("CODEX_API_KEY", text)
            self.assertTrue(all((fixtures / rel).is_file() for case in specs.values() for rel in case["paths"]))

    def test_release_runner_requires_three_live_probes(self):
        text = (self.validation / "run_validation.py").read_text(encoding="utf-8")
        self.assertIn("len(live_probes) >= 3", text)
        self.assertNotIn("len(live_probes) >= min(3, args.runs)", text)

    def test_long_benchmark_is_opt_in_not_a_p0_default(self):
        text = (self.validation / "run_validation.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--benchmark"', text)
        self.assertIn("if args.benchmark:", text)

    def test_codex_task_requires_execution_and_forbids_api_key(self):
        text = (self.validation / "CODEX_TASK.md").read_text(encoding="utf-8")
        self.assertIn("必须在当前机器上实际安装、运行", text)
        self.assertIn("不得创建或使用 API Key", text)
        self.assertIn("PASS", text)
        self.assertIn("CONDITIONAL PASS", text)
        self.assertIn("FAIL", text)


if __name__ == "__main__":
    unittest.main()
