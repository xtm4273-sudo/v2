"""Final delivery display policy.

The report shown to customers should not expose internal missing-data markers.
Diagnostics still keep the original missing/conflict status for debugging.
"""
from __future__ import annotations

import re


PENDING_RE = re.compile(
    r"(?:<span\b[^>]*>\s*)?(?:待补充|数据待补充|数据暂未提供|接口未提供|缺少可比同期数据)(?:\s*</span>)?",
    re.IGNORECASE,
)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

HIDE_WHEN_MISSING_RE = re.compile(
    r"(前三|前五|TOP\s*5|Top\s*5|top\s*5|排名前三|排名前五|客户明细|明细|产品为|客户为)"
)


def normalize_delivery_display(markdown: str) -> str:
    """Remove visible missing markers from customer-facing Markdown.

    Numeric missing values are displayed as 0. Missing TopN/detail sentences are
    hidden instead of being displayed with a fake 0 identity.
    """
    return _normalize_delivery_display_with_audit(markdown)[0]


def build_delivery_display_audit(markdown: str, normalized: str | None = None) -> dict:
    """Summarize final-display fixes applied to customer-facing Markdown."""
    if normalized is None:
        normalized, actions = _normalize_delivery_display_with_audit(markdown)
    else:
        actions = _normalize_delivery_display_with_audit(markdown)[1]

    visible_missing_after = len(PENDING_RE.findall(_unwrap_pending_spans(normalized)))
    return {
        "status": "ok" if visible_missing_after == 0 else "needs_review",
        "visible_missing_before": len(PENDING_RE.findall(_unwrap_pending_spans(markdown))),
        "visible_missing_after": visible_missing_after,
        "zero_replacements": sum(1 for action in actions if action["action"] == "replace_missing_with_zero"),
        "hidden_topn_or_detail": sum(1 for action in actions if action["action"].startswith("hide_")),
        "actions": actions[:80],
        "truncated": len(actions) > 80,
        "note": "交付报告不展示待补充；数值缺失置0，空TopN/明细句隐藏。原始接口与章节清洗状态仍保留在 raw、cleaned 和 chapters.*.stats 中。",
    }


def _normalize_delivery_display_with_audit(markdown: str) -> tuple[str, list[dict]]:
    markdown = COMMENT_RE.sub("", markdown)
    markdown = _unwrap_pending_spans(markdown)
    lines = markdown.splitlines()
    normalized: list[str] = []
    actions: list[dict] = []
    skip_table = False

    for line_number, line in enumerate(lines, 1):
        stripped = line.strip()
        has_pending = _has_pending(stripped)

        if skip_table:
            if stripped.startswith("|") or not stripped:
                if stripped.startswith("|") and has_pending:
                    actions.append(_action("hide_missing_detail_table", line_number, stripped))
                continue
            skip_table = False

        trimmed = _trim_missing_topn_tail(line)
        if trimmed != line:
            actions.append(_action("hide_missing_topn_sentence", line_number, stripped))
            replaced = _replace_pending_with_zero(trimmed)
            if replaced != trimmed:
                actions.append(_action("replace_missing_with_zero", line_number, stripped))
            normalized.append(replaced)
            continue

        if has_pending and _should_hide_missing_line(stripped):
            actions.append(_action("hide_missing_topn_or_detail_line", line_number, stripped))
            skip_table = True
            continue

        replaced = _replace_pending_with_zero(line)
        if replaced != line:
            actions.append(_action("replace_missing_with_zero", line_number, stripped))
        normalized.append(replaced)

    text = "\n".join(normalized)
    text = _normalize_rank_placeholders(text)
    text = _remove_empty_table_artifacts(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + ("\n" if markdown.endswith("\n") else ""), actions


def _action(action: str, line_number: int, text: str) -> dict:
    return {
        "action": action,
        "line": line_number,
        "failure_type": "data_error",
        "failure_type_label": "接口数据问题",
        "reason": "接口数据为空、字段缺失或章节规则无法唯一取值，交付展示按规则清洗。",
        "preview": text[:160],
    }


def _unwrap_pending_spans(text: str) -> str:
    text = re.sub(
        r"<span\b[^>]*>\s*(待补充|数据待补充|数据暂未提供|接口未提供|缺少可比同期数据)\s*</span>",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"<font\b[^>]*>\s*(?:<b>)?\s*(待补充|数据待补充|数据暂未提供|接口未提供|缺少可比同期数据)\s*(?:</b>)?\s*</font>",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )


def _has_pending(text: str) -> bool:
    return bool(PENDING_RE.search(text))


def _should_hide_missing_line(text: str) -> bool:
    if HIDE_WHEN_MISSING_RE.search(text):
        return True
    if text.startswith("◇") and ("数据" in text or "明细" in text):
        return True
    return False


def _trim_missing_topn_tail(line: str) -> str:
    if not _has_pending(line):
        return line
    match = re.search(r"(.*?。?)其中[^。]*(?:前三|前五|TOP\s*5|Top\s*5|top\s*5|排名前三|排名前五)[^。]*。?", line)
    if not match:
        return line
    prefix = match.group(1).rstrip("。")
    return f"{prefix}。" if prefix else ""


def _replace_pending_with_zero(line: str) -> str:
    line = re.sub(r"[（(]\s*接口未提供(?:名称|数据)?\s*[）)]", "", line)
    line = re.sub(r"接口未提供(?:名称)?", "", line)
    line = PENDING_RE.sub("0", line)
    line = line.replace("客户名称0", "客户0")
    line = line.replace("TOP0", "TOP0%")
    line = re.sub(r"数据(?:暂未提供|待补充)", "0", line)
    return line


def _normalize_rank_placeholders(text: str) -> str:
    text = re.sub(r"(\d+)/0(?![\d%])", r"\1/0", text)
    text = re.sub(r"0/(\d+)", r"0/\1", text)
    return text


def _remove_empty_table_artifacts(text: str) -> str:
    text = re.sub(r"\n\|\s*0\s*(?:\|\s*0\s*)+\|\n?", "\n", text)
    return text
