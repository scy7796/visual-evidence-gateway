"""Cache tests (T6 and spec section 16)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from visual_evidence_gateway.router.cache import VisionCache
from tests import make_cfg, make_image


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vr-cache-"))
        self.cfg = make_cfg(self.tmp)
        self.cache = VisionCache(self.cfg.cache_dir, key_path=self.tmp / "key")
        self.img = make_image(self.tmp / "a.png")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    class _Norm:
        pass

    def _norm(self, query="问题A", mode="ui", rigor="normal", img=None):
        n = self._Norm()
        n.hashes = ["h" + ("1" if img is None else "2")]
        n.query_norm = query
        n.mode = mode
        n.rigor = rigor
        return n

    def test_store_and_get_roundtrip(self):
        key = self.cache.key(self._norm(), self.cfg)
        compact = {"status": "ok", "answer": "答案", "evidence": [], "relevant_text": [], "uncertainty": [], "verified_by": ["primary-model"], "detail_ref": None, "full_text_ref": None}
        self.cache.store(key, compact, {"primary": {"status": "ok"}}, {"query": "问题A"})
        got = self.cache.get(key)
        self.assertEqual(got["answer"], "答案")
        self.assertIsNone(got["detail_ref"])
        self.assertIsNone(got["full_text_ref"])
        self.assertTrue(self.cache.summary_path(key).exists())
        self.assertFalse((self.cache.root / f"{key}.raw.primary.json").exists())
        index_lines = (self.cache.root / "index.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(index_lines), 1)
        self.assertEqual(json.loads(index_lines[0])["key"], key)

    def test_local_references_require_explicit_opt_in(self):
        cache = VisionCache(
            self.cfg.cache_dir / "refs",
            key_path=self.tmp / "refs-key",
            store_full_text=True,
            expose_local_refs=True,
        )
        key = cache.key(self._norm(), self.cfg)
        compact = {"status": "ok", "answer": "答案", "evidence": [], "relevant_text": [], "uncertainty": [], "verified_by": ["primary-model"], "detail_ref": None, "full_text_ref": None}
        cache.write_full_text(key, "完整 OCR")
        cache.store(key, compact, {}, {"query_hash": "abc"})
        got = cache.get(key)
        self.assertEqual(got["detail_ref"], str(cache.summary_path(key)))
        self.assertEqual(got["full_text_ref"], str(cache.root / f"{key}.ocr.txt"))

    def test_full_text_is_not_persisted_by_default(self):
        key = self.cache.key(self._norm(), self.cfg)
        self.cache.write_full_text(key, "sensitive OCR")
        self.assertFalse((self.cache.root / f"{key}.ocr.txt").exists())

    def test_raw_cache_requires_explicit_opt_in(self):
        cache = VisionCache(self.cfg.cache_dir / "raw", key_path=self.tmp / "raw-key", store_raw=True)
        key = cache.key(self._norm(), self.cfg)
        compact = {"status": "ok", "answer": "answer", "evidence": [], "relevant_text": [], "uncertainty": [], "verified_by": ["primary-model"], "detail_ref": None, "full_text_ref": None}
        cache.store(key, compact, {"primary": {"status": "ok"}}, {"query_hash": "abc"})
        self.assertTrue((cache.root / f"{key}.raw.primary.json").exists())

    def test_opt_in_raw_cache_is_still_recursively_redacted(self):
        cache = VisionCache(self.cfg.cache_dir / "masked", key_path=self.tmp / "masked-key", store_raw=True)
        key = cache.key(self._norm(), self.cfg)
        compact = {"status": "ok", "answer": "answer", "evidence": [], "relevant_text": [], "uncertainty": [], "verified_by": ["primary-model"], "detail_ref": None, "full_text_ref": None}
        cache.store(key, compact, {"primary": {"nested": ["Bearer abcdefghijklmnop"]}}, {"query_hash": "abc"})
        raw = (cache.root / f"{key}.raw.primary.json").read_text(encoding="utf-8")
        self.assertIn("[MASKED]", raw)
        self.assertNotIn("abcdefghijklmnop", raw)

    def test_key_varies_by_query(self):
        k1 = self.cache.key(self._norm(query="问题A"), self.cfg)
        k2 = self.cache.key(self._norm(query="问题B"), self.cfg)
        self.assertNotEqual(k1, k2)

    def test_key_varies_by_rigor(self):
        k1 = self.cache.key(self._norm(rigor="normal"), self.cfg)
        k2 = self.cache.key(self._norm(rigor="critical"), self.cfg)
        self.assertNotEqual(k1, k2)

    def test_key_varies_by_image(self):
        k1 = self.cache.key(self._norm(img=None), self.cfg)
        k2 = self.cache.key(self._norm(img=1), self.cfg)
        self.assertNotEqual(k1, k2)

    def test_key_varies_by_result_affecting_configuration(self):
        k1 = self.cache.key(self._norm(), self.cfg)
        self.cfg.backends["primary"]["model"] = "different-model"
        k2 = self.cache.key(self._norm(), self.cfg)
        self.assertNotEqual(k1, k2)

    def test_miss_returns_none(self):
        self.assertIsNone(self.cache.get("deadbeef" * 8))


if __name__ == "__main__":
    unittest.main()
