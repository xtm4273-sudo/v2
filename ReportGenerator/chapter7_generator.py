"""第七章生成器 - 行销行为。

第七章分析拜访量和时间分配。主流程读取 MOUDLE=7 接口指标行，
同时保留内部 visit/time_allocation 契约用于旧 fixture 和单测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging

from Data import EMPTY_DATA_MESSAGE, ChapterDataError

logger = logging.getLogger(__name__)

DEFAULT_CHAPTER7_ACTION_GUIDE = ""


def _fmt_int(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return str(int(value))


def _fmt_percent(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%"


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


# ── 数据契约 dataclasses ─────────────────────────────────────────────


@dataclass
class VisitMetric:
    actual: Optional[float] = None
    target: Optional[float] = None
    achievement_rate: Optional[float] = None
    deduction_score: Optional[float] = None


@dataclass
class TimeAllocation:
    project_ratio: Optional[float] = None
    customer_ratio: Optional[float] = None


@dataclass
class Chapter7Data:
    metadata: Dict[str, Any] = field(default_factory=dict)
    total_visit: VisitMetric = field(default_factory=VisitMetric)
    project_visit: VisitMetric = field(default_factory=VisitMetric)
    time_allocation: TimeAllocation = field(default_factory=TimeAllocation)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "total_visit": {
                "actual": self.total_visit.actual,
                "target": self.total_visit.target,
                "achievement_rate": self.total_visit.achievement_rate,
                "deduction_score": self.total_visit.deduction_score,
            },
            "project_visit": {
                "actual": self.project_visit.actual,
                "target": self.project_visit.target,
                "achievement_rate": self.project_visit.achievement_rate,
                "deduction_score": self.project_visit.deduction_score,
            },
            "time_allocation": {
                "project_ratio": self.time_allocation.project_ratio,
                "customer_ratio": self.time_allocation.customer_ratio,
            },
            "warnings": self.warnings,
        }


# ── 主入口 ───────────────────────────────────────────────────────────


def format_chapter7_data(
    raw_data: Any,
    period: str = "",
    action_guide_text: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    chapter_data = normalize_chapter7_data(raw_data, period=period)
    markdown = build_chapter7_markdown(chapter_data, action_guide_text=action_guide_text)
    stats = build_chapter7_stats(chapter_data)
    stats["行动指南来源"] = "AI" if action_guide_text else "规则"
    return markdown, stats


async def format_chapter7_data_with_ai(
    raw_data: Any,
    period: str = "",
    model: Optional[Any] = None,
    action_writer: Optional[Any] = None,
) -> Tuple[str, Dict[str, Any]]:
    chapter_data = normalize_chapter7_data(raw_data, period=period)
    action_context = build_chapter7_action_context(chapter_data)
    action_guide_text = ""

    if action_writer is not None:
        action_guide_text = await action_writer.generate(
            action_context=action_context,
            fallback_text=action_guide_text,
        )
    elif model is not None:
        from ReportGenerator.chapter7_ai_writer import generate_chapter7_action_guide

        action_guide_text = await generate_chapter7_action_guide(
            action_context=action_context,
            model=model,
            fallback_text=action_guide_text,
        )

    markdown = build_chapter7_markdown(chapter_data, action_guide_text=action_guide_text)
    stats = build_chapter7_stats(chapter_data, action_context=action_context)
    stats["行动指南来源"] = "AI" if action_guide_text else "规则"
    return markdown, stats


# ── 数据标准化 ───────────────────────────────────────────────────────


def normalize_chapter7_data(raw_data: Any, period: str = "") -> Chapter7Data:
    subject = _extract_subject(raw_data)
    rows = subject.get("章节数据")
    if isinstance(rows, list) and rows:
        return _normalize_chapter7_from_metric_rows(subject, rows, period=period)

    return _normalize_chapter7_from_internal_contract(subject, period=period)


def _normalize_chapter7_from_internal_contract(subject: Dict[str, Any], period: str = "") -> Chapter7Data:
    metadata = _extract_metadata(subject, period=period)
    warnings: List[str] = []

    visit_data = subject.get("visit") if isinstance(subject.get("visit"), dict) else {}
    total_visit = _normalize_visit_metric(
        visit_data.get("total") if isinstance(visit_data.get("total"), dict) else {}, warnings, "拜访总频次"
    )
    project_visit = _normalize_visit_metric(
        visit_data.get("project") if isinstance(visit_data.get("project"), dict) else {}, warnings, "项目拜访频次"
    )

    alloc_data = subject.get("time_allocation") if isinstance(subject.get("time_allocation"), dict) else {}
    time_allocation = TimeAllocation(
        project_ratio=_normalize_percent_value(_to_float(alloc_data.get("项目拜访占比"))),
        customer_ratio=_normalize_percent_value(_to_float(alloc_data.get("客户拜访占比"))),
    )

    return Chapter7Data(
        metadata=metadata,
        total_visit=total_visit,
        project_visit=project_visit,
        time_allocation=time_allocation,
        warnings=warnings,
    )


def _normalize_chapter7_from_metric_rows(
    subject: Dict[str, Any],
    rows: List[Any],
    period: str = "",
) -> Chapter7Data:
    metadata = _extract_metadata(subject, period=period)
    warnings: List[str] = []
    metric_rows = [row for row in rows if isinstance(row, dict)]

    total_row = _find_metric_row(
        metric_rows,
        candidates=("拜访总频次", "拜访总次数", "总拜访频次", "总拜访次数", "拜访总数", "总拜访量", "拜访量"),
        include_groups=(("拜访", "总"), ("拜访量",)),
        exclude=("项目", "客户", "占比", "时间"),
        unit="次",
    )
    total_rate_row = _find_metric_row(
        metric_rows,
        candidates=("拜访总达成率", "总拜访达成率", "拜访达成率", "拜访量"),
        include_groups=(("拜访", "达成"), ("拜访量",)),
        exclude=("项目", "客户", "占比", "时间"),
        unit="%",
    )
    project_row = _find_metric_row(
        metric_rows,
        candidates=("项目拜访频次", "项目拜访次数", "项目拜访量", "项目拜访"),
        include_groups=(("项目", "拜访"),),
        exclude=("占比", "时间"),
        unit="次",
    )
    project_rate_row = _find_metric_row(
        metric_rows,
        candidates=("项目拜访达成率", "项目拜访"),
        include_groups=(("项目", "拜访", "达成"),),
        exclude=("占比", "时间"),
        unit="%",
    )
    project_ratio_row = _find_metric_row(
        metric_rows,
        candidates=("项目拜访占比", "项目时间占比"),
        include_groups=(("项目", "占比"),),
        exclude=(),
    )
    customer_ratio_row = _find_metric_row(
        metric_rows,
        candidates=("客户拜访占比", "客户时间占比"),
        include_groups=(("客户", "占比"),),
        exclude=(),
    )
    if project_ratio_row is None or customer_ratio_row is None:
        allocation_rows = [
            row for row in metric_rows
            if "时间分配" in _row_search_text(row) and _unit_of(row) == "%"
        ]
        if len(allocation_rows) >= 2:
            customer_ratio_row = customer_ratio_row or allocation_rows[0]
            project_ratio_row = project_ratio_row or allocation_rows[1]

    return Chapter7Data(
        metadata=metadata,
        total_visit=_normalize_visit_metric_from_rows(total_row, total_rate_row, warnings, "拜访总频次"),
        project_visit=_normalize_visit_metric_from_rows(project_row, project_rate_row, warnings, "项目拜访频次"),
        time_allocation=TimeAllocation(
            project_ratio=_extract_percent_metric_value(project_ratio_row),
            customer_ratio=_extract_percent_metric_value(customer_ratio_row),
        ),
        warnings=warnings,
    )


def _extract_subject(raw_data: Any) -> Dict[str, Any]:
    if raw_data is None:
        raise ChapterDataError(f"第七章数据清洗失败: 原始数据为 null。{EMPTY_DATA_MESSAGE}")
    if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
        return raw_data["data"]
    if isinstance(raw_data, dict):
        return raw_data
    raise ChapterDataError(f"第七章数据清洗失败: 原始数据不是对象。{EMPTY_DATA_MESSAGE}")


def _extract_metadata(subject: Dict[str, Any], period: str = "") -> Dict[str, Any]:
    keys = [
        "月份", "部门编码", "区域经理工号", "部门名称",
        "区域经理姓名", "岗位名称", "客户编码", "客户名称", "章节名称",
    ]
    metadata = {key: subject.get(key, "") for key in keys}
    if period:
        metadata["月份"] = period
    return metadata


def _normalize_visit_metric(data: Dict[str, Any], warnings: List[str], label: str) -> VisitMetric:
    if not data:
        warnings.append(f"第七章{label}数据未提供，已保留模板占位。")
        return VisitMetric()
    return VisitMetric(
        actual=_to_float(data.get("实际值")),
        target=_to_float(data.get("目标值")),
        achievement_rate=_to_float(data.get("达成率")),
        deduction_score=_to_float(data.get("扣分值")),
    )


def _normalize_visit_metric_from_rows(
    actual_row: Optional[Dict[str, Any]],
    rate_row: Optional[Dict[str, Any]],
    warnings: List[str],
    label: str,
) -> VisitMetric:
    actual_data = _metric_data(actual_row)
    rate_data = _metric_data(rate_row)
    if not actual_data:
        warnings.append(f"第七章{label}数据未提供，已保留模板占位。")
    if rate_row is not None and rate_row is not actual_row:
        rate_value = _to_float(rate_data.get("实际值"))
    else:
        rate_value = _to_float(actual_data.get("达成率"))
    return VisitMetric(
        actual=_to_float(actual_data.get("实际值")),
        target=_to_float(actual_data.get("目标值")),
        achievement_rate=_normalize_percent_value(rate_value),
        deduction_score=_to_float(actual_data.get("扣分值")),
    )


def _find_metric_row(
    rows: List[Dict[str, Any]],
    candidates: Tuple[str, ...],
    include_groups: Tuple[Tuple[str, ...], ...],
    exclude: Tuple[str, ...],
    unit: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    matched = []
    for row in rows:
        if unit and _unit_of(row) not in ("", unit):
            continue
        text = _row_search_text(row)
        if any(word in text for word in exclude):
            continue
        if any(candidate and candidate in text for candidate in candidates):
            matched.append(row)
    if matched:
        return _prefer_informative_metric_row(matched)

    matched = []
    for row in rows:
        if unit and _unit_of(row) not in ("", unit):
            continue
        text = _row_search_text(row)
        if any(word in text for word in exclude):
            continue
        if any(all(word in text for word in group) for group in include_groups):
            matched.append(row)
    return _prefer_informative_metric_row(matched)


def _prefer_informative_metric_row(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            _metric_abs_value(row) > 0,
            _metric_abs_value(row),
        ),
    )


def _metric_abs_value(row: Dict[str, Any]) -> float:
    value = _to_float(_metric_data(row).get("实际值"))
    return abs(value) if value is not None else 0.0


def _row_search_text(row: Dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("指标名称", "指标路径", "指标口径", "指标说明")
    )


def _metric_data(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    metric = row.get("指标数据")
    return metric if isinstance(metric, dict) else {}


def _unit_of(row: Dict[str, Any]) -> str:
    return str(_metric_data(row).get("单位") or "").strip()


def _extract_metric_value(row: Optional[Dict[str, Any]]) -> Optional[float]:
    metric = _metric_data(row)
    for key in ("实际值", "占比", "比率", "达成率"):
        value = _to_float(metric.get(key))
        if value is not None:
            return value
    return None


def _extract_percent_metric_value(row: Optional[Dict[str, Any]]) -> Optional[float]:
    return _normalize_percent_value(_extract_metric_value(row))


def _normalize_percent_value(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    normalized = value * 100 if abs(value) <= 10 else value
    return round(normalized, 1)


# ── Markdown 生成 ─────────────────────────────────────────────────────


def month_label(period: str) -> str:
    if len(period) >= 6 and period[-2:].isdigit():
        month = int(period[-2:])
        return f"{month}月"
    return "报告月"


def build_chapter7_markdown(
    chapter_data: Chapter7Data,
    action_guide_text: str = "",
) -> str:
    period = str(chapter_data.metadata.get("月份") or "")
    m_label = month_label(period)
    tv = chapter_data.total_visit
    pv = chapter_data.project_visit
    ta = chapter_data.time_allocation

    lines = [
        "# 七、行销行为",
        "",
        "## 7.1 拜访量",
        "",
        _build_visit_text(tv, pv, m_label),
        "",
        "## 7.2 时间分配",
        "",
        _build_time_allocation_text(ta),
    ]

    if action_guide_text:
        lines.append("")
        lines.append("## 7.3 行动指南")
        lines.append("")
        lines.append(f"◇ {action_guide_text}")

    if chapter_data.warnings:
        lines.extend(["", "<!-- " + "；".join(chapter_data.warnings) + " -->"])

    return "\n".join(lines).rstrip() + "\n"


def _build_visit_line(m: VisitMetric, label: str, m_label: str) -> str:
    if m.actual is None:
        return f"{m_label}{label}待补充"

    parts = [f"{m_label}{label} {_fmt_int(m.actual)}次"]

    if m.achievement_rate is not None:
        parts.append(f"，拜访达成率{_fmt_percent(m.achievement_rate)}")

    return "".join(parts)


def _build_visit_text(tv: VisitMetric, pv: VisitMetric, m_label: str) -> str:
    total_text = _build_visit_line(tv, "拜访总频次", m_label)
    project_text = _build_visit_line(pv, "项目拜访频次", "")
    return total_text + "。" + project_text + "。"


def _build_time_allocation_text(ta: TimeAllocation) -> str:
    if ta.project_ratio is None and ta.customer_ratio is None:
        return "时间分配数据暂未提供。"

    parts = []
    if ta.project_ratio is not None:
        parts.append(f"{_fmt_percent(ta.project_ratio)}用于项目拜访")
    if ta.customer_ratio is not None:
        parts.append(f"{_fmt_percent(ta.customer_ratio)}用于客户拜访")

    return "，".join(parts) + "。"


# ── 行动指南 ──────────────────────────────────────────────────────────


def build_chapter7_action_context(chapter_data: Chapter7Data) -> Dict[str, Any]:
    tv = chapter_data.total_visit
    pv = chapter_data.project_visit

    return {
        "metadata": {
            "月份": chapter_data.metadata.get("月份", ""),
            "区域经理工号": chapter_data.metadata.get("区域经理工号", ""),
            "区域经理姓名": chapter_data.metadata.get("区域经理姓名", ""),
        },
        "total_visit": {
            "actual": tv.actual,
            "target": tv.target,
            "achievement_rate": tv.achievement_rate,
            "gap": (tv.target - tv.actual) if (tv.target is not None and tv.actual is not None) else None,
            "deduction_score": tv.deduction_score,
        },
        "project_visit": {
            "actual": pv.actual,
            "target": pv.target,
            "achievement_rate": pv.achievement_rate,
            "gap": (pv.target - pv.actual) if (pv.target is not None and pv.actual is not None) else None,
            "deduction_score": pv.deduction_score,
        },
        "time_allocation": {
            "项目拜访占比": chapter_data.time_allocation.project_ratio,
            "客户拜访占比": chapter_data.time_allocation.customer_ratio,
        },
        "数据提示": chapter_data.warnings,
    }


def build_chapter7_stats(
    chapter_data: Chapter7Data,
    action_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    tv = chapter_data.total_visit
    pv = chapter_data.project_visit
    return {
        "接口月份": chapter_data.metadata.get("月份", ""),
        "拜访总频次": tv.actual,
        "拜访总达成率": tv.achievement_rate,
        "项目拜访频次": pv.actual,
        "项目拜访达成率": pv.achievement_rate,
        "项目拜访占比": chapter_data.time_allocation.project_ratio,
        "客户拜访占比": chapter_data.time_allocation.customer_ratio,
        "warnings": chapter_data.warnings,
        "cleaned_data": chapter_data.to_dict(),
        "action_context": action_context or build_chapter7_action_context(chapter_data),
    }


# ── Chapter7Generator 类 ──────────────────────────────────────────────


class Chapter7Generator:
    """第七章「行销行为」生成器。"""

    def __init__(
        self,
        data: Any,
        guideline: str = "",
        period: str = "",
        sale_id: Optional[str] = None,
        sale_name: Optional[str] = None,
        action_model: Optional[Any] = None,
        action_writer: Optional[Any] = None,
    ):
        self.raw_data = data
        self.guideline = guideline
        self.period = period
        self.sale_id = sale_id
        self.sale_name = sale_name
        self.action_model = action_model
        self.action_writer = action_writer

    def run(self) -> str:
        markdown, _stats = format_chapter7_data(self.raw_data, period=self.period)
        return markdown

    async def run_async(self) -> str:
        try:
            if self.action_model is None and self.action_writer is None:
                return self.run()
            markdown, _stats = await format_chapter7_data_with_ai(
                self.raw_data,
                period=self.period,
                model=self.action_model,
                action_writer=self.action_writer,
            )
            return markdown
        except Exception as e:
            logger.error(f"第七章生成失败: {e}")
            raise
