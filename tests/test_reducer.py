"""Compression tests (T9 and spec section 13 limits)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from visual_evidence_gateway.router.cache import VisionCache
from visual_evidence_gateway.router.models import BackendResult
from visual_evidence_gateway.router.reducer import build_compact, estimate_tokens
from tests import make_cfg


class ReducerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vr-red-"))
        self.cfg = make_cfg(self.tmp)
        self.cache = VisionCache(
            self.cfg.cache_dir, key_path=self.tmp / "key", store_full_text=True, expose_local_refs=True
        )
        self.key = "a" * 64

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _result(self, answer="答案", relevant=None, evidence=None, uncertainty=None, backend="primary", model="primary-model", status="ok", confidence=0.9):
        return BackendResult(
            backend=backend,
            ok=True,
            status=status,
            answer=answer,
            evidence=evidence or [{"finding": "证据一", "location": "center", "confidence": 0.9}],
            relevant_text=relevant or ["相关文字"],
            uncertainty=uncertainty or [],
            confidence=confidence,
            verified_model=model,
        )

    def test_t9_long_output_excerpted_with_full_ref(self):
        long_answer = " ".join(["word"] * 150)  # > 100 words
        compact, raws = build_compact([self._result(answer=long_answer)], "normal", self.key, self.cache, self.cfg)
        self.assertLessEqual(len(compact["answer"].split()), 100)
        self.assertIn("full_text_ref", compact)
        self.assertIsNotNone(compact["full_text_ref"])
        ref = Path(compact["full_text_ref"])
        self.assertTrue(ref.exists())
        self.assertIn("word word", ref.read_text(encoding="utf-8"))
        self.assertTrue(compact["trimmed"])

    def test_truncation_without_retention_has_no_broken_full_text_reference(self):
        cache = VisionCache(self.cfg.cache_dir, key_path=self.tmp / "key-no-ref", store_full_text=False)
        long_answer = " ".join(["word"] * 150)
        compact, _ = build_compact([self._result(answer=long_answer)], "normal", "b" * 64, cache, self.cfg)
        self.assertIsNone(compact["full_text_ref"])
        self.assertIn("已截断", compact["answer"])
        self.assertNotIn("full_text_ref", compact["answer"])
        self.assertTrue(compact["trimmed"])

    def test_evidence_capped_at_5(self):
        evidence = [{"finding": f"e{i}", "location": "center", "confidence": 0.5 + i / 20} for i in range(7)]
        compact, _ = build_compact([self._result(evidence=evidence)], "normal", self.key, self.cache, self.cfg)
        self.assertLessEqual(len(compact["evidence"]), 5)

    def test_relevant_text_capped_at_20(self):
        relevant = [f"line{i}" for i in range(30)]
        compact, _ = build_compact([self._result(relevant=relevant)], "normal", self.key, self.cache, self.cfg)
        self.assertLessEqual(len(compact["relevant_text"]), 20)

    def test_uncertainty_capped_at_3(self):
        uncertainty = [f"u{i}" for i in range(5)]
        compact, _ = build_compact([self._result(uncertainty=uncertainty)], "normal", self.key, self.cache, self.cfg)
        self.assertLessEqual(len(compact["uncertainty"]), 3)

    def test_token_budget_normal_350(self):
        relevant = [f"line{i} with some text" for i in range(60)]
        compact, _ = build_compact([self._result(relevant=relevant)], "normal", self.key, self.cache, self.cfg)
        self.assertLessEqual(estimate_tokens(compact), 350)
        self.assertIsNotNone(compact["detail_ref"])

    def test_token_budget_critical_600(self):
        relevant = [f"line{i} with some text" for i in range(60)]
        compact, _ = build_compact([self._result(relevant=relevant)], "critical", self.key, self.cache, self.cfg)
        self.assertLessEqual(estimate_tokens(compact), 600)

    def test_conflict_merge_marks_partial(self):
        primary = self._result(answer="错误提示被完全遮挡。")
        secondary = self._result(backend="verifier", model="verifier-model", answer="未发现遮挡。", confidence=0.95)
        compact, _ = build_compact([primary, secondary], "critical", self.key, self.cache, self.cfg)
        self.assertEqual(compact["status"], "partial")
        self.assertTrue(any("分歧" in u for u in compact["uncertainty"]))
        self.assertEqual(len(compact["verified_by"]), 2)

    def test_agreement_merge_stays_ok(self):
        primary = self._result(answer="错误提示被状态栏遮挡。")
        secondary = self._result(backend="verifier", model="verifier-model", answer="错误提示被状态栏遮挡。", confidence=0.95)
        compact, _ = build_compact([primary, secondary], "critical", self.key, self.cache, self.cfg)
        self.assertEqual(compact["status"], "ok")

    def test_negation_conflict_detected(self):
        primary = self._result(answer="页面正常。")
        secondary = self._result(backend="verifier", model="verifier-model", answer="页面不正常。", confidence=0.95)
        compact, _ = build_compact([primary, secondary], "critical", self.key, self.cache, self.cfg)
        self.assertEqual(compact["status"], "partial")

    def test_mixed_cjk_and_words_truncated(self):
        mixed = "字" * 120 + " " + " ".join(["word"] * 95)
        compact, _ = build_compact([self._result(answer=mixed)], "normal", self.key, self.cache, self.cfg)
        self.assertIsNotNone(compact["full_text_ref"])
        self.assertIn("已截断", compact["answer"])

    def test_conflict_note_survives_uncertainty_cap(self):
        primary = self._result(answer="结论A。", uncertainty=["u1", "u2", "u3"])
        secondary = self._result(backend="verifier", model="verifier-model", answer="相反的结论B。", confidence=0.95)
        compact, _ = build_compact([primary, secondary], "critical", self.key, self.cache, self.cfg)
        self.assertEqual(compact["status"], "partial")
        self.assertTrue(any("分歧" in u for u in compact["uncertainty"]))

    def test_cross_language_answers_not_flagged_conflict(self):
        primary = self._result(answer="页面有红色按钮，一切正常")
        secondary = self._result(backend="verifier", model="verifier-model", answer="the page shows a red button, everything is fine", confidence=0.95)
        compact, _ = build_compact([primary, secondary], "critical", self.key, self.cache, self.cfg)
        self.assertEqual(compact["status"], "ok")

    def test_english_negation_conflict_detected(self):
        primary = self._result(answer="There is no signal.")
        secondary = self._result(backend="verifier", model="verifier-model", answer="There is a signal.", confidence=0.95)
        compact, _ = build_compact([primary, secondary], "critical", self.key, self.cache, self.cfg)
        self.assertEqual(compact["status"], "partial")


if __name__ == "__main__":
    unittest.main()
