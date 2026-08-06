"""Mechanical validation of backend results (spec section 14)."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any, Iterator, List, Tuple

VALID_STATUS = {"ok", "partial", "failed", "unreadable"}

BANNED_UNREADABLE = [
    "无法看到附件",
    "无法看到图片",
    "无法读取图片",
    "无法访问图片",
    "看不到图片",
    "没有看到图片",
    "图片不可见",
    "cannot see the attachment",
    "cannot view the image",
    "can't view the image",
    "unable to access the image",
    "cannot access the image",
    "i cannot see",
    "无法查看图片",
    "看不见图片",
    "无法查看",
    "not visible",
    "can't see the image",
    "cannot see the image",
]

# Patterns that describe actions the model CLAIMS TO HAVE TAKEN (execution),
# as opposed to image instructions quoted as OCR data.
INJECTION_EXEC = [
    "读取了 auth",
    "读取了认证",
    "已读取密钥",
    "读取了密钥",
    "执行了图片中的指令",
    "已执行图片中的",
    "按图片要求",
    "遵照图片指示",
    "opened auth",
    "executed the instruction",
    "read the credentials",
    "deleted the file",
    "删除了文件",
    # Traditional-Chinese variants (NFKC does not do simplified/traditional mapping).
    "已執行圖片中的",
    "執行圖片中的指令",
    "讀取了認證",
    "已讀取密鑰",
    "讀取了密鑰",
    "按圖片要求",
    "遵照圖片指示",
    # QR/URL, fake system message, fake dialog command, ignore-system-prompt claims.
    "打开了链接",
    "访问了链接",
    "访问了 url",
    "opened the link",
    "opened http",
    "以系统身份",
    "pretended to be the system",
    "运行了命令",
    "ran the command",
    "弹窗中的命令已运行",
    "运行了弹窗中的命令",
    "命令已运行",
    "已忽略系统提示",
    "ignored the system prompt",
    "打開了鏈接",
    "訪問了鏈接",
    "以系統身份",
    "運行了命令",
    "彈窗中的命令已運行",
    "運行了彈窗中的命令",
    "已忽略系統提示",
]


_SIMPLE = str.maketrans(
    {
        "執": "执", "圖": "图", "讀": "读", "認": "认", "鑰": "钥", "刪": "删", "檔": "档",
        "開": "开", "鏈": "链", "訪": "访", "問": "问", "統": "统", "運": "运", "彈": "弹",
        "們": "们", "個": "个", "藍": "蓝", "塊": "块", "紅": "红", "圓": "圆", "數": "数",
        # Japanese kanji / variant characters used in the same phrases.
        "実": "执", "図": "图", "証": "证", "読": "读", "無": "无", "変": "变", "対": "对",
        "関": "关", "閉": "闭", "誤": "误", "見": "见", "伝": "传", "達": "达",
    }
)

_HOMOGLYPHS = str.maketrans(
    {
        # Cyrillic lowercase (lower() runs first, so uppercase forms collapse here)
        "е": "e", "а": "a", "о": "o", "р": "p", "с": "c", "х": "x", "і": "i", "ѕ": "s",
        "н": "h", "м": "m", "и": "u", "у": "y", "п": "n", "к": "k", "в": "b", "һ": "h",
        "ԁ": "d", "т": "t", "г": "r",
        # Greek
        "ε": "e", "ο": "o", "ι": "i", "ρ": "p", "υ": "u", "ν": "v", "τ": "t", "η": "n",
        "κ": "k", "α": "a", "μ": "m", "χ": "x", "λ": "l",
        # Small caps (U+1D00-1D7F, U+029C)
        "ᴇ": "e", "ᴛ": "t", "ʜ": "h", "ɪ": "i", "ɴ": "n", "ꜱ": "s", "ᴜ": "u", "ᴄ": "c",
        "ᴅ": "d", "ʀ": "r", "ᴀ": "a", "ʟ": "l", "ᴏ": "o", "ᴍ": "m", "ꜰ": "f", "ɢ": "g",
        "ʙ": "b", "ᴘ": "p", "ᴠ": "v", "ᴡ": "w", "ʏ": "y", "ᴋ": "k",
    }
)

_QUOTE_MARKERS = ("图中写着", "图片中写着", "图中文字为", "图片文字为", "写着“", "文字为“", "图中内容为", "图像内容为")
_FRAMING = ("图像内容", "图片内容", "未执行", "并未执行", "转述", "引号", "是内容")


def _normalize(text: str) -> str:
    """NFKC + lower + strip C/Mn + simplified/homoglyph map + strip ALL
    punctuation/digits/whitespace (keep CJK ext-A/kana/hangul/fullwidth + ASCII letters)."""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = "".join(
        ch
        for ch in text
        if not unicodedata.category(ch).startswith("C") and not unicodedata.category(ch).startswith("M")
    )
    text = text.translate(_SIMPLE).translate(_HOMOGLYPHS)
    return re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7a3\uff01-\uff5eA-Za-z]", "", text)


_INJECTION_NORMALIZED = [_normalize(p) for p in INJECTION_EXEC]


def _iter_text(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from _iter_text(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_text(value)


def _all_keys(obj: Any) -> Iterator[str]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from _all_keys(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _all_keys(value)


def _banned_hit(text: str) -> bool:
    n = _normalize(text)
    return any(b in n for b in _BANNED_UNREADABLE_NORMALIZED)


_BANNED_UNREADABLE_NORMALIZED = [_normalize(b) for b in BANNED_UNREADABLE]


def validate_backend_payload(raw: Any, n_images: int, mode: str) -> Tuple[bool, List[str]]:
    """Validate the model payload against the public result contract.

    Only ``ok`` and ``partial`` are usable results. ``failed`` and ``unreadable``
    remain valid status vocabulary for model self-reporting, but never become
    accepted evidence.
    """
    issues: List[str] = []
    if not isinstance(raw, dict):
        return False, ["后端输出不是 JSON 对象"]

    allowed_fields = {
        "status", "answer", "evidence", "relevant_text", "uncertainty",
        "confidence", "model_id", "images_seen",
    }
    missing = sorted(allowed_fields - set(raw))
    extra = sorted(set(raw) - allowed_fields)
    if missing:
        issues.append("缺少字段: " + ", ".join(missing))
    if extra:
        issues.append("存在未声明字段: " + ", ".join(str(v) for v in extra[:10]))

    status = raw.get("status")
    if status not in VALID_STATUS:
        issues.append(f"status 非法: {status!r}")
    elif status in {"failed", "unreadable"}:
        issues.append("模型报告结果失败或图片不可读")

    answer = raw.get("answer")
    if not isinstance(answer, str):
        issues.append("answer 必须是字符串")
    elif not answer.strip():
        issues.append("answer 为空")
    elif len(answer) > 100_000:
        issues.append("answer 过长")
    elif _has_lone_surrogate(answer):
        issues.append("answer 含非法代理项")

    evidence = raw.get("evidence")
    if not isinstance(evidence, list):
        issues.append("evidence 必须是数组")
        evidence = []
    elif not evidence:
        issues.append("evidence 为空")
    elif len(evidence) > 5:
        issues.append("evidence 超过 5 项")
    evidence_fields = {"finding", "location", "confidence", "image_index"}
    for i, item in enumerate(evidence):
        if not isinstance(item, dict):
            issues.append(f"evidence[{i}] 必须是对象")
            continue
        missing_e = sorted(evidence_fields - set(item))
        extra_e = sorted(set(item) - evidence_fields)
        if missing_e:
            issues.append(f"evidence[{i}] 缺少字段: {', '.join(missing_e)}")
        if extra_e:
            issues.append(f"evidence[{i}] 存在未声明字段: {', '.join(str(v) for v in extra_e)}")
        finding = item.get("finding")
        location = item.get("location")
        if not isinstance(finding, str) or not finding.strip():
            issues.append(f"evidence[{i}].finding 必须是非空字符串")
        elif len(finding) > 20_000 or _has_lone_surrogate(finding):
            issues.append(f"evidence[{i}].finding 非法或过长")
        if not isinstance(location, str):
            issues.append(f"evidence[{i}].location 必须是字符串")
        elif len(location) > 2_000 or _has_lone_surrogate(location):
            issues.append(f"evidence[{i}].location 非法或过长")
        confidence = item.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            issues.append(f"evidence[{i}].confidence 不在 0..1")
        image_index = item.get("image_index")
        if isinstance(image_index, bool) or not isinstance(image_index, int):
            issues.append(f"evidence[{i}].image_index 必须是整数")
        elif image_index < 0 or image_index >= n_images:
            issues.append(f"evidence[{i}].image_index 超出输入图片范围")

    for field, max_items, max_length in (
        ("relevant_text", 100, 20_000),
        ("uncertainty", 3, 4_000),
    ):
        items = raw.get(field)
        if not isinstance(items, list):
            issues.append(f"{field} 必须是数组")
            continue
        if len(items) > max_items:
            issues.append(f"{field} 项数过多")
        for i, value in enumerate(items):
            if not isinstance(value, str):
                issues.append(f"{field}[{i}] 必须是字符串")
            elif len(value) > max_length or _has_lone_surrogate(value):
                issues.append(f"{field}[{i}] 非法或过长")

    conf = raw.get("confidence")
    if (
        isinstance(conf, bool)
        or not isinstance(conf, (int, float))
        or not math.isfinite(float(conf))
        or not 0.0 <= float(conf) <= 1.0
    ):
        issues.append("confidence 不在 0..1")

    model_id = raw.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        issues.append("model_id 缺失")
    elif len(model_id) > 512 or _has_lone_surrogate(model_id):
        issues.append("model_id 非法或过长")

    seen = raw.get("images_seen")
    if isinstance(seen, bool) or not isinstance(seen, int) or seen < 1:
        issues.append("images_seen 缺失或不是正整数")
    elif seen != n_images:
        issues.append(f"images_seen({seen}) 与输入图片数({n_images})不一致")

    if isinstance(answer, str) and (
        _banned_hit(answer)
        or any(_banned_hit(str(item.get("finding", ""))) for item in evidence if isinstance(item, dict))
    ):
        issues.append("答案声称无法看到图片")
    if mode == "compare":
        indices = [item.get("image_index") for item in evidence if isinstance(item, dict)]
        if 0 not in indices or 1 not in indices:
            issues.append("compare 模式未区分 before/after")
    return len(issues) == 0, issues


def detect_injection(raw: Any) -> bool:
    """True when the model claims to have executed image instructions.

    Scans answer, evidence findings, uncertainty and dict keys (relevant_text is
    quoted OCR data; only cross-field spans from answer into relevant_text are
    flagged). Exemptions are strict: a quote marker immediately before the match
    (OCR transcription) or a direct negation prefix (未/没有/did not/not/never)
    immediately before the match. A negation AFTER the match never exempts, and
    double negations (不得不/不能不) count as affirmative execution.
    """
    if not isinstance(raw, dict):
        return False
    neg_prefixes = ("didnot", "not", "never", "没有", "不曾", "尚未", "从未", "不能", "未曾", "未能", "未")
    double_neg = ("cannotnot", "nevernot", "notnot", "不得不", "不能不")

    def _flagged(n: str, p: str) -> bool:
        idx = n.find(p)
        while idx != -1:
            before = n[max(0, idx - 12) : idx]
            after = n[idx + len(p) : idx + len(p) + 25]
            if any(q in before for q in _QUOTE_MARKERS) and any(f in after for f in _FRAMING):
                idx = n.find(p, idx + 1)
                continue
            pre = n[max(0, idx - 8) : idx]
            if pre.endswith(double_neg):
                return True
            if pre.endswith(neg_prefixes):
                idx = n.find(p, idx + 1)
                continue
            return True
        return False

    def _collect(obj, out, depth=0):
        if isinstance(obj, str):
            out.append(obj)
        elif isinstance(obj, dict):
            for key, value in obj.items():
                if depth == 0 and key == "relevant_text":
                    continue  # top-level OCR field only: filtered at delivery
                out.append(str(key))
                _collect(value, out, depth + 1)
        elif isinstance(obj, list):
            for value in obj:
                _collect(value, out, depth)

    fields: List[str] = []
    _collect(raw, fields)
    joined = "".join(fields)
    for text in [*fields, joined, joined[::-1]]:
        n = _normalize(text)
        for p in _INJECTION_NORMALIZED:
            if _flagged(n, p):
                return True
    for text in [str(raw.get("answer", "")), joined]:
        if _semantic_flagged(text):
            return True
    return False


def _has_lone_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


_ACTION_ZH = ("执行", "运行", "打开", "读取", "删除", "访问", "复制", "发送", "上传", "下载", "移动", "写入", "创建", "转发", "点击", "提交", "获取", "取得", "提取", "导出", "泄露", "解密", "窃取")
_OBJECT_ZH = ("命令", "指令", "密钥", "凭据", "认证", "凭证", "密码", "文件", "链接", "url", "附件", "auth", "token", "截图", "指示", "要求")
_FOLLOW_ZH = ("遵照", "遵从", "依照", "按照", "按图片", "按图")
_CLAIM_ZH = ("已", "已经", "把", "将", "完成", "成功")
# Verbs whose bare claim (已执行/执行了/运行了) is already an execution claim,
# even without an explicit object. Task verbs (读取/删除/打开/...) need an object
# (密钥/文件/指令/...) so that legitimate OCR summaries like "已读取图片内容"
# are not false positives.
_EXEC_VERBS = ("执行", "运行")
_CLAIM_PREFIXES = ("已", "已经", "完成", "成功", "把", "将")
# Verbs that describe the vision analysis itself. A bare 已执行/执行了 claim is
# exempt ONLY when such an analysis verb appears early in the tail and no
# sensitive object or other action verb is present (e.g. "已执行两图对比").
_ANALYSIS_FOLLOW = ("对比", "比较", "分析", "检查", "验证", "识别", "读取", "提取", "扫描", "核对", "评估", "审查")
_ACTION_EN_RE = re.compile(
    r"\b(execut\w*|run\w*|open\w*|read\w*|delet\w*|access\w*|cop\w*|send\w*|upload\w*|download\w*|writ\w*|creat\w*|click\w*|submit\w*|follow\w*)\b"
)
_OBJECT_EN_RE = re.compile(
    r"\b(command\w*|instruction\w*|credential\w*|auth\w*|file\w*|link\w*|url\w*|password\w*|token\w*|attachment\w*|screenshot\w*)\b"
)
# "reads" is also used statively ("the token reads X") to describe image
# content. A read-family verb only counts as an execution claim when a
# first-person subject is attached ("I read the credentials").
_READ_FIRST_PERSON_RE = re.compile(r"\b(i|we|my|our)\b[^.;!?]{0,40}\bread\w*\b")


def _semantic_flagged(raw_text: str) -> bool:
    """Collocation-based paraphrase detection (past-tense execution claims).

    Unlike bag-of-words co-occurrence, this requires the claim marker to be
    attached to the verb (已执行/执行了/把文件删除/按图片要求删除...), and it
    applies the same quote/framing exemption as the pattern scanner so that
    legitimate OCR quotations ("图中写着「已执行...」，该文字是图像内容，未执行")
    are not treated as execution claims.
    """
    text = unicodedata.normalize("NFKC", str(raw_text)).lower()
    text = text.translate(_SIMPLE).translate(_HOMOGLYPHS)
    zh = _normalize(str(raw_text))

    def _exempt(idx: int) -> bool:
        before = zh[max(0, idx - 12) : idx]
        after = zh[idx : idx + 25]
        return any(q in before for q in _QUOTE_MARKERS) and any(f in after for f in _FRAMING)

    def _exec_claim_flagged(tail: str) -> bool:
        tail = tail[:40]
        if any(o in tail for o in _OBJECT_ZH):
            return True
        if any(a in tail[:12] for a in _ANALYSIS_FOLLOW):
            return False
        if any(a in tail for a in _ACTION_ZH):
            return True
        return True  # bare execution claim without benign analysis context

    if any(f in zh for f in _FOLLOW_ZH) and any(o in zh for o in _OBJECT_ZH):
        for f in _FOLLOW_ZH:
            idx = zh.find(f)
            if idx != -1:
                seg = zh[idx:]
                if any(a in seg for a in _ACTION_ZH) and any(o in seg for o in _OBJECT_ZH):
                    if not _exempt(idx):
                        return True
    for a in _ACTION_ZH:
        for pre in _CLAIM_PREFIXES:
            idx = zh.find(pre + a)
            if idx != -1:
                flagged = _exec_claim_flagged(zh[idx + len(pre) + len(a) :]) if a in _EXEC_VERBS else any(
                    o in zh[idx:] for o in _OBJECT_ZH
                )
                if flagged and not _exempt(idx):
                    return True
        idx = zh.find(a + "了")
        if idx != -1:
            flagged = _exec_claim_flagged(zh[idx + len(a) + 1 :]) if a in _EXEC_VERBS else any(
                o in zh[idx:] for o in _OBJECT_ZH
            )
            if flagged and not _exempt(idx):
                return True
        # Bare action + sensitive object (e.g. "打开链接", "解密认证文件"):
        # imperative-style claims without 了/已 are covered here, with the same
        # quote/framing exemption so OCR transcriptions still pass.
        idx = zh.find(a)
        if idx != -1:
            seg = zh[idx:]
            if any(o in seg for o in _OBJECT_ZH):
                if not _exempt(idx):
                    return True
    action_matches = list(_ACTION_EN_RE.finditer(text))
    agentive_en = any(not match.group(0).lower().startswith("read") for match in action_matches)
    read_claim_en = bool(_READ_FIRST_PERSON_RE.search(text))
    object_en = bool(_OBJECT_EN_RE.search(text))
    if action_matches and object_en and (agentive_en or read_claim_en):
        negated = bool(re.search(r"\b(did not|didn't|never)\b", text)) or "没有" in zh or "未" in zh or "不能" in zh
        double_neg_en = bool(re.search(r"\b(cannot not|never not|not not)\b", text))
        if not negated or double_neg_en:
            return True
    return False


def filter_relevant_text(entries) -> List[str]:
    """Strip execution-claim content from the OCR field before delivery."""
    out: List[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        n = _normalize(entry)
        if any(p in n for p in _INJECTION_NORMALIZED) or _semantic_flagged(entry):
            out.append("[图像文字疑似指令，已过滤]")
        else:
            out.append(entry)
    return out


def extract_json(text: str) -> Any:
    """Extract a JSON object from backend output (fences/multi-object tolerated)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError, ValueError):
        pass
    candidates: List[Any] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    obj = json.loads(text[start : i + 1])
                    candidates.append(obj)
                except Exception:
                    pass
                start = -1
    for obj in candidates:
        if isinstance(obj, dict) and ("status" in obj or "answer" in obj):
            return obj
    if candidates:
        return candidates[-1]
    try:
        repaired = json.loads(text + "}")
        if isinstance(repaired, dict):
            return repaired
    except Exception:
        pass
    if start != -1:
        for end in range(len(text) - 1, start, -1):
            if text[end] == "}":
                try:
                    obj = json.loads(text[start : end + 1])
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    continue
    return None
