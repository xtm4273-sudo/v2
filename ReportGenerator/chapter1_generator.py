"""第一章生成器 - 绩效得分与预警。

第一章严格按 V5 范本文档和批注规则生成，不接入 AI。真实接口未完成前，
本模块先提供稳定的内部数据结构、接口映射占位和确定性计算逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

from Data import EMPTY_DATA_MESSAGE, ChapterDataError


@dataclass
class RankValue:
    actual: Optional[float] = None
    unit: str = ""
    province_rank: Optional[int] = None
    province_total: Optional[int] = None
    business_rank: Optional[int] = None
    business_total: Optional[int] = None


@dataclass
class PerformanceItem:
    name: str
    actual: Optional[float] = None
    target: Optional[float] = None
    achievement_rate: Optional[float] = None
    deduction: Optional[float] = None
    weight: Optional[float] = None
    monthly_score: Optional[float] = None


@dataclass
class QuarterBonusWarning:
    sales_actual: Optional[float] = None
    sales_target: Optional[float] = None
    achievement_rate: Optional[float] = None
    distance_to_80: Optional[float] = None
    distance_to_same_period: Optional[float] = None
    distance_to_100: Optional[float] = None
    expected_bonus: Optional[float] = None
    overdue_amount: Optional[float] = None
    due_amount: Optional[float] = None
    potential_overdue: Optional[float] = None
    same_period_overdue: Optional[float] = None
    overdue_limit: Optional[float] = None


@dataclass
class YearEndProfitWarning:
    accumulated_profit: Optional[float] = None
    bonus_base: Optional[float] = None


@dataclass
class Chapter1Data:
    metadata: Dict[str, Any] = field(default_factory=dict)
    performance_score: RankValue = field(default_factory=RankValue)
    sales: RankValue = field(default_factory=RankValue)
    profit: RankValue = field(default_factory=RankValue)
    underperforming_items: List[PerformanceItem] = field(default_factory=list)
    quarter_bonus: QuarterBonusWarning = field(default_factory=QuarterBonusWarning)
    year_end_profit: YearEndProfitWarning = field(default_factory=YearEndProfitWarning)
    warnings: List[str] = field(default_factory=list)
    field_sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "performance_score": self.performance_score.__dict__,
            "sales": self.sales.__dict__,
            "profit": self.profit.__dict__,
            "underperforming_items": [item.__dict__ for item in self.underperforming_items],
            "quarter_bonus": self.quarter_bonus.__dict__,
            "year_end_profit": self.year_end_profit.__dict__,
            "warnings": self.warnings,
            "field_sources": self.field_sources,
        }


CHAPTER1_FIELD_MAP: Dict[str, Dict[str, Any]] = {
    "chapter1.performance_score.actual": {
        "match": {"指标名称": "绩效总分"},
        "value_path": ("指标数据", "实际值"),
        "unit_path": ("指标数据", "单位"),
        "target": ("performance_score", "actual"),
        "required": True,
        "fallback": [
            {"match": {"指标名称": "绩效得分"}, "value_path": ("指标数据", "实际值"), "unit_path": ("指标数据", "单位")},
            {"match": {"指标名称": "月平均绩效得分（不含其他奖惩）"}, "value_path": ("指标数据", "实际值"), "unit_path": ("指标数据", "单位")},
        ],
    },
    "chapter1.rank_table.performance_province_rank": {
        "match": {"指标名称": "绩效总分"},
        "value_path": ("指标数据", "省区排名"),
        "target": ("performance_score", "province_rank"),
        "required": True,
        "fallback": [
            {"match": {"指标名称": "绩效得分"}, "value_path": ("指标数据", "省区排名")},
            {"match": {"指标名称": "月平均绩效得分（不含其他奖惩）"}, "value_path": ("指标数据", "省区排名")},
        ],
    },
    "chapter1.rank_table.performance_business_rank": {
        "match": {"指标名称": "绩效总分"},
        "value_path": ("指标数据", "部门排名"),
        "target": ("performance_score", "business_rank"),
        "required": True,
        "fallback": [
            {"match": {"指标名称": "绩效得分"}, "value_path": ("指标数据", "事业部排名")},
            {"match": {"指标名称": "月平均绩效得分（不含其他奖惩）"}, "value_path": ("指标数据", "部门排名")},
        ],
    },
    "chapter1.rank_table.sales_amount": {
        "match": {"指标名称": "销量", "指标数据.日期类型": "年"},
        "value_path": ("指标数据", "实际值"),
        "unit_path": ("指标数据", "单位"),
        "target": ("sales", "actual"),
        "required": True,
    },
    "chapter1.rank_table.sales_province_rank": {
        "match": {"指标名称": "销量排名-省区"},
        "value_path": ("指标数据", "省区排名"),
        "target": ("sales", "province_rank"),
        "required": True,
    },
    "chapter1.rank_table.sales_business_rank": {
        "match": {"指标名称": "销量排名-事业部"},
        "value_path": ("指标数据", "部门排名"),
        "target": ("sales", "business_rank"),
        "required": True,
    },
    "chapter1.rank_table.profit_amount": {
        "match": {"指标名称": "本年累计分摊前利润", "指标数据.日期类型": "年"},
        "value_path": ("指标数据", "实际值"),
        "unit_path": ("指标数据", "单位"),
        "target": ("profit", "actual"),
        "required": True,
    },
    "chapter1.rank_table.profit_province_rank": {
        "match": {"指标名称": "分摊前利润排名-省区"},
        "value_path": ("指标数据", "省区排名"),
        "target": ("profit", "province_rank"),
        "required": True,
    },
    "chapter1.rank_table.profit_business_rank": {
        "match": {"指标名称": "分摊前利润排名-事业部"},
        "value_path": ("指标数据", "部门排名"),
        "target": ("profit", "business_rank"),
        "required": True,
    },
    "chapter1.quarter_bonus.sales_actual": {
        "match": {"指标名称": "个人季度实际销量", "指标数据.日期类型": "季"},
        "select": "unique_value",
        "value_path": ("指标数据", "实际值"),
        "target": ("quarter_bonus", "sales_actual"),
        "required": False,
    },
    "chapter1.quarter_bonus.achievement_rate": {
        "match": {"指标名称": "个人季度实际销量", "指标数据.日期类型": "季"},
        "select": "unique_value",
        "value_path": ("指标数据", "达成率"),
        "target": ("quarter_bonus", "achievement_rate"),
        "transform": "rate",
        "required": False,
    },
    "chapter1.quarter_bonus.overdue_amount": {
        "match": {"指标名称": "截止月底逾期金额"},
        "value_path": ("指标数据", "实际值"),
        "target": ("quarter_bonus", "overdue_amount"),
        "required": False,
    },
    "chapter1.quarter_bonus.due_amount": {
        "match": {"指标名称": "本季度预计到期款"},
        "value_path": ("指标数据", "实际值"),
        "target": ("quarter_bonus", "due_amount"),
        "required": False,
    },
    "chapter1.quarter_bonus.same_period_overdue": {
        "match": {"指标名称": "25年同期逾期金额"},
        "value_path": ("指标数据", "实际值"),
        "target": ("quarter_bonus", "same_period_overdue"),
        "required": False,
    },
    "chapter1.year_end_profit.accumulated_profit": {
        "match": {"指标名称": "本年累计分摊前利润", "指标数据.日期类型": "年"},
        "value_path": ("指标数据", "实际值"),
        "target": ("year_end_profit", "accumulated_profit"),
        "required": True,
        "fallback": [
            {"match": {"指标名称": "本年累计分摊前利润"}, "value_path": ("指标数据", "实际值")},
        ],
    },
    "chapter1.year_end_profit.bonus_base": {
        "match": {"指标名称": "奖金基数", "指标数据.日期类型": "年"},
        "value_path": ("指标数据", "实际值"),
        "target": ("year_end_profit", "bonus_base"),
        "required": False,
        "fallback": [
            {"match": {"指标名称": "奖金基数"}, "value_path": ("指标数据", "实际值")},
        ],
    },
}


# 数据集当前未提供有效权重；按报告截止月使用不晚于该月的最新配置。
PERFORMANCE_WEIGHTS_BY_MONTH: Dict[str, Dict[str, float]] = {
    "202605": {
        "招商生效": 50,
        "个人销量": 30,
        "有效出货项目数": 10,
        "品牌入库": 10,
    }
}


def format_chapter1_data(raw_data: Any, period: str = "") -> Tuple[str, Dict[str, Any]]:
    """清洗第一章数据并生成 Markdown。"""
    chapter_data = normalize_chapter1_data(raw_data, period=period)
    markdown = build_chapter1_markdown(chapter_data, period=period)
    stats = build_chapter1_stats(chapter_data)
    return markdown, stats


def normalize_chapter1_data(raw_data: Any, period: str = "") -> Chapter1Data:
    """把未来接口响应或 fixture 标准化为第一章内部结构。"""
    subject = _extract_subject(raw_data)
    rows = _extract_chapter_rows(subject)
    if not rows:
        raise ChapterDataError(f"第一章数据清洗失败: 原始章节数据为空。{EMPTY_DATA_MESSAGE}")

    data = Chapter1Data(
        metadata={
            "month": subject.get("月份", period),
            "department_name": subject.get("部门名称", ""),
            "operation_department": subject.get("经营部名称") or subject.get("城市经营部") or "",
            "manager_id": subject.get("区域经理工号", ""),
            "manager_name": subject.get("区域经理姓名", ""),
            "chapter_name": subject.get("章节名称", "一、绩效得分与预警"),
        }
    )
    _apply_chapter1_field_mapping(rows, data)
    _apply_quarter_bonus_detail_mapping(rows, data)
    _apply_underperforming_items_mapping(rows, data)
    _apply_performance_weight_config(data, period or subject.get("月份", ""))

    if data.performance_score.actual is None:
        data.warnings.append("缺少绩效得分")
    return data


def build_chapter1_markdown(chapter_data: Chapter1Data, period: str = "") -> str:
    """按 V5 范本第一章固定结构生成 Markdown。"""
    month = _month_from_period(period or chapter_data.metadata.get("month"))
    ytd_label = f"1-{month}月" if month else "累计"
    title_period = _title_period(period or chapter_data.metadata.get("month"))
    operation_department = chapter_data.metadata.get("operation_department") or "经营部（接口未提供）"

    lines: List[str] = [
        f"{operation_department}区域经理{title_period}经营分析报告",
        "",
        "# 一、绩效得分与预警",
        "",
        _build_rank_table(chapter_data),
        "",
        "说明：此处销量含双算，与绩效评分同口径",
        "",
        "## 1.1 绩效得分情况",
        "",
        _build_performance_table(chapter_data),
        "",
        "## 1.2 本季度目标达成奖预警",
        "",
        "季度目标达成奖=个人季度实际销量×0.6%×个人季度销量达成率",
        "",
        _build_quarter_bonus_table(chapter_data, month),
        "",
        "## 1.3 年终利润达成奖预警",
        "",
        "年终利润达成奖=个人年度分摊前利润绝对值对应的奖金基数*个人销量达成率（上限1.2倍）",
        "",
        _build_year_end_profit_text(chapter_data, month),
        "",
        "请注意：",
        "",
        "若本年销量出现负增长，则年终奖总额=奖金基数*（1+销量达成增长率）。",
        "",
        "对于老员工，当年度个人销量绝对值不低于400万，若低于400万则年终奖清零。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def build_chapter1_stats(chapter_data: Chapter1Data) -> Dict[str, Any]:
    return {
        "有效未达百绩效项目数": len(chapter_data.underperforming_items),
        "绩效得分": chapter_data.performance_score.actual,
        "季度销量": chapter_data.quarter_bonus.sales_actual,
        "累计分摊前利润": chapter_data.year_end_profit.accumulated_profit,
        "cleaned_data": chapter_data.to_dict(),
        "warnings": chapter_data.warnings,
    }


def profit_bonus_base(profit: Optional[float]) -> Tuple[str, str]:
    """按年终利润达成奖阶梯返回当前奖金基数和下一档提示。"""
    if profit is None:
        return "待补充", "若到年底分摊前利润在60万-80万（含）之间，奖金基数为1.2。"

    brackets = [
        (20, "20万以下", 0),
        (40, "20万-40万（含）", 0.3),
        (60, "40万-60万（含）", 0.6),
        (80, "60万-80万（含）", 1.2),
        (100, "80万-100万（含）", 1.8),
        (120, "100万-120万（含）", 2.4),
        (140, "120万-140万（含）", 3.0),
        (160, "140万-160万（含）", 3.6),
        (180, "160万-180万（含）", 4.2),
        (200, "180万-200万（含）", 4.8),
        (220, "200万-220万（含）", 5.4),
        (240, "220万-240万（含）", 6.0),
        (260, "240万-260万（含）", 6.6),
        (280, "260万-280万（含）", 7.2),
        (300, "280万-300万（含）", 7.8),
        (320, "300万-320万（含）", 8.4),
        (340, "320万-340万（含）", 9.0),
        (360, "340万-360万（含）", 9.6),
        (380, "360万-380万（含）", 10.2),
        (400, "380万-400万（含）", 10.8),
    ]
    for index, (upper_bound, _label, base) in enumerate(brackets):
        if profit < upper_bound or (upper_bound == 400 and profit <= upper_bound):
            next_index = min(index + 1, len(brackets))
            if next_index < len(brackets):
                next_label, next_base = brackets[next_index][1], brackets[next_index][2]
            else:
                next_label, next_base = "400万以上", 12
            return _bonus_base_text(base), f"若到年底分摊前利润在{next_label}之间，奖金基数为{_bonus_base_text(next_base)}。"

    return _bonus_base_text(12), "若到年底分摊前利润在400万以上，奖金基数为12。"


def _bonus_base_text(value: Optional[float]) -> str:
    """1.3 中“奖金基数”按客户模板不展示“万”单位。"""
    return _fmt_number(value)


def _build_rank_table(chapter_data: Chapter1Data) -> str:
    return "\n".join(
        [
            f"|  | 绩效排名 | 销量{_rank_amount_text(chapter_data.sales)} | 分摊前利润{_rank_amount_text(chapter_data.profit)} |",
            "| --- | --- | --- | --- |",
            (
                f"| 省区内排名 | "
                f"{_rank_text(chapter_data.performance_score, 'province')} | "
                f"{_rank_text(chapter_data.sales, 'province')} | "
                f"{_rank_text(chapter_data.profit, 'province')} |"
            ),
            (
                f"| 事业部内排名 | "
                f"{_rank_text(chapter_data.performance_score, 'business')} | "
                f"{_rank_text(chapter_data.sales, 'business')} | "
                f"{_rank_text(chapter_data.profit, 'business')} |"
            ),
        ]
    )


def _build_performance_table(chapter_data: Chapter1Data) -> str:
    problem_names = "、".join(item.name for item in chapter_data.underperforming_items)
    if problem_names:
        detail_text = f"未达百绩效项目：{problem_names}"
    elif chapter_data.performance_score.actual is not None and chapter_data.performance_score.actual < 100:
        detail_text = "未达百绩效项目：待补充"
    else:
        detail_text = "未达百绩效项目：无"
    score_text = f"{_fmt_number(chapter_data.performance_score.actual)}分"
    top_text = _top_text(chapter_data.performance_score)
    if top_text:
        score_text += f"（{top_text}）"
    rows = [
        "| 月度绩效 | 完成情况 | 关键详情 |",
        "| --- | --- | --- |",
        (
            "| 月平均绩效得分（不含其他奖惩） | "
            f"{score_text} | "
            f"{detail_text} |"
        ),
    ]
    for item in chapter_data.underperforming_items:
        monthly_score_text = (
            f"{_fmt_number(item.monthly_score)}分"
            if item.monthly_score is not None
            else "待补充"
        )
        rows.append(
            f"| {item.name} | 得分率：{_fmt_number(item.achievement_rate)}% | "
            f"全年总扣分{_fmt_number(item.deduction)}分，"
            f"月平均得分{monthly_score_text}"
            f"（权重{_fmt_number(item.weight)}分） |"
        )
    if not chapter_data.underperforming_items and chapter_data.performance_score.actual is not None and chapter_data.performance_score.actual < 100:
        deduction = max(100 - chapter_data.performance_score.actual, 0)
        rows.append(
            "| 绩效总分 | "
            f"达成率：{_fmt_number(chapter_data.performance_score.actual)}% | "
            f"较100分差{_fmt_number(deduction)}分；接口未提供未达百绩效项目明细 |"
        )
    return "\n".join(rows)


def _build_quarter_bonus_table(chapter_data: Chapter1Data, month: Optional[int]) -> str:
    bonus = chapter_data.quarter_bonus
    potential_overdue = bonus.potential_overdue
    if potential_overdue is None:
        potential_overdue = _sum_optional(bonus.overdue_amount, bonus.due_amount)
    overdue_limit = bonus.overdue_limit
    if overdue_limit is None and bonus.same_period_overdue is not None:
        overdue_limit = float(Decimal(str(bonus.same_period_overdue)) * Decimal("0.7"))
    month_text = f"{month}月底" if month else "月底"
    next_year = _previous_year_suffix(chapter_data.metadata.get("month"))
    distance_100_text = _amount_or_pending(bonus.distance_to_100, precision=0)
    if bonus.expected_bonus is not None:
        distance_100_text += f"，预计奖金{_fmt_number(bonus.expected_bonus, 2)}万"

    return "\n".join(
        [
            "| 奖金影响因素 | 情形 | 数值 |",
            "| --- | --- | --- |",
            f"| 个人季度实际销量 | 本季度累计销量 | {_amount_or_pending(bonus.sales_actual, precision=0)} |",
            f"|  | 当前达成率 | {_percent_or_pending(bonus.achievement_rate, precision=1)} |",
            f"|  | 距离80%达成率（发放硬性条件）还差 | {_amount_or_pending(bonus.distance_to_80, precision=0)} |",
            f"|  | 距离同期销量持平（负增长将同比例打折）还差 | {_amount_or_pending(bonus.distance_to_same_period, precision=0)} |",
            f"|  | 距离100%达成率还差 | {distance_100_text} |",
            f"| 发放规则（与逾期金额同比挂钩） | 截止{month_text}逾期金额 | {_amount_or_pending(bonus.overdue_amount, precision=0)} |",
            f"|  | 本季度预计到期款 | {_amount_or_pending(bonus.due_amount, precision=0)} |",
            f"|  | 合计（潜在逾期总额） | {_amount_or_pending(potential_overdue, precision=0)} |",
            f"|  | {next_year}年同期逾期金额（含法诉，仅考虑{next_year}年同期，不考虑交接后的逾期） | {_amount_or_pending(bonus.same_period_overdue, precision=0)} |",
            f"|  | 逾期金额同比下降30%，本季度末逾期金额不超过（含法诉，仅考虑{next_year}年同期，不考虑交接后的逾期） | {_amount_or_pending(overdue_limit, precision=0)} |",
            f"|  | 本季度末逾期金额对应的各类情形 | {_overdue_rule_text()} |",
        ]
    )


def _build_year_end_profit_text(chapter_data: Chapter1Data, month: Optional[int]) -> str:
    profit = chapter_data.year_end_profit.accumulated_profit
    base, next_tip = profit_bonus_base(profit)
    if chapter_data.year_end_profit.bonus_base is not None:
        base = _bonus_base_text(chapter_data.year_end_profit.bonus_base)
    month_text = f"{month}月" if month else "当前"
    return f"截止{month_text}本年累计分摊前利润{_fmt_number(profit, 0)}万，奖金基数为{base}。{next_tip}"


def _overdue_rule_text() -> str:
    return (
        "当季度先发50%，剩余50%奖金与逾期金额挂钩，情形如下：<br>"
        "（1）0逾期则奖金100%发放；<br>"
        "（2）若存在逾期金额且同比下降30%以内，剩余奖金按逾期金额同比下降率*3发放。例如:员工A当季度逾期金额同比下降率为20%，则奖金发放比例为50%+50%*20%*3=80%；<br>"
        "（3）若存在逾期金额且同比下降超过30%（含），剩余奖金按100%发放，例如:员工B当季度逾期金额同比下降率为30%，则奖金发放比例为50%+50%=100%；<br>"
        "（4）如当季度逾期金额(含法务)占循环12个月销量占比低于2%(含)，则剩余奖金100%发放；例如:员工C循环12个月销量为800万，当季度逾期金额为15万，则占比为1.87%，对应剩余奖金发放比例为100%；<br>"
        "（5）如当季度有逾期且同比持平或增长，则剩余奖金延后发放并打折。如剩余奖金延后发放，则剩余奖金金额逐季度按0.85打折，顺延至年底的剩余奖金发放条件参照信用管理制度中年终奖发放条件）"
    )


def _amount_or_pending(value: Any, precision: Optional[int] = None) -> str:
    return "待补充" if value is None else f"{_fmt_number(value, precision)}万"


def _percent_or_pending(value: Any, precision: Optional[int] = None) -> str:
    return "待补充" if value is None else f"{_fmt_number(value, precision)}%"


def _extract_subject(raw_data: Any) -> Dict[str, Any]:
    if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
        return raw_data["data"]
    if isinstance(raw_data, dict):
        return raw_data
    if isinstance(raw_data, list):
        return {"章节数据": raw_data}
    raise ChapterDataError(f"第一章数据清洗失败: 原始数据不是有效对象。{EMPTY_DATA_MESSAGE}")


def _extract_chapter_rows(subject: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = subject.get("章节数据")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _apply_chapter1_field_mapping(rows: List[Dict[str, Any]], data: Chapter1Data) -> None:
    targets = {
        "performance_score": data.performance_score,
        "sales": data.sales,
        "profit": data.profit,
        "quarter_bonus": data.quarter_bonus,
        "year_end_profit": data.year_end_profit,
    }
    for field_id, rule in CHAPTER1_FIELD_MAP.items():
        result = _resolve_mapped_field(rows, rule)
        data.field_sources[field_id] = result
        if result.get("status") != "ok":
            if rule.get("required"):
                data.warnings.append(f"{field_id} 取数失败: {result.get('message', '未命中')}")
            continue

        target_name, attr = rule["target"]
        target = targets[target_name]
        value = result.get("value")
        if attr.endswith("_rank"):
            setattr(target, attr, _to_int(value))
            metric = result.get("metric") if isinstance(result.get("metric"), dict) else {}
            if attr == "province_rank":
                target.province_total = _to_int(metric.get("省区总人数") or metric.get("省区人数") or metric.get("省区总数"))
            elif attr == "business_rank":
                target.business_total = _to_int(metric.get("事业部总人数") or metric.get("部门总人数") or metric.get("事业部总数"))
        else:
            converted = _rate_value(value) if rule.get("transform") == "rate" else _to_float(value)
            setattr(target, attr, converted)
            unit = result.get("unit")
            if unit and hasattr(target, "unit"):
                target.unit = str(unit)


def _apply_quarter_bonus_detail_mapping(rows: List[Dict[str, Any]], data: Chapter1Data) -> None:
    """映射季度奖金明细。

    当前接口存在同名记录，因此用已提供数值间的关系做唯一性校验；
    报告展示值仍直接取选中记录的“实际值”。
    """
    records: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        metric = row.get("指标数据") if isinstance(row, dict) else None
        if not isinstance(metric, dict):
            continue
        path = _normalize_metric_path(str(row.get("指标路径") or ""))
        name = str(row.get("指标名称") or "").strip() or _path_leaf(path)
        records.append(
            {
                "index": index,
                "name": name,
                "path": path,
                "metric": metric,
                "actual": _to_float(metric.get("实际值")),
                "target": _to_float(metric.get("目标值")),
                "same_period": _to_float(metric.get("同期数")),
                "rate": _rate_value(metric.get("达成率")),
                "date_type": str(metric.get("日期类型") or "").strip(),
            }
        )

    def named(name: str) -> List[Dict[str, Any]]:
        return [
            record
            for record in records
            if record["actual"] is not None
            and (record["name"] == name or _path_contains_segment(record["path"], name))
        ]

    def under_path(path: str) -> List[Dict[str, Any]]:
        normalized = _normalize_metric_path(path)
        return [
            record
            for record in records
            if record["actual"] is not None
            and (record["path"] == normalized or record["path"].startswith(f"{normalized}-"))
        ]

    def closest(candidates: List[Dict[str, Any]], expected: Optional[float], tolerance: float = 0.02) -> Optional[Dict[str, Any]]:
        if expected is None or not candidates:
            return None
        ordered = sorted(candidates, key=lambda record: abs(record["actual"] - expected))
        if abs(ordered[0]["actual"] - expected) > tolerance:
            return None
        if len(ordered) > 1 and abs(ordered[0]["actual"] - expected) == abs(ordered[1]["actual"] - expected):
            return None
        return ordered[0]

    def assign(attr: str, record: Optional[Dict[str, Any]], value_key: str = "actual") -> None:
        field_id = f"chapter1.quarter_bonus.{attr}"
        if record is None:
            data.field_sources[field_id] = {"status": "missing", "message": "未找到唯一可校验的接口记录"}
            return
        value = record.get(value_key)
        setattr(data.quarter_bonus, attr, value)
        data.field_sources[field_id] = {
            "status": "ok",
            "source": f"章节数据[{record['index']}].指标数据.{'达成率' if value_key == 'rate' else '实际值'}",
            "record_index": record["index"],
            "value": value,
        }

    quarterly_sales = [
        record
        for record in under_path("一、绩效得分与预警-个人季度实际销量")
        if record["date_type"] == "季" and record["name"] in {"个人季度实际销量", "本季度累计销量"}
    ]
    actual_values = {record["actual"] for record in quarterly_sales if record["actual"] is not None}
    if len(actual_values) == 1:
        data.quarter_bonus.sales_actual = next(iter(actual_values))
    elif quarterly_sales:
        unit_records = [record for record in quarterly_sales if str(record["metric"].get("单位") or "") == "万元"]
        if len(unit_records) == 1:
            data.quarter_bonus.sales_actual = unit_records[0]["actual"]
    target_values = [record["target"] for record in quarterly_sales if record["target"] not in (None, 0)]
    if len(set(target_values)) == 1:
        data.quarter_bonus.sales_target = target_values[0]

    rate_records = [
        record for record in named("当前达成率")
        if record["date_type"] == "季" and record["rate"] not in (None, 0)
    ]
    if not rate_records:
        rate_records = [record for record in quarterly_sales if record["rate"] not in (None, 0)]
    rate_values = {record["rate"] for record in rate_records}
    if len(rate_values) == 1:
        assign("achievement_rate", rate_records[0], "rate")
        if data.quarter_bonus.sales_target is None and rate_records[0].get("target") not in (None, 0):
            data.quarter_bonus.sales_target = rate_records[0]["target"]
    elif not rate_records and quarterly_sales and {record["rate"] for record in quarterly_sales} == {0.0}:
        assign("achievement_rate", quarterly_sales[0], "rate")
    else:
        assign("achievement_rate", None, "rate")

    distance_80_records = named("距离80%达成率（发放硬性条件）")
    assign("distance_to_80", distance_80_records[0] if len(distance_80_records) == 1 else None)
    same_period_records = named("距离同期销量持平（负增长将同比例打折）")
    same_period_record = same_period_records[0] if len(same_period_records) == 1 else None
    if same_period_record is None and data.quarter_bonus.sales_actual is not None:
        same_period_values = [record["same_period"] for record in quarterly_sales if record["same_period"] is not None]
        if len(set(same_period_values)) == 1:
            same_period_record = {
                "index": -1,
                "actual": max(0.0, same_period_values[0] - data.quarter_bonus.sales_actual),
            }
    assign("distance_to_same_period", same_period_record)

    distance_100_parent_records = named("距离100%达成率还差")
    distance_100_records = [
        record
        for record in distance_100_parent_records
        if record["name"] in {"本季度累计销量还差", "距离100%达成率还差"}
    ]
    distance_expected = (
        data.quarter_bonus.sales_target - data.quarter_bonus.sales_actual
        if data.quarter_bonus.sales_target is not None and data.quarter_bonus.sales_actual is not None
        else None
    )
    distance_record = closest(distance_100_records, distance_expected)
    if distance_record is None and len(distance_100_records) >= 2:
        distance_record = max(distance_100_records, key=lambda record: record["actual"] or 0)
    assign("distance_to_100", distance_record)
    bonus_expected = (
        Decimal(str(data.quarter_bonus.sales_actual))
        * Decimal("0.006")
        * Decimal(str(data.quarter_bonus.achievement_rate))
        / Decimal("100")
        if data.quarter_bonus.sales_actual is not None and data.quarter_bonus.achievement_rate is not None
        else None
    )
    bonus_candidates = [
        record for record in distance_100_parent_records
        if record["name"] == "预计奖金"
    ]
    bonus_record = closest(bonus_candidates, float(bonus_expected) if bonus_expected is not None else None)
    if bonus_record is None and distance_record is not None:
        remaining_distance_100_records = [
            record for record in distance_100_parent_records if record["index"] != distance_record["index"]
        ]
        if remaining_distance_100_records:
            bonus_record = min(remaining_distance_100_records, key=lambda record: record["actual"] or 0)
    assign("expected_bonus", bonus_record)

    explicit_overdue = [
        record for record in records
        if record["actual"] is not None
        and record["name"].startswith("截止")
        and record["name"].endswith("月底逾期金额")
    ]
    rule_records = under_path("一、绩效得分与预警-发放规则（与逾期金额同比挂钩）")
    monthly_rule_records = [
        record for record in rule_records
        if record["date_type"] == "月" and record["name"] == "发放规则（与逾期金额同比挂钩）"
    ]
    overdue_record = (
        explicit_overdue[0]
        if len(explicit_overdue) == 1
        else monthly_rule_records[0] if len(monthly_rule_records) == 1 else None
    )
    assign("overdue_amount", overdue_record)

    seasonal_rule_records = [
        record for record in rule_records
        if record["date_type"] == "季"
        and record["name"] not in {"本季度预计到期款", "25年同期逾期金额"}
    ]
    potential_expected = (
        data.quarter_bonus.overdue_amount + data.quarter_bonus.due_amount
        if data.quarter_bonus.overdue_amount is not None and data.quarter_bonus.due_amount is not None
        else None
    )
    potential_record = closest(seasonal_rule_records, potential_expected)
    assign("potential_overdue", potential_record)
    limit_expected = (
        float(Decimal(str(data.quarter_bonus.same_period_overdue)) * Decimal("0.7"))
        if data.quarter_bonus.same_period_overdue is not None
        else None
    )
    limit_record = closest(
        [record for record in seasonal_rule_records if potential_record is None or record["index"] != potential_record["index"]],
        limit_expected,
    )
    assign("overdue_limit", limit_record)


def _apply_underperforming_items_mapping(rows: List[Dict[str, Any]], data: Chapter1Data) -> None:
    matched: List[Dict[str, Any]] = []
    monthly_score_records: List[Dict[str, Any]] = []
    item_keys: Dict[int, str] = {}
    for row_index, row in enumerate(rows):
        name = str(row.get("指标名称") or "").strip()
        path = str(row.get("指标路径") or "").strip()
        metric = row.get("指标数据") if isinstance(row, dict) else {}
        if not isinstance(metric, dict):
            continue
        if "未达百绩效项目" not in path:
            continue
        if _is_monthly_score_record(name, path):
            monthly_score_records.append(
                {
                    "record_index": row_index,
                    "source": f"章节数据[{row_index}].指标数据.实际值",
                    "actual": _to_float(metric.get("实际值")),
                    "achievement_rate": _rate_value(metric.get("达成率")),
                    "item_key": _performance_item_key(row, metric, allow_name=False),
                }
            )
            continue
        if name in {"月平均得分", "全年总扣分"} or "未达百绩效项目(扣分)" in path:
            continue

        item_key = _performance_item_key(row, metric, allow_name=True)
        item = _performance_item(name or item_key, metric)
        if item.achievement_rate is None:
            item.achievement_rate = _achievement_rate(item.actual, item.target)
        if item.achievement_rate is not None and item.achievement_rate < 100:
            data.underperforming_items.append(item)
            item_keys[id(item)] = item_key
            matched.append(
                {
                    "record_index": row_index,
                    "source": f"章节数据[{row_index}].指标数据",
                    "metric_name": name,
                    "metric": metric,
                }
            )

    monthly_score_matches: List[Dict[str, Any]] = []
    used_record_indexes = set()

    explicit_records_by_key: Dict[str, List[Dict[str, Any]]] = {}
    for record in monthly_score_records:
        item_key = record.get("item_key") or ""
        if item_key:
            explicit_records_by_key.setdefault(item_key, []).append(record)
    unkeyed_monthly_score_records = [
        record
        for record in monthly_score_records
        if not record.get("item_key") and record["actual"] is not None
    ]

    def assign_unkeyed_monthly_score(item: PerformanceItem, item_key: str) -> bool:
        sequential_index = len([
            match for match in monthly_score_matches
            if match.get("match_method") == "interface_order_fallback"
        ])
        if sequential_index >= len(unkeyed_monthly_score_records):
            return False
        selected = unkeyed_monthly_score_records[sequential_index]
        if selected["record_index"] in used_record_indexes:
            return False
        item.monthly_score = selected["actual"]
        used_record_indexes.add(selected["record_index"])
        monthly_score_matches.append(
            {
                "item_name": item.name,
                "record_index": selected["record_index"],
                "source": selected["source"],
                "value": selected["actual"],
                "match_method": "interface_order_fallback",
                "item_key": item_key,
            }
        )
        return True

    for item in data.underperforming_items:
        item_key = item_keys.get(id(item), _normalize_performance_item_key(item.name))
        explicit_candidates = [
            record
            for record in explicit_records_by_key.get(item_key, [])
            if record["actual"] is not None
            and record["record_index"] not in used_record_indexes
        ]
        if len(explicit_candidates) == 1:
            selected = explicit_candidates[0]
            item.monthly_score = selected["actual"]
            used_record_indexes.add(selected["record_index"])
            monthly_score_matches.append(
                {
                    "item_name": item.name,
                    "record_index": selected["record_index"],
                    "source": selected["source"],
                    "value": selected["actual"],
                    "match_method": "explicit_indicator",
                    "item_key": item_key,
                }
            )
            continue

        if item.achievement_rate is None:
            assign_unkeyed_monthly_score(item, item_key)
            continue
        candidates = [
            record
            for record in monthly_score_records
            if record["actual"] is not None
            and record["achievement_rate"] is not None
            and record["record_index"] not in used_record_indexes
            and abs(record["achievement_rate"] - item.achievement_rate) <= 1
        ]
        candidates.sort(key=lambda record: abs(record["achievement_rate"] - item.achievement_rate))
        if not candidates:
            assign_unkeyed_monthly_score(item, item_key)
            continue
        closest_distance = abs(candidates[0]["achievement_rate"] - item.achievement_rate)
        if sum(
            abs(record["achievement_rate"] - item.achievement_rate) == closest_distance
            for record in candidates
        ) != 1:
            assign_unkeyed_monthly_score(item, item_key)
            continue
        selected = candidates[0]
        item.monthly_score = selected["actual"]
        used_record_indexes.add(selected["record_index"])
        monthly_score_matches.append(
            {
                "item_name": item.name,
                "record_index": selected["record_index"],
                "source": selected["source"],
                "value": selected["actual"],
                "match_method": "achievement_rate_fallback",
                "item_key": item_key,
            }
        )

    data.field_sources["chapter1.performance.underperforming_items"] = {
        "status": "ok" if matched else "missing",
        "source": "按 指标路径 包含 未达百绩效项目 且排除 月平均得分/全年总扣分 的记录生成",
        "items": matched,
        "matched_count": len(matched),
    }
    data.field_sources["chapter1.performance.monthly_scores"] = {
        "status": "ok" if monthly_score_matches else "missing",
        "source": "优先按接口指标区分匹配月平均得分；缺失指标区分时按得分率唯一匹配兜底，展示值直接取指标数据.实际值",
        "items": monthly_score_matches,
        "matched_count": len(monthly_score_matches),
    }


def _apply_performance_weight_config(data: Chapter1Data, period: Any) -> None:
    digits = "".join(character for character in str(period or "") if character.isdigit())
    period_key = digits[:6] if len(digits) >= 6 else "999999"
    applicable_months = sorted(month for month in PERFORMANCE_WEIGHTS_BY_MONTH if month <= period_key)
    config_month = applicable_months[-1] if applicable_months else None
    config = PERFORMANCE_WEIGHTS_BY_MONTH.get(config_month, {}) if config_month else {}
    sources = []
    for item in data.underperforming_items:
        if item.weight not in (None, 0):
            source = "接口指标数据.权重分数"
        elif item.name in config:
            item.weight = config[item.name]
            source = f"月度权重配置[{config_month}]"
        else:
            item.weight = None
            source = "待补充"
        sources.append({"item_name": item.name, "weight": item.weight, "source": source})
    data.field_sources["chapter1.performance.weights"] = {
        "status": "ok" if sources and all(item["weight"] is not None for item in sources) else "missing",
        "config_month": config_month,
        "items": sources,
    }


def _resolve_mapped_field(rows: List[Dict[str, Any]], rule: Dict[str, Any]) -> Dict[str, Any]:
    attempts = [rule] + [
        {
            "match": item.get("match", {}),
            "value_path": item.get("value_path", rule.get("value_path")),
            "unit_path": item.get("unit_path", rule.get("unit_path")),
            "select": item.get("select", rule.get("select", "first")),
        }
        for item in rule.get("fallback", [])
    ]
    for attempt_index, attempt in enumerate(attempts):
        matches = _match_rows(rows, attempt.get("match", {}))
        if not matches:
            continue
        selected = _select_match(matches, attempt)
        if selected is None:
            continue
        row_index, row = selected
        value = _get_path(row, attempt.get("value_path", ()))
        unit = _get_path(row, attempt.get("unit_path", ())) if attempt.get("unit_path") else None
        if value in (None, ""):
            continue
        if rule.get("target", ("", ""))[1].endswith("_rank") and _to_int(value) in (None, 0):
            continue
        return {
            "status": "ok",
            "source": f"章节数据[{row_index}].{'.'.join(attempt.get('value_path', ())) }",
            "record_index": row_index,
            "record_match": attempt.get("match", {}),
            "metric": row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {},
            "value_path": ".".join(attempt.get("value_path", ())),
            "raw_value": value,
            "value": value,
            "unit": unit,
            "fallback_used": attempt_index > 0,
            "matched_count": len(matches),
        }
    return {
        "status": "missing",
        "message": f"未找到可用字段: {rule.get('match', {})}",
        "record_match": rule.get("match", {}),
        "value_path": ".".join(rule.get("value_path", ())),
    }


def _select_match(matches: List[Tuple[int, Dict[str, Any]]], rule: Dict[str, Any]) -> Optional[Tuple[int, Dict[str, Any]]]:
    select = rule.get("select", "first")
    if select == "last":
        return matches[-1]
    if select == "unique_value":
        value_path = rule.get("value_path", ())
        values = [str(_get_path(row, value_path)) for _index, row in matches if _get_path(row, value_path) not in (None, "")]
        if not values or len(set(values)) != 1:
            return None
        return matches[0]
    if select in {"max_value", "min_value"}:
        value_path = rule.get("value_path", ())
        valued = [(index, row, _to_float(_get_path(row, value_path))) for index, row in matches]
        valued = [item for item in valued if item[2] is not None]
        if not valued:
            return None
        key = lambda item: item[2] or 0
        index, row, _value = max(valued, key=key) if select == "max_value" else min(valued, key=key)
        return index, row
    return matches[0]


def _match_rows(rows: List[Dict[str, Any]], match: Dict[str, Any]) -> List[Tuple[int, Dict[str, Any]]]:
    result: List[Tuple[int, Dict[str, Any]]] = []
    for index, row in enumerate(rows):
        if all(_match_value(row, key, expected) for key, expected in match.items()):
            result.append((index, row))
    return result


def _match_value(row: Dict[str, Any], key: str, expected: Any) -> bool:
    if key == "指标名称":
        actual = str(row.get("指标名称") or "").strip()
        if actual == expected:
            return True
        path = _normalize_metric_path(str(row.get("指标路径") or ""))
        return not actual and _path_contains_segment(path, str(expected))
    if key == "指标路径":
        return _normalize_metric_path(str(row.get("指标路径") or "")) == _normalize_metric_path(str(expected))
    return _get_path(row, tuple(key.split("."))) == expected


def _get_path(data: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    value: Any = data
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _rank_value(metric: Dict[str, Any]) -> RankValue:
    return RankValue(
        actual=_to_float(metric.get("实际值")),
        unit=str(metric.get("单位") or ""),
        province_rank=_to_int(metric.get("省区排名")),
        province_total=_to_int(metric.get("省区总人数") or metric.get("省区人数") or metric.get("省区总数")),
        business_rank=_to_int(metric.get("事业部排名") or metric.get("部门排名")),
        business_total=_to_int(metric.get("事业部总人数") or metric.get("部门总人数") or metric.get("事业部总数")),
    )


def _merge_rank_value(target: RankValue, source: RankValue, province: bool, business: bool) -> None:
    if target.actual is None:
        target.actual = source.actual
    if not target.unit:
        target.unit = source.unit
    if province:
        target.province_rank = source.province_rank
        target.province_total = source.province_total
    if business:
        target.business_rank = source.business_rank
        target.business_total = source.business_total


def _is_monthly_score_record(name: str, path: str) -> bool:
    return name == "月平均得分" or "未达百绩效项目-月平均得分" in path


def _performance_item(name: str, metric: Dict[str, Any]) -> PerformanceItem:
    actual = _to_float(metric.get("实际值"))
    target = _to_float(metric.get("目标值"))
    weight = _to_float(metric.get("权重分数"))
    return PerformanceItem(
        name=name or "未达百绩效项目",
        actual=actual,
        target=target,
        achievement_rate=_rate_value(metric.get("达成率")),
        deduction=abs(_to_float(metric.get("扣分值")) or 0),
        weight=weight,
        monthly_score=None,
    )


PERFORMANCE_ITEM_KEY_FIELDS = (
    "指标区分",
    "项目区分",
    "绩效项目",
    "考核项目",
    "指标项目",
    "项目名称",
    "项目",
)

PERFORMANCE_ITEM_ALIASES = {
    "有效落地项目": "有效出货项目数",
    "有效落地项目数": "有效出货项目数",
    "有效出货项目": "有效出货项目数",
    "招商生效客户": "招商生效",
}


def _performance_item_key(row: Dict[str, Any], metric: Dict[str, Any], allow_name: bool) -> str:
    for source in (row, metric):
        for field in PERFORMANCE_ITEM_KEY_FIELDS:
            key = _normalize_performance_item_key(source.get(field))
            if key:
                return key

    path_key = _performance_item_key_from_path(str(row.get("指标路径") or ""))
    if path_key:
        return path_key

    if allow_name:
        return _normalize_performance_item_key(row.get("指标名称"))
    return ""


def _performance_item_key_from_path(path: str) -> str:
    if not path:
        return ""
    marker = "月平均得分-"
    if marker in path:
        return _normalize_performance_item_key(path.rsplit(marker, 1)[-1])
    if "得分率-" in path:
        return _normalize_performance_item_key(path.rsplit("得分率-", 1)[-1])
    return ""


def _normalize_performance_item_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for character in (" ", "\t", "\n", "　", "（", "）", "(", ")", "-", "_", "：", ":"):
        text = text.replace(character, "")
    return PERFORMANCE_ITEM_ALIASES.get(text, text)


def _rate_value(value: Any) -> Optional[float]:
    number = _to_float(value)
    if number is None:
        return None
    if 0 < number <= 2:
        return float(Decimal(str(number)) * Decimal("100"))
    return number


def _is_metric(path: str, name: str, candidates: Iterable[str]) -> bool:
    leaf = _path_leaf(path)
    return any(candidate == name or candidate == leaf for candidate in candidates)


def _normalize_metric_path(path: str) -> str:
    return path.strip().rstrip("-").strip()


def _path_contains_segment(path: str, segment: str) -> bool:
    normalized_segment = segment.strip()
    if not normalized_segment:
        return False
    return normalized_segment in [part.strip() for part in _normalize_metric_path(path).split("-")]


def _path_leaf(path: str) -> str:
    normalized = _normalize_metric_path(path)
    return normalized.split("-")[-1].strip() if normalized else ""


def _achievement_rate(actual: Optional[float], target: Optional[float]) -> Optional[float]:
    if actual is None or target in (None, 0):
        return None
    return actual / target * 100


def _rank_text(value: RankValue, level: str) -> str:
    if level == "province":
        rank, total = value.province_rank, value.province_total
    else:
        rank, total = value.business_rank, value.business_total
    if rank is None:
        return "待补充"
    if total:
        return f"{rank}/{total}"
    return f"{rank}/待补充"


def _amount_text(value: RankValue) -> str:
    if value.actual is None:
        return "—"
    unit = value.unit or "万"
    return f"{_fmt_number(value.actual)}{unit}"


def _rank_amount_text(value: RankValue) -> str:
    if value.actual is None:
        return "—"
    unit = value.unit or "万"
    precision = 0 if unit in {"万", "万元"} else None
    return f"{_fmt_number(value.actual, precision=precision)}{unit}"


def _top_text(value: RankValue) -> str:
    if not value.business_rank or not value.business_total:
        return "TOP待补充"
    pct = value.business_rank / value.business_total * 100
    for threshold in (5, 10, 15, 20):
        if pct <= threshold:
            return f"TOP{threshold}%"
    return ""


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> Optional[int]:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _fmt_number(value: Optional[float], precision: Optional[int] = None) -> str:
    """默认保留接口数值精度，不擅自截断或四舍五入。"""
    if value is None:
        return "—"
    decimal = Decimal(str(value))
    if precision is not None:
        quant = Decimal("1") if precision == 0 else Decimal("1").scaleb(-precision)
        decimal = decimal.quantize(quant, rounding=ROUND_HALF_UP)
    text = format(decimal.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _sum_optional(*values: Optional[float]) -> Optional[float]:
    if any(value is None for value in values):
        return None
    return float(sum((Decimal(str(value)) for value in values if value is not None), Decimal("0")))


def _month_from_period(period: Any) -> Optional[int]:
    text = str(period or "")
    if len(text) >= 6 and text[-2:].isdigit():
        return int(text[-2:])
    return None


def _title_period(period: Any) -> str:
    text = str(period or "")
    if len(text) >= 6 and text[:4].isdigit() and text[-2:].isdigit():
        return f"{int(text[:4])}年1-{int(text[-2:])}月"
    return "2026年1-5月"


def _previous_year_suffix(period: Any) -> str:
    text = str(period or "")
    if len(text) >= 4 and text[:4].isdigit():
        return str(int(text[:4]) - 1)[-2:]
    return "25"


class Chapter1Generator:
    """第一章「绩效得分与预警」生成器。"""

    def __init__(self, data: Any, period: str = "", guideline: str = "", **_: Any):
        self.data = data
        self.period = period
        self.guideline = guideline

    def run(self) -> str:
        markdown, _stats = format_chapter1_data(self.data, period=self.period)
        return markdown

    async def run_async(self) -> str:
        return self.run()
