"""Trigger and routing policy (spec sections 4-7, 10, 14)."""
from __future__ import annotations

import re

_AMBIGUITY_MARKER = re.compile(
    # Readability-of-the-image markers only. Meta caveats such as
    # "无法确认是否为期望结果" or "无法判断后台是否运行" do not undermine the
    # pixel evidence and must not downgrade a correct visual answer.
    r"无法看清|看不清|无法辨认|无法读取|无法识别|模糊|难以分辨|低分辨率|分辨率低|"
    r"cannot see|cannot read|unclear|blurry|ambiguous|low resolution|unreadable"
)


def visual_required(has_visual_material: bool, depends_on_pixels: bool, no_better_text_source: bool) -> bool:
    """Formal decision: VisualRequired = material AND pixel/layout dependence AND no better source."""
    return bool(has_visual_material and depends_on_pixels and no_better_text_source)


def is_operational_failure(result) -> bool:
    return bool(result.operational_failure)


def is_semantic_insufficient(result, mode: str, cfg) -> bool:
    """Deterministic upgrade conditions (spec section 14)."""
    if not result.ok or result.status in ("partial", "failed", "unreadable"):
        return True
    threshold = cfg.prompt_settings.get("semantic_confidence_threshold", 0.72)
    if result.confidence < threshold:
        return True
    if mode == "text" and not result.relevant_text:
        return True  # 关键 OCR 为空
    if any(_AMBIGUITY_MARKER.search(entry) for entry in (result.uncertainty or [])):
        return True  # 图像本身不可读或关键内容歧义
    if mode == "chart" and any("数" in u or "value" in u.lower() for u in result.uncertainty):
        return True  # 图表关键数字歧义
    return False
