"""第七章生成器 - 行销行为。

第七章分析拜访量和时间分配。当前接口 MOUDLE 7 尚在开发中，
本文件先定义内部数据契约、条件展示逻辑和模板填充，后续只需要
把接口原始 JSON 转换到该契约即可继续复用渲染与报告生成逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging

from Data import EMPTY_DATA_MESSAGE, ChapterDataError

logger = logging.getLogger(__name__)

DEFAULT_CHAPTER7_ACTION_GUIDE = "日均拜访量不低于3次，月度达标60次。"


def _fmt_int(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return str(int(value))


def _fmt_percent(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


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
    action_guide_text = DEFAULT_CHAPTER7_ACTION_GUIDE

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
    stats["行动指南来源"] = "AI" if action_guide_text != DEFAULT_CHAPTER7_ACTION_GUIDE else "规则"
    return markdown, stats


# ── 数据标准化 ───────────────────────────────────────────────────────


def normalize_chapter7_data(raw_data: Any, period: str = "") -> Chapter7Data:
    subject = _extract_subject(raw_data)
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
        project_ratio=_to_float(alloc_data.get("项目拜访占比")),
        customer_ratio=_to_float(alloc_data.get("客户拜访占比")),
    )

    return Chapter7Data(
        metadata=metadata,
        total_visit=total_visit,
        project_visit=project_visit,
        time_allocation=time_allocation,
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
    if period and not metadata.get("月份"):
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
        "## 七、行销行为",
        "",
        "### 拜访量",
        "",
        _build_visit_text(tv, pv, m_label),
        "",
        "### 时间分配",
        "",
        _build_time_allocation_text(ta),
    ]

    guide = action_guide_text or DEFAULT_CHAPTER7_ACTION_GUIDE
    if guide:
        lines.append("")
        lines.append("### 行动指南：")
        lines.append("")
        lines.append(f"◇ {guide}")

    if chapter_data.warnings:
        lines.extend(["", "<!-- " + "；".join(chapter_data.warnings) + " -->"])

    return "\n".join(lines).rstrip() + "\n"


def _build_visit_line(m: VisitMetric, label: str, m_label: str) -> str:
    """构建单条拜访指标文本，处理批注[31]的隐藏规则。"""
    if m.actual is None:
        return f"{m_label}{label}数据暂未提供。"

    parts = [f"{m_label}{label} {_fmt_int(m.actual)}次"]

    if m.achievement_rate is not None:
        parts.append(f"，拜访达成率{_fmt_percent(m.achievement_rate)}")

    # 批注[31]: 达成率超百则不展示扣分和差额
    if m.achievement_rate is not None and m.achievement_rate >= 100:
        return "".join(parts) + "。"

    if m.deduction_score is not None:
        score = m.deduction_score
        parts.append(f"（扣绩效{_fmt_int(abs(score))}分）")

    if m.actual is not None and m.target is not None:
        gap = m.target - m.actual
        if gap > 0:
            parts.append(f"，还差{_fmt_int(gap)}次")

    return "".join(parts) + "。"


def _build_visit_text(tv: VisitMetric, pv: VisitMetric, m_label: str) -> str:
    total_text = _build_visit_line(tv, "拜访总频次", m_label)
    project_text = _build_visit_line(pv, "项目拜访频次", m_label)
    return total_text + " " + project_text


def _build_time_allocation_text(ta: TimeAllocation) -> str:
    if ta.project_ratio is None and ta.customer_ratio is None:
        return "时间分配数据暂未提供。"

    parts = []
    if ta.project_ratio is not None:
        parts.append(f"{_fmt_percent(ta.project_ratio * 100) if ta.project_ratio <= 1 else _fmt_percent(ta.project_ratio)}用于项目拜访")
    if ta.customer_ratio is not None:
        parts.append(f"{_fmt_percent(ta.customer_ratio * 100) if ta.customer_ratio <= 1 else _fmt_percent(ta.customer_ratio)}用于客户拜访")

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
