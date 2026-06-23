"""第八章生成器 - 总结。

第八章是综合总结章节，基于前七章的关键信号生成优势归纳、短板识别
和六维度核心策略。数据来源 MOUDLE 8，与其他章节统一走 POST 接口。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
import logging

from Data import EMPTY_DATA_MESSAGE, ChapterDataError

logger = logging.getLogger(__name__)

# ── 回退文案 ────────────────────────────────────────────────────────────

DEFAULT_ADVANTAGE_FALLBACK = "本期暂无特别突出的正向指标。"

DEFAULT_WEAKNESS_FALLBACK = "数据不足，无法自动生成短板分析。"

DIMENSION_FALLBACKS: Dict[str, str] = {
    "产品": "持续优化产品结构，关注增长品类。",
    "项目": "推进重点项目落地，提升单项目产出。",
    "渠道": "拓展渠道覆盖，提升渠道质量。",
    "客户": "维护核心客户关系，提升客均销量。",
    "应收": "加强应收账款管理，控制逾期与减值。",
    "打样": "控制打样费用，提升转化率。",
}

DIMENSION_ORDER = ["产品", "项目", "渠道", "客户", "应收", "打样"]


# ── 格式化工具 ──────────────────────────────────────────────────────────


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


def _to_int(value: Any) -> Optional[int]:
    v = _to_float(value)
    if v is None:
        return None
    return int(v)


# ── 数据契约 dataclasses ───────────────────────────────────────────────


@dataclass
class PerformanceSummary:
    score: Optional[float] = None
    rank_province: str = ""
    rank_bu: str = ""
    sales: Optional[float] = None
    profit: Optional[float] = None


@dataclass
class Chapter8Signal:
    dimension: str = ""
    dimension_label: str = ""
    metric_name: str = ""
    value_display: str = ""
    change_display: str = ""
    is_outstanding: bool = False
    severity: str = ""


@dataclass
class ProductDimension:
    top_growing: List[Dict[str, Any]] = field(default_factory=list)
    top_declining: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ProjectDimension:
    project_count: Optional[int] = None
    project_target: Optional[int] = None
    achievement_rate: Optional[float] = None
    single_project_revenue: Optional[float] = None
    yoy_change_pct: Optional[float] = None


@dataclass
class ChannelDimension:
    channel_count: Optional[int] = None
    channel_target: Optional[int] = None
    achievement_rate: Optional[float] = None
    yoy_change_pct: Optional[float] = None


@dataclass
class CustomerDimension:
    customer_count: Optional[int] = None
    customer_target: Optional[int] = None
    achievement_rate: Optional[float] = None
    avg_revenue_per_customer: Optional[float] = None
    yoy_change_pct: Optional[float] = None


@dataclass
class ReceivableDimension:
    overdue_amount: Optional[float] = None
    impairment_amount: Optional[float] = None
    finance_cost: Optional[float] = None


@dataclass
class SamplingDimension:
    sample_expense: Optional[float] = None
    yoy_direction: str = "flat"


@dataclass
class DimensionSummary:
    product: ProductDimension = field(default_factory=ProductDimension)
    project: ProjectDimension = field(default_factory=ProjectDimension)
    channel: ChannelDimension = field(default_factory=ChannelDimension)
    customer: CustomerDimension = field(default_factory=CustomerDimension)
    receivable: ReceivableDimension = field(default_factory=ReceivableDimension)
    sampling: SamplingDimension = field(default_factory=SamplingDimension)


@dataclass
class Chapter8Data:
    metadata: Dict[str, Any] = field(default_factory=dict)
    performance: PerformanceSummary = field(default_factory=PerformanceSummary)
    positive_signals: List[Chapter8Signal] = field(default_factory=list)
    negative_signals: List[Chapter8Signal] = field(default_factory=list)
    facts: List[Dict[str, Any]] = field(default_factory=list)
    dimension_summary: DimensionSummary = field(default_factory=DimensionSummary)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "performance": {
                "score": self.performance.score,
                "rank_province": self.performance.rank_province,
                "rank_bu": self.performance.rank_bu,
                "sales": self.performance.sales,
                "profit": self.performance.profit,
            },
            "positive_signals": [
                {
                    "dimension": s.dimension,
                    "dimension_label": s.dimension_label,
                    "metric_name": s.metric_name,
                    "value_display": s.value_display,
                    "change_display": s.change_display,
                    "is_outstanding": s.is_outstanding,
                }
                for s in self.positive_signals
            ],
            "negative_signals": [
                {
                    "dimension": s.dimension,
                    "dimension_label": s.dimension_label,
                    "metric_name": s.metric_name,
                    "value_display": s.value_display,
                    "change_display": s.change_display,
                    "severity": s.severity,
                }
                for s in self.negative_signals
            ],
            "facts": self.facts,
            "dimension_summary": {
                "产品": {
                    "top_growing": self.dimension_summary.product.top_growing,
                    "top_declining": self.dimension_summary.product.top_declining,
                },
                "项目": {
                    "project_count": self.dimension_summary.project.project_count,
                    "project_target": self.dimension_summary.project.project_target,
                    "achievement_rate": self.dimension_summary.project.achievement_rate,
                    "single_project_revenue": self.dimension_summary.project.single_project_revenue,
                    "yoy_change_pct": self.dimension_summary.project.yoy_change_pct,
                },
                "渠道": {
                    "channel_count": self.dimension_summary.channel.channel_count,
                    "channel_target": self.dimension_summary.channel.channel_target,
                    "achievement_rate": self.dimension_summary.channel.achievement_rate,
                    "yoy_change_pct": self.dimension_summary.channel.yoy_change_pct,
                },
                "客户": {
                    "customer_count": self.dimension_summary.customer.customer_count,
                    "customer_target": self.dimension_summary.customer.customer_target,
                    "achievement_rate": self.dimension_summary.customer.achievement_rate,
                    "avg_revenue_per_customer": self.dimension_summary.customer.avg_revenue_per_customer,
                    "yoy_change_pct": self.dimension_summary.customer.yoy_change_pct,
                },
                "应收": {
                    "overdue_amount": self.dimension_summary.receivable.overdue_amount,
                    "impairment_amount": self.dimension_summary.receivable.impairment_amount,
                    "finance_cost": self.dimension_summary.receivable.finance_cost,
                },
                "打样": {
                    "sample_expense": self.dimension_summary.sampling.sample_expense,
                    "yoy_direction": self.dimension_summary.sampling.yoy_direction,
                },
            },
            "warnings": self.warnings,
        }


# ── 主入口 ─────────────────────────────────────────────────────────────


def format_chapter8_data(
    raw_data: Any,
    period: str = "",
    advantage_text: Optional[str] = None,
    weakness_text: Optional[str] = None,
    strategy_lines: Optional[List[str]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """清洗第八章数据并生成正式 Markdown（纯规则版）。"""
    chapter_data = normalize_chapter8_data(raw_data, period=period)
    markdown = build_chapter8_markdown(
        chapter_data,
        advantage_text=advantage_text,
        weakness_text=weakness_text,
        strategy_lines=strategy_lines,
    )
    stats = build_chapter8_stats(chapter_data)
    stats["行动指南来源"] = "AI" if all(
        value is not None for value in (advantage_text, weakness_text, strategy_lines)
    ) else "规则"
    return markdown, stats


async def format_chapter8_data_with_ai(
    raw_data: Any,
    period: str = "",
    model: Optional[Any] = None,
    action_writer: Optional[Any] = None,
) -> Tuple[str, Dict[str, Any]]:
    """生成第八章 Markdown，优势/短板/核心策略走 AI 生成。

    AI 参与段落：优势、短板、核心策略（6 维度）。
    章节标题和结构由规则固定。
    未传入 model/action_writer、调用失败或输出为空时，回退到规则版。
    """
    chapter_data = normalize_chapter8_data(raw_data, period=period)
    context = build_chapter8_action_context(chapter_data)

    advantage_text = _build_rule_advantage(chapter_data)
    weakness_text = _build_rule_weakness(chapter_data)
    strategy_lines = _build_rule_strategies(chapter_data)

    if action_writer is not None:
        result = await action_writer.generate(
            action_context=context,
            fallback_advantage=advantage_text,
            fallback_weakness=weakness_text,
            fallback_strategies=strategy_lines,
        )
        advantage_text = result.get("advantage", advantage_text)
        weakness_text = result.get("weakness", weakness_text)
        strategy_lines = result.get("strategies", strategy_lines)
    elif model is not None:
        from ReportGenerator.chapter8_ai_writer import generate_chapter8_summary

        result = await generate_chapter8_summary(
            action_context=context,
            model=model,
            fallback_advantage=advantage_text,
            fallback_weakness=weakness_text,
            fallback_strategies=strategy_lines,
        )
        advantage_text = result.get("advantage", advantage_text)
        weakness_text = result.get("weakness", weakness_text)
        strategy_lines = result.get("strategies", strategy_lines)

    ai_used = (
        advantage_text != _build_rule_advantage(chapter_data)
        or weakness_text != _build_rule_weakness(chapter_data)
        or strategy_lines != _build_rule_strategies(chapter_data)
    )

    markdown = build_chapter8_markdown(
        chapter_data,
        advantage_text=advantage_text,
        weakness_text=weakness_text,
        strategy_lines=strategy_lines,
    )
    stats = build_chapter8_stats(chapter_data, action_context=context)
    stats["行动指南来源"] = "AI" if ai_used else "规则"
    return markdown, stats


# ── 数据标准化 ─────────────────────────────────────────────────────────


def normalize_chapter8_data(raw_data: Any, period: str = "") -> Chapter8Data:
    """将原始数据标准化为第八章内部契约。

    支持三类输入：
    1. 完整接口响应：{"code": 1, "data": {...}}。
    2. data 对象：{"月份": "...", "performance": {...}, ...}。
    3. 直接传入已结构化的字段。
    """
    subject = _extract_subject(raw_data)
    metadata = _extract_metadata(subject, period=period)
    warnings: List[str] = []

    performance = _normalize_performance(subject, warnings)
    positive_signals = _normalize_signals(subject, "positive_signals", warnings)
    negative_signals = _normalize_signals(subject, "negative_signals", warnings)
    facts = _safe_list(subject.get("facts"))
    dimension_summary = _normalize_dimension_summary(subject, warnings)

    return Chapter8Data(
        metadata=metadata,
        performance=performance,
        positive_signals=positive_signals,
        negative_signals=negative_signals,
        facts=facts,
        dimension_summary=dimension_summary,
        warnings=warnings,
    )


def _extract_subject(raw_data: Any) -> Dict[str, Any]:
    if raw_data is None:
        raise ChapterDataError(f"第八章数据清洗失败: 原始数据为 null。{EMPTY_DATA_MESSAGE}")
    if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
        return raw_data["data"]
    if isinstance(raw_data, dict):
        return raw_data
    raise ChapterDataError(f"第八章数据清洗失败: 原始数据不是对象。{EMPTY_DATA_MESSAGE}")


def _extract_metadata(subject: Dict[str, Any], period: str = "") -> Dict[str, Any]:
    keys = [
        "月份", "部门编码", "区域经理工号", "部门名称",
        "区域经理姓名", "岗位名称", "客户编码", "客户名称", "章节名称",
    ]
    metadata = {key: subject.get(key, "") for key in keys}
    if period and not metadata.get("月份"):
        metadata["月份"] = period
    return metadata


def _normalize_performance(subject: Dict[str, Any], warnings: List[str]) -> PerformanceSummary:
    perf = subject.get("performance")
    if not isinstance(perf, dict):
        warnings.append("第八章绩效数据未提供。")
        return PerformanceSummary()

    score_data = perf.get("绩效得分")
    score = _to_float(score_data.get("实际值")) if isinstance(score_data, dict) else _to_float(score_data)

    rank_p_data = perf.get("省区内排名")
    rank_province = str(rank_p_data.get("实际值", "")) if isinstance(rank_p_data, dict) else str(rank_p_data or "")

    rank_bu_data = perf.get("事业部内排名")
    rank_bu = str(rank_bu_data.get("实际值", "")) if isinstance(rank_bu_data, dict) else str(rank_bu_data or "")

    sales_data = perf.get("销量")
    sales = _to_float(sales_data.get("实际值")) if isinstance(sales_data, dict) else _to_float(sales_data)

    profit_data = perf.get("分摊前利润")
    profit = _to_float(profit_data.get("实际值")) if isinstance(profit_data, dict) else _to_float(profit_data)

    return PerformanceSummary(
        score=score,
        rank_province=rank_province,
        rank_bu=rank_bu,
        sales=sales,
        profit=profit,
    )


def _normalize_signals(subject: Dict[str, Any], key: str, warnings: List[str]) -> List[Chapter8Signal]:
    raw = subject.get(key)
    if not isinstance(raw, list):
        if key == "negative_signals":
            return []
        warnings.append(f"第八章{key}数据未提供。")
        return []

    signals = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        signals.append(
            Chapter8Signal(
                dimension=str(item.get("dimension") or ""),
                dimension_label=str(item.get("dimension_label") or item.get("dimension") or ""),
                metric_name=str(item.get("metric_name") or ""),
                value_display=str(item.get("value_display") or ""),
                change_display=str(item.get("change_display") or ""),
                is_outstanding=bool(item.get("is_outstanding", False)),
                severity=str(item.get("severity") or ""),
            )
        )
    return signals


def _normalize_dimension_summary(subject: Dict[str, Any], warnings: List[str]) -> DimensionSummary:
    ds = subject.get("dimension_summary")
    if not isinstance(ds, dict):
        warnings.append("第八章维度汇总数据未提供，策略回退到通用文案。")
        return DimensionSummary()

    return DimensionSummary(
        product=_normalize_product_dim(ds.get("产品"), warnings),
        project=_normalize_project_dim(ds.get("项目"), warnings),
        channel=_normalize_channel_dim(ds.get("渠道"), warnings),
        customer=_normalize_customer_dim(ds.get("客户"), warnings),
        receivable=_normalize_receivable_dim(ds.get("应收"), warnings),
        sampling=_normalize_sampling_dim(ds.get("打样"), warnings),
    )


def _normalize_product_dim(data: Any, warnings: List[str]) -> ProductDimension:
    if not isinstance(data, dict):
        return ProductDimension()
    return ProductDimension(
        top_growing=_safe_list(data.get("top_growing")),
        top_declining=_safe_list(data.get("top_declining")),
    )


def _normalize_project_dim(data: Any, warnings: List[str]) -> ProjectDimension:
    if not isinstance(data, dict):
        return ProjectDimension()
    pc = data.get("project_count")
    return ProjectDimension(
        project_count=_to_int(pc.get("实际值")) if isinstance(pc, dict) else _to_int(pc),
        project_target=_to_int(data.get("project_target")),
        achievement_rate=_to_float(data.get("achievement_rate")),
        single_project_revenue=_extract_nested_float(data, "single_project_revenue", "实际值"),
        yoy_change_pct=_to_float(data.get("yoy_change_pct")),
    )


def _normalize_channel_dim(data: Any, warnings: List[str]) -> ChannelDimension:
    if not isinstance(data, dict):
        return ChannelDimension()
    cc = data.get("channel_count")
    return ChannelDimension(
        channel_count=_to_int(cc.get("实际值")) if isinstance(cc, dict) else _to_int(cc),
        channel_target=_to_int(data.get("channel_target")),
        achievement_rate=_to_float(data.get("achievement_rate")),
        yoy_change_pct=_to_float(data.get("yoy_change_pct")),
    )


def _normalize_customer_dim(data: Any, warnings: List[str]) -> CustomerDimension:
    if not isinstance(data, dict):
        return CustomerDimension()
    cc = data.get("customer_count")
    return CustomerDimension(
        customer_count=_to_int(cc.get("实际值")) if isinstance(cc, dict) else _to_int(cc),
        customer_target=_to_int(data.get("customer_target")),
        achievement_rate=_to_float(data.get("achievement_rate")),
        avg_revenue_per_customer=_extract_nested_float(data, "avg_revenue_per_customer", "实际值"),
        yoy_change_pct=_to_float(data.get("yoy_change_pct")),
    )


def _normalize_receivable_dim(data: Any, warnings: List[str]) -> ReceivableDimension:
    if not isinstance(data, dict):
        return ReceivableDimension()
    return ReceivableDimension(
        overdue_amount=_extract_nested_float(data, "overdue_amount", "实际值"),
        impairment_amount=_extract_nested_float(data, "impairment_amount", "实际值"),
        finance_cost=_extract_nested_float(data, "finance_cost", "实际值"),
    )


def _normalize_sampling_dim(data: Any, warnings: List[str]) -> SamplingDimension:
    if not isinstance(data, dict):
        return SamplingDimension()
    return SamplingDimension(
        sample_expense=_extract_nested_float(data, "sample_expense", "实际值"),
        yoy_direction=str(data.get("yoy_direction", "flat")).strip(),
    )


def _extract_nested_float(data: Any, outer_key: str, inner_key: str) -> Optional[float]:
    if not isinstance(data, dict):
        return None
    inner = data.get(outer_key)
    if isinstance(inner, dict):
        return _to_float(inner.get(inner_key))
    return _to_float(inner)


def _safe_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


# ── Markdown 生成 ─────────────────────────────────────────────────────


def build_chapter8_markdown(
    chapter_data: Chapter8Data,
    advantage_text: str = "",
    weakness_text: str = "",
    strategy_lines: Optional[List[str]] = None,
) -> str:
    """生成第八章正式 Markdown。"""
    if strategy_lines is None:
        strategy_lines = _build_rule_strategies(chapter_data)
    if not advantage_text:
        advantage_text = _build_rule_advantage(chapter_data)
    if not weakness_text:
        weakness_text = _build_rule_weakness(chapter_data)

    lines = [
        "## 八、总结",
        "",
        f"优势：{advantage_text}",
        "",
        f"短板：{weakness_text}",
        "",
        "核心策略：",
    ]

    for s in strategy_lines:
        lines.append(f"{str(s).rstrip('。；; ')}；")

    # 最后一行策略去掉分号，改为句号
    if lines and lines[-1].endswith("；"):
        lines[-1] = lines[-1][:-1] + "。"

    if chapter_data.warnings:
        lines.extend(["", "<!-- " + "；".join(chapter_data.warnings) + " -->"])

    return "\n".join(lines).rstrip() + "\n"


# ── 规则版文案 ─────────────────────────────────────────────────────────


def _build_rule_advantage(chapter_data: Chapter8Data) -> str:
    """基于正向信号生成优势文案（规则版）。"""
    if not chapter_data.positive_signals:
        return DEFAULT_ADVANTAGE_FALLBACK

    outstanding = [s for s in chapter_data.positive_signals if s.is_outstanding]
    others = [s for s in chapter_data.positive_signals if not s.is_outstanding]

    parts = []

    # 绩效
    perf = chapter_data.performance
    if perf.score is not None and perf.score >= 100:
        parts.append(f"绩效优秀（{int(perf.score)}分）")

    # 特别突出的信号优先
    for s in outstanding[:4]:
        label = _build_signal_label(s)
        if label:
            parts.append(label)

    # 其他正向信号
    for s in others[:3]:
        label = _build_signal_label(s)
        if label and label not in parts:
            parts.append(label)

    if not parts:
        return DEFAULT_ADVANTAGE_FALLBACK

    return "、".join(parts[:6]) + "。"


def _build_rule_weakness(chapter_data: Chapter8Data) -> str:
    """基于负向信号生成短板文案（规则版）。"""
    if not chapter_data.negative_signals:
        return DEFAULT_WEAKNESS_FALLBACK

    # 高严重性优先
    high = [s for s in chapter_data.negative_signals if s.severity == "high"]
    medium = [s for s in chapter_data.negative_signals if s.severity != "high"]

    parts = []
    for s in (high + medium)[:5]:
        label = _build_negative_label(s)
        if label:
            parts.append(label)

    if not parts:
        return DEFAULT_WEAKNESS_FALLBACK

    return "、".join(parts) + "。"


def _build_signal_label(s: Chapter8Signal) -> str:
    """构建正向信号标签文本。"""
    if s.change_display and s.metric_name and s.value_display:
        return f"{s.metric_name}{s.value_display}（{s.change_display}）"
    if s.change_display and s.metric_name:
        return f"{s.metric_name}（{s.change_display}）"
    if s.metric_name and s.value_display:
        return f"{s.metric_name}{s.value_display}"
    if s.metric_name:
        return s.metric_name
    return ""


def _build_negative_label(s: Chapter8Signal) -> str:
    """构建负向信号标签文本。"""
    if s.metric_name and s.change_display:
        return f"{s.metric_name}{s.change_display}"
    if s.metric_name and s.value_display:
        return f"{s.metric_name}{s.value_display}"
    if s.metric_name:
        return s.metric_name
    return ""


def _build_rule_strategies(chapter_data: Chapter8Data) -> List[str]:
    """基于维度汇总生成六维度核心策略（规则版）。"""
    ds = chapter_data.dimension_summary
    strategies = []

    for dim in DIMENSION_ORDER:
        s = _build_dim_strategy(dim, ds)
        strategies.append(s)

    return strategies


def _build_dim_strategy(dim: str, ds: DimensionSummary) -> str:
    """为单个维度生成规则版策略文案。"""
    if dim == "产品":
        return _product_strategy(ds.product)
    if dim == "项目":
        return _project_strategy(ds.project)
    if dim == "渠道":
        return _channel_strategy(ds.channel)
    if dim == "客户":
        return _customer_strategy(ds.customer)
    if dim == "应收":
        return _receivable_strategy(ds.receivable)
    if dim == "打样":
        return _sampling_strategy(ds.sampling)
    return f"{dim}：{DIMENSION_FALLBACKS.get(dim, '持续优化。')}"


def _product_strategy(pd: ProductDimension) -> str:
    growing_names = [p.get("product_name", "") for p in pd.top_growing[:2] if p.get("product_name")]
    declining_names = [p.get("product_name", "") for p in pd.top_declining[:2] if p.get("product_name")]

    parts = ["产品："]
    if growing_names:
        parts.append(f"主推{'、'.join(growing_names)}")
    if declining_names:
        parts.append(f"，关注{'、'.join(declining_names)}下滑趋势")
    if len(parts) == 1:
        parts.append(DIMENSION_FALLBACKS["产品"])
    return "".join(parts)


def _project_strategy(pd: ProjectDimension) -> str:
    parts = ["项目："]
    if pd.project_count is not None:
        if pd.project_target is not None:
            parts.append(f"年度出货项目{pd.project_count}/{pd.project_target}个，加快重点项目转化")
        else:
            parts.append(f"推进{pd.project_count}个出货项目落地")
        if pd.single_project_revenue is not None:
            parts.append(f"，提升单项目销量（当前{pd.single_project_revenue}万）")
    else:
        parts.append(DIMENSION_FALLBACKS["项目"])
    return "".join(parts)


def _channel_strategy(cd: ChannelDimension) -> str:
    parts = ["渠道："]
    if cd.channel_count is not None:
        if cd.channel_target is not None:
            parts.append(f"招商生效客户{cd.channel_count}/{cd.channel_target}家，强化线索转化和过程管理")
        else:
            parts.append(f"当前{cd.channel_count}个渠道，持续拓展有效覆盖")
    else:
        parts.append(DIMENSION_FALLBACKS["渠道"])
    return "".join(parts)


def _customer_strategy(cd: CustomerDimension) -> str:
    parts = ["客户："]
    if cd.customer_count is not None:
        if cd.customer_target is not None:
            parts.append(f"存量生效客户{cd.customer_count}/{cd.customer_target}个，聚焦客户激活与复购提升")
        else:
            parts.append(f"维护{cd.customer_count}个产销客户")
        if cd.avg_revenue_per_customer is not None:
            parts.append(f"，提升客均销量（当前{cd.avg_revenue_per_customer}万）")
    else:
        parts.append(DIMENSION_FALLBACKS["客户"])
    return "".join(parts)


def _receivable_strategy(rd: ReceivableDimension) -> str:
    parts = ["应收："]
    if rd.overdue_amount is not None:
        parts.append(f"逾期{rd.overdue_amount}万元需加大清收")
        if rd.impairment_amount is not None and rd.impairment_amount > 0:
            parts.append(f"，减值{rd.impairment_amount}万需控制新增")
    elif rd.impairment_amount is not None:
        parts.append(f"控制减值损失，当前{rd.impairment_amount}万")
    else:
        parts.append(DIMENSION_FALLBACKS["应收"])
    if rd.finance_cost is not None:
        parts.append(f"，资金费用{int(rd.finance_cost)}元需降低占用")
    return "".join(parts)


def _sampling_strategy(sd: SamplingDimension) -> str:
    parts = ["打样："]
    if sd.sample_expense is not None:
        parts.append(f"费用{int(sd.sample_expense)}元")
        if sd.yoy_direction == "up":
            parts.append("同比增加，需评估转化效率")
        elif sd.yoy_direction == "down":
            parts.append("同比下降，保持效率")
        elif sd.yoy_direction == "unknown":
            parts.append("，缺少可比同期数据，需建立转化跟踪")
        else:
            parts.append("，关注投入产出比")
    else:
        parts.append(DIMENSION_FALLBACKS["打样"])
    return "".join(parts)


# ── 行动上下文 ─────────────────────────────────────────────────────────


def build_chapter8_action_context(chapter_data: Chapter8Data) -> Dict[str, Any]:
    """构造供 AI 生成使用的结构化上下文。"""
    return {
        "metadata": {
            "月份": chapter_data.metadata.get("月份", ""),
            "区域经理工号": chapter_data.metadata.get("区域经理工号", ""),
            "区域经理姓名": chapter_data.metadata.get("区域经理姓名", ""),
            "部门名称": chapter_data.metadata.get("部门名称", ""),
        },
        "performance": {
            "score": chapter_data.performance.score,
            "rank_province": chapter_data.performance.rank_province,
            "rank_bu": chapter_data.performance.rank_bu,
            "sales": chapter_data.performance.sales,
            "profit": chapter_data.performance.profit,
        },
        "positive_signals": [
            {
                "dimension": s.dimension,
                "dimension_label": s.dimension_label,
                "metric_name": s.metric_name,
                "value_display": s.value_display,
                "change_display": s.change_display,
                "is_outstanding": s.is_outstanding,
            }
            for s in chapter_data.positive_signals
        ],
        "negative_signals": [
            {
                "dimension": s.dimension,
                "dimension_label": s.dimension_label,
                "metric_name": s.metric_name,
                "value_display": s.value_display,
                "change_display": s.change_display,
                "severity": s.severity,
            }
            for s in chapter_data.negative_signals
        ],
        "facts": chapter_data.facts,
        "dimension_summary": chapter_data.to_dict()["dimension_summary"],
        "数据提示": chapter_data.warnings,
    }


def build_chapter8_stats(
    chapter_data: Chapter8Data,
    action_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "接口月份": chapter_data.metadata.get("月份", ""),
        "绩效得分": chapter_data.performance.score,
        "正向信号数": len(chapter_data.positive_signals),
        "负向信号数": len(chapter_data.negative_signals),
        "warnings": chapter_data.warnings,
        "cleaned_data": chapter_data.to_dict(),
        "action_context": action_context or build_chapter8_action_context(chapter_data),
    }


# ── Chapter8Generator 类 ──────────────────────────────────────────────


class Chapter8Generator:
    """第八章「总结」生成器。"""

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
        markdown, _stats = format_chapter8_data(self.raw_data, period=self.period)
        return markdown

    async def run_async(self) -> str:
        try:
            if self.action_model is None and self.action_writer is None:
                return self.run()
            markdown, _stats = await format_chapter8_data_with_ai(
                self.raw_data,
                period=self.period,
                model=self.action_model,
                action_writer=self.action_writer,
            )
            return markdown
        except Exception as e:
            logger.error(f"第八章生成失败: {e}")
            raise
