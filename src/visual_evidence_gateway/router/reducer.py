"""Compact result builder and compression limits (spec section 13)."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any, Dict, List, Tuple


def cjk_count(text: str) -> int:
    return sum(1 for ch in text if _cjk_weight(ch) > 0)


def _cjk_weight(ch: str) -> float:
    if (
        "\u4e00" <= ch <= "\u9fff"
        or "\u3400" <= ch <= "\u4dbf"
        or "\u3040" <= ch <= "\u30ff"
        or "\uac00" <= ch <= "\ud7a3"
        or "\uff01" <= ch <= "\uff5e"
        or "\uf900" <= ch <= "\ufaff"
    ):
        return 1.2
    return 0.0


def word_count(text: str) -> int:
    return len(text.split())


def _norm_compare(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\s\W_]+", "", text).lower()
    out = []
    for ch in text:
        out.append(str(_CN_NUM[ch]) if ch in _CN_NUM else ch)
    return "".join(out)


_CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NEG_EXCLUDE = ("未央", "无垠", "不丹", "未来", "未免", "无非", "无为", "无边", "无敌", "非常", "不断", "不见得", "不料", "不仅", "不论", "无论", "无妨")


def _digits(s: str) -> List[int]:
    return [int(m) for m in re.findall(r"\d+", s)]


def _conflict(a: str, b: str) -> bool:
    na, nb = _norm_compare(a), _norm_compare(b)
    if not na or not nb or na == nb:
        return False
    digits_a, digits_b = _digits(na), _digits(nb)
    if digits_a and digits_b and digits_a != digits_b:
        return True  # 关键数字矛盾
    cjk_a = any("\u4e00" <= ch <= "\u9fff" for ch in na)
    cjk_b = any("\u4e00" <= ch <= "\u9fff" for ch in nb)
    if cjk_a != cjk_b:
        return False  # cross-language answers: no reliable mechanical conflict verdict

    def _neg(s: str) -> bool:
        raw = s
        if re.search(r"\b(not|no|never)\b", raw, re.IGNORECASE):
            return True
        for t in ("不", "无", "没", "未"):
            if t in raw and not any(ex in raw for ex in _NEG_EXCLUDE):
                return True
        return False

    if _neg(a) != _neg(b):
        return True
    if na in nb or nb in na:
        return False
    overlap = len(set(na) & set(nb)) / max(1, len(set(na) | set(nb)))
    return overlap < 0.5


def estimate_tokens(compact: Dict[str, Any]) -> int:
    """Deterministic token approximation: CJK chars *1.2 + ascii chars /4."""
    text = json.dumps(compact, ensure_ascii=False)
    weight = 0.0
    wide = 0
    for ch in text:
        w = _cjk_weight(ch)
        if w:
            weight += w
            wide += 1
    return int(weight + (len(text) - wide) / 4)


_SUFFIX_WITH_REF = "…(已截断，全文见 full_text_ref)"
_SUFFIX_NO_REF = "…(已截断)"


def _suffix(full_ref: Any) -> str:
    return _SUFFIX_WITH_REF if full_ref else _SUFFIX_NO_REF


def _fit_answer(answer: str, max_cjk: int, max_words: int, suffix: str) -> str:
    if cjk_count(answer) <= max_cjk and word_count(answer) <= max_words:
        return answer
    suffix_cjk = cjk_count(suffix)
    suffix_words = len(suffix.split())
    if cjk_count(answer) > max_cjk:
        keep = max_cjk - suffix_cjk
        if keep < 20:
            keep = 20
        cut: List[str] = []
        count = 0
        for ch in answer:
            if count >= keep:
                break
            cut.append(ch)
            if _cjk_weight(ch) > 0:
                count += 1
        return "".join(cut).rstrip() + suffix
    words = answer.split()
    keep = max_words - suffix_words
    if keep < 20:
        keep = 20
    return " ".join(words[:keep]).rstrip() + suffix


def build_compact(results: List, rigor: str, key: str, cache, cfg) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (ds_visible_compact, raw_by_backend)."""
    if not results:
        return (
            {
                "status": "failed",
                "answer": "",
                "evidence": [],
                "relevant_text": [],
                "uncertainty": [],
                "verified_by": [],
                "detail_ref": None,
                "full_text_ref": None,
                "trimmed": False,
            },
            {},
        )
    valid = [r for r in results if r.ok and not r.model_mismatch]
    primary = max(valid, key=lambda r: r.confidence if math.isfinite(r.confidence) else -1) if valid else results[0]
    answer = primary.answer if valid else ""
    evidence = list(primary.evidence) if valid else []
    relevant = list(primary.relevant_text) if valid else []
    uncertainty = list(primary.uncertainty) if valid else []
    raw_by_backend: Dict[str, Any] = {}
    for r in results:
        raw_by_backend[r.backend] = r.raw

    conflict = False
    note = ""
    for r in valid:
        for e in r.evidence:
            if e not in evidence:
                evidence.append(e)
        for u in r.uncertainty:
            if u not in uncertainty:
                uncertainty.append(u)
    evidence = sorted(
        evidence,
        key=lambda e: (e.get("confidence", 0) if isinstance(e.get("confidence", 0), (int, float)) else 0),
        reverse=True,
    )
    ok_pairs = [r for r in valid if r.answer.strip()]
    for i in range(1, len(ok_pairs)):
        a0, a1 = ok_pairs[i - 1].answer.strip(), ok_pairs[i].answer.strip()
        if _conflict(a0, a1):
            conflict = True
            break
    if conflict:
        secondary = valid[1] if len(valid) > 1 else ok_pairs[1]
        note = f"双后端结论存在分歧：{secondary.answer[:60]}"
        if note not in uncertainty:
            uncertainty.append(note)

    verified = []
    for r in valid:
        vm = (r.verified_model or "")[:64]
        if vm and vm not in verified:
            verified.append(vm)
    verified = verified[:4]
    if not verified:
        verified = [primary.backend] if valid else []

    if not valid:
        status = "failed"
    elif conflict:
        status = "partial"
    elif primary.status == "ok":
        status = "ok"
    else:
        status = primary.status  # never promote partial/failed to ok

    max_evidence = cfg.prompt_settings.get("max_evidence", 5)
    max_lines = cfg.prompt_settings.get("max_relevant_lines", 20)
    max_uncertainty = cfg.prompt_settings.get("max_uncertainty", 3)
    evidence = evidence[:max_evidence]
    from visual_evidence_gateway.router.validator import filter_relevant_text

    relevant = filter_relevant_text(relevant)[:max_lines]
    uncertainty = uncertainty[:max_uncertainty]
    if conflict and note not in uncertainty:
        uncertainty = uncertainty[: max(0, max_uncertainty - 1)] + [note]

    full_ref = None
    trimmed = False
    original_answer = answer
    max_cjk = cfg.prompt_settings.get("answer_max_cjk", 120)
    max_words = cfg.prompt_settings.get("answer_max_words", 100)
    budget = cfg.budget_tokens.get("critical" if rigor == "critical" else "normal", 350)
    if (
        cjk_count(answer) > max_cjk
        or word_count(answer) > max_words
        or estimate_tokens({"answer": answer}) > max(120, budget - 150)
    ):
        cache.write_full_text(key, answer)
        full_ref = cache.full_text_ref(key)
        target = max(120, budget - 150)
        while estimate_tokens({"answer": answer}) > target and len(answer) > 40:
            answer = answer[: max(40, int(len(answer) * 0.85))]
        suffix = _suffix(full_ref)
        answer = _fit_answer(answer, max_cjk, max_words, suffix)
        if suffix not in answer:
            answer = answer.rstrip("…") + suffix
        trimmed = answer != original_answer

    compact: Dict[str, Any] = {
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "relevant_text": relevant,
        "uncertainty": uncertainty,
        "verified_by": verified,
        "detail_ref": cache.detail_ref(key),
        "full_text_ref": full_ref,
        "trimmed": trimmed,
    }

    guard = 0
    while estimate_tokens(compact) > budget and guard < 200:
        guard += 1
        if len(compact["relevant_text"]) > 1:
            compact["relevant_text"].pop()
            trimmed = True
        elif compact["relevant_text"] and len(compact["relevant_text"][0]) > 61:
            compact["relevant_text"][0] = compact["relevant_text"][0][:60] + "…"
            trimmed = True
        elif len(compact["evidence"]) > 1:
            compact["evidence"].pop()
            trimmed = True
        elif compact["evidence"] and len(str(compact["evidence"][0].get("finding", ""))) > 101:
            compact["evidence"][0]["finding"] = str(compact["evidence"][0].get("finding", ""))[:100] + "…"
            trimmed = True
        elif len(compact["uncertainty"]) > 1:
            compact["uncertainty"].pop()
            trimmed = True
        elif compact["uncertainty"] and len(compact["uncertainty"][-1]) > 61:
            compact["uncertainty"][-1] = compact["uncertainty"][-1][:60] + "…"
            trimmed = True
        elif len(compact["answer"]) > 41:
            if not full_ref:
                try:
                    cache.write_full_text(key, compact["answer"])
                    full_ref = cache.full_text_ref(key)
                    compact["full_text_ref"] = full_ref
                except Exception:
                    pass
            suffix = _suffix(full_ref)
            compact["answer"] = compact["answer"][: max(40, len(compact["answer"]) // 2)].rstrip("…") + suffix
            trimmed = True
        else:
            break
        compact["trimmed"] = trimmed
    if estimate_tokens(compact) > budget:
        # Nuclear fallback: guarantee the hard budget for adversarial content.
        trimmed = True
        compact["relevant_text"] = []
        compact["evidence"] = []
        compact["uncertainty"] = []
        compact["verified_by"] = []
        compact["detail_ref"] = None
        compact["full_text_ref"] = None
        if not full_ref:
            try:
                cache.write_full_text(key, compact["answer"])
                full_ref = cache.full_text_ref(key)
                compact["full_text_ref"] = full_ref
            except Exception:
                pass
        compact["trimmed"] = True
        source = compact["answer"] or original_answer
        suffix = _suffix(compact.get("full_text_ref"))
        compact["answer"] = source[:30].rstrip("…") + suffix
        while estimate_tokens(compact) > budget and compact["answer"]:
            source = source[: max(0, len(source) - 4)]
            compact["answer"] = source.rstrip("…") + (suffix if source else "")
        if estimate_tokens(compact) > budget:
            compact["answer"] = "结果因输出预算限制而被截断。"
            compact["status"] = "partial" if valid else "failed"
    compact["trimmed"] = trimmed
    # Configuration validation enforces a minimum budget, but retain a final
    # invariant check so refactors cannot silently return an oversized object.
    if estimate_tokens(compact) > budget:
        compact = {
            "status": "partial" if valid else "failed",
            "answer": "结果因输出预算限制而被截断。",
            "evidence": [],
            "relevant_text": [],
            "uncertainty": [],
            "verified_by": [],
            "detail_ref": None,
            "full_text_ref": None,
            "trimmed": True,
        }
    return compact, raw_by_backend
