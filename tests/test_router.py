"""Routing tests (T2, T3, T4, T5, T8, T10 + cheap + recursion guard)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from visual_evidence_gateway.router.models import BackendResult
from visual_evidence_gateway.router.orchestrator import inspect
from tests import make_cfg, make_image


def ok_result(
    backend="primary",
    model="primary-model",
    answer="登录失败提示被状态栏遮挡。",
    confidence=0.93,
    relevant=None,
    uncertainty=None,
    evidence=None,
    status="ok",
):
    return BackendResult(
        backend=backend,
        ok=True,
        status=status,
        answer=answer,
        evidence=evidence
        or [{"finding": "错误提示底部约三分之一不可见", "location": "bottom-right", "confidence": confidence}],
        relevant_text=relevant or ["Connection failed"],
        uncertainty=uncertainty or [],
        confidence=confidence,
        verified_model=model,
    )


class FakeBackends:
    def __init__(self, behaviors):
        self.behaviors = behaviors
        self.calls = {name: 0 for name in behaviors}

    def runner(self, name):
        def fn(norm, cfg, prior_summary=None, retry_crop=None):
            self.calls[name] += 1
            return self.behaviors[name](norm, cfg, prior_summary=prior_summary, retry_crop=retry_crop)

        return fn

    def runners(self):
        return {name: self.runner(name) for name in self.behaviors}


class RouterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vr-test-"))
        self.img = make_image(self.tmp / "ok.png")
        self.outside = make_image(Path(tempfile.gettempdir()) / "vr-outside.png")
        self.cfg = make_cfg(self.tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)
        self.outside.unlink(missing_ok=True)

    def request(self, rigor="normal", mode="ui", path=None):
        return {"paths": [str(path or self.img)], "query": "页面右下角为什么显示异常？", "mode": mode, "rigor": rigor}

    def test_t2_normal_screenshot_single_primary(self):
        fake = FakeBackends({"primary": lambda n, c, **k: ok_result(), "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model"), "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model")})
        compact = inspect(self.request(), self.cfg, fake.runners())
        self.assertEqual(fake.calls, {"primary": 1, "verifier": 0, "fallback": 0})
        self.assertEqual(compact["status"], "ok")
        self.assertIn("primary-model", compact["verified_by"])
        from visual_evidence_gateway.router.reducer import estimate_tokens

        self.assertLessEqual(estimate_tokens(compact), 350)

    def test_t3_primary_rate_limited_verifier_first(self):
        primary_fail = BackendResult(backend="primary", ok=False, operational_failure=True, error="HTTP 429: rate limit")

        def primary(n, c, **k):
            return primary_fail

        fake = FakeBackends({"primary": primary, "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model"), "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model")})
        compact = inspect(self.request(), self.cfg, fake.runners())
        self.assertEqual(fake.calls["verifier"], 1)
        self.assertEqual(fake.calls["fallback"], 0)
        self.assertEqual(compact["status"], "ok")
        self.assertIn("verifier-model", compact["verified_by"])

    def test_t3b_verifier_fails_go_fallback(self):
        primary_fail = BackendResult(backend="primary", ok=False, operational_failure=True, error="HTTP 429")
        go_fail = BackendResult(backend="fallback", ok=False, operational_failure=True, error="HTTP 500")

        def primary(n, c, **k):
            return primary_fail

        def go(n, c, **k):
            return go_fail

        fake = FakeBackends({"primary": primary, "fallback": go, "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model")})
        compact = inspect(self.request(), self.cfg, fake.runners())
        self.assertEqual(fake.calls["verifier"], 1)
        self.assertEqual(fake.calls["fallback"], 0)
        self.assertEqual(compact["status"], "ok")

        # When verifier also fails, fallback is the fallback.
        verifier_fail = BackendResult(backend="verifier", ok=False, operational_failure=True, error="verifier 不可用")
        fake2 = FakeBackends(
            {
                "primary": lambda n, c, **k: primary_fail,
                "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model"),
                "verifier": lambda n, c, **k: verifier_fail,
            }
        )
        compact2 = inspect({**self.request(), "query": "另一个问题避免缓存命中"}, self.cfg, fake2.runners())
        self.assertEqual(fake2.calls["fallback"], 1)
        self.assertEqual(compact2["status"], "ok")
        self.assertIn("fallback-model", compact2["verified_by"])

    def test_t4_dense_text_crop_retry_then_verifier(self):
        low = BackendResult(
            backend="primary",
            ok=True,
            status="partial",
            answer="右下角文字无法辨认",
            evidence=[{"finding": "文字模糊", "location": "bottom-right", "confidence": 0.5}],
            relevant_text=[],
            uncertainty=["右下角文字无法辨认"],
            confidence=0.5,
            verified_model="primary-model",
        )
        calls = {"n": 0}

        def primary(n, c, prior_summary=None, retry_crop=None):
            calls["n"] += 1
            if retry_crop:
                return ok_result(answer="错误提示：Connection failed", relevant=["Connection failed"])
            return low

        fake = FakeBackends({"primary": primary, "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model"), "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model", answer="Connection failed")})
        compact = inspect(self.request(), self.cfg, fake.runners())
        self.assertEqual(calls["n"], 2)  # 原图 + 裁剪重试
        self.assertEqual(fake.calls["verifier"], 0)  # 重试已充分，不再升级
        self.assertEqual(compact["status"], "ok")

    def test_t4b_crop_retry_insufficient_then_verifier(self):
        low = BackendResult(
            backend="primary",
            ok=True,
            status="partial",
            answer="右下角文字无法辨认",
            evidence=[{"finding": "文字模糊", "location": "bottom-right", "confidence": 0.5}],
            relevant_text=[],
            uncertainty=["右下角文字无法辨认"],
            confidence=0.5,
            verified_model="primary-model",
        )

        def primary(n, c, prior_summary=None, retry_crop=None):
            if retry_crop:
                return BackendResult(
                    backend="primary", ok=True, status="partial", answer="裁剪后仍无法辨认",
                    evidence=[{"finding": "仍模糊", "location": "bottom-right", "confidence": 0.4}],
                    relevant_text=[], uncertainty=["仍无法辨认"], confidence=0.4,
                    verified_model="primary-model",
                )
            return low

        fake = FakeBackends({"primary": primary, "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model"), "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model", answer="Connection failed", confidence=0.98)})
        compact = inspect(self.request(), self.cfg, fake.runners())
        self.assertEqual(fake.calls["verifier"], 1)
        self.assertIn("verifier-model", compact["verified_by"])

    def test_t5_critical_primary_plus_verifier_one_result(self):
        fake = FakeBackends({"primary": lambda n, c, **k: ok_result(), "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model", answer="登录失败提示被状态栏遮挡。", confidence=0.95), "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model")})
        compact = inspect(self.request(rigor="critical"), self.cfg, fake.runners())
        self.assertEqual(fake.calls["primary"], 1)
        self.assertEqual(fake.calls["verifier"], 1)
        self.assertIsInstance(compact, dict)
        self.assertEqual(len(compact["verified_by"]), 2)
        self.assertEqual(compact["status"], "ok")

    def test_t5b_critical_conflict_partial(self):
        fake = FakeBackends(
            {
                "primary": lambda n, c, **k: ok_result(answer="错误提示被状态栏完全遮挡。"),
                "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model", answer="未发现任何遮挡。", confidence=0.95),
                "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model"),
            }
        )
        compact = inspect(self.request(rigor="critical"), self.cfg, fake.runners())
        self.assertEqual(compact["status"], "partial")
        self.assertTrue(any("分歧" in u for u in compact["uncertainty"]))

    def test_t8_path_outside_allowed_root_rejected_without_calls(self):
        fake = FakeBackends({"primary": lambda n, c, **k: ok_result(), "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model"), "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model")})
        compact = inspect(self.request(path=self.outside), self.cfg, fake.runners())
        self.assertEqual(compact["status"], "failed")
        self.assertIn("允许目录", compact.get("reason", ""))
        self.assertEqual(fake.calls, {"primary": 0, "verifier": 0, "fallback": 0})

    def test_t10_model_silent_substitution(self):
        substituted = ok_result(model="substituted-model", answer="替换模型给出的结论")
        substituted.model_mismatch = True

        def primary(n, c, **k):
            return substituted

        fake = FakeBackends({"primary": primary, "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model", answer="正式结论"), "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model")})
        compact = inspect(self.request(), self.cfg, fake.runners())
        self.assertEqual(fake.calls["verifier"], 1)
        # Independent verification passed; the substituted model is still not trusted evidence.
        self.assertEqual(compact["status"], "ok")
        self.assertEqual(compact["verified_by"], ["verifier-model"])
        self.assertTrue(any("与配置不符" in u for u in compact["uncertainty"]))

    def test_cheap_mode_verifier_first(self):
        primary_fail = BackendResult(backend="primary", ok=False, operational_failure=True, error="HTTP 429")

        def primary(n, c, **k):
            return primary_fail

        fake = FakeBackends({"primary": primary, "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model", answer="无重大错误弹窗"), "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model")})
        compact = inspect(self.request(rigor="cheap"), self.cfg, fake.runners())
        self.assertEqual(fake.calls["verifier"], 1)
        self.assertEqual(fake.calls["fallback"], 0)
        self.assertEqual(compact["status"], "ok")

    def test_recursion_guard(self):
        old = os.environ.get("VISUAL_EVIDENCE_GATEWAY_CHILD")
        os.environ["VISUAL_EVIDENCE_GATEWAY_CHILD"] = "1"
        try:
            fake = FakeBackends({"primary": lambda n, c, **k: ok_result(), "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model"), "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model")})
            compact = inspect(self.request(), self.cfg, fake.runners())
            self.assertEqual(compact["status"], "failed")
            self.assertIn("递归保护", compact.get("reason", ""))
            self.assertEqual(fake.calls, {"primary": 0, "verifier": 0, "fallback": 0})
        finally:
            if old is None:
                os.environ.pop("VISUAL_EVIDENCE_GATEWAY_CHILD", None)
            else:
                os.environ["VISUAL_EVIDENCE_GATEWAY_CHILD"] = old

    def test_compare_mode_requires_both_images(self):
        img2 = make_image(self.tmp / "after.png", color=(30, 30, 200))
        fake = FakeBackends(
            {
                "primary": lambda n, c, **k: ok_result(
                    answer="遮挡已消失。",
                    evidence=[
                        {"finding": "before 有遮挡", "location": "bottom-right", "confidence": 0.9, "image_index": 0},
                        {"finding": "after 无遮挡", "location": "bottom-right", "confidence": 0.95, "image_index": 1},
                    ],
                ),
                "verifier": lambda n, c, **k: ok_result("verifier", "verifier-model", answer="遮挡已消失。"),
                "fallback": lambda n, c, **k: ok_result("fallback", "fallback-model"),
            }
        )
        compact = inspect(
            {"paths": [str(self.img), str(img2)], "query": "对比两张图", "mode": "compare", "rigor": "normal"},
            self.cfg,
            fake.runners(),
        )
        self.assertEqual(fake.calls["primary"], 1)
        self.assertEqual(compact["status"], "ok")


if __name__ == "__main__":
    unittest.main()
