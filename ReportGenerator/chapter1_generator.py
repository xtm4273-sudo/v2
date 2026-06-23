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
    achievement_rate: Optional[float] = None
    overdue_amount: Optional[float] = None
    due_amount: Optional[float] = None
    same_period_overdue: Optional[float] = None


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
        ],
    },
    "chapter1.rank_table.performance_province_rank": {
        "match": {"指标名称": "绩效总分"},
        "value_path": ("指标数据", "省区排名"),
        "target": ("performance_score", "province_rank"),
        "required": True,
        "fallback": [
            {"match": {"指标名称": "绩效得分"}, "value_path": ("指标数据", "省区排名")},
        ],
    },
    "chapter1.rank_table.performance_business_rank": {
        "match": {"指标名称": "绩效总分"},
        "value_path": ("指标数据", "部门排名"),
        "target": ("performance_score", "business_rank"),
        "required": True,
        "fallback": [
            {"match": {"指标名称": "绩效得分"}, "value_path": ("指标数据", "事业部排名")},
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
        "required": True,
    },
    "chapter1.quarter_bonus.achievement_rate": {
        "match": {"指标名称": "个人季度实际销量", "指标数据.日期类型": "季"},
        "select": "unique_value",
        "value_path": ("指标数据", "达成率"),
        "target": ("quarter_bonus", "achievement_rate"),
        "transform": "rate",
        "required": True,
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
    _apply_underperforming_items_mapping(rows, data)

    if data.performance_score.actual is None:
        data.warnings.append("缺少绩效得分")
    return data


def build_chapter1_markdown(chapter_data: Chapter1Data, period: str = "") -> str:
    """按 V5 范本第一章固定结构生成 Markdown。"""
    month = _month_from_period(chapter_data.metadata.get("month") or period)
    ytd_label = f"1-{month}月" if month else "累计"
    title_period = _title_period(chapter_data.metadata.get("month") or period)
    operation_department = chapter_data.metadata.get("operation_department") or "经营部（接口未提供）"

    lines: List[str] = [
        f"{operation_department}区域经理{title_period}经营分析报告",
        "",
        "# 绩效得分与预警",
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
    """奖金档位待客户补充完整规则，不根据范本中的单个示例推测。"""
    return "待补充", "上一档奖金基数规则待客户补充，暂不进行区间判断。"


def _build_rank_table(chapter_data: Chapter1Data) -> str:
    return "\n".join(
        [
            f"|  | 绩效排名 | 销量{_amount_text(chapter_data.sales)} | 分摊前利润{_amount_text(chapter_data.profit)} |",
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
    if not problem_names and chapter_data.performance_score.actual is not None:
        problem_names = "绩效总分未达100分" if chapter_data.performance_score.actual < 100 else "—"
    elif not problem_names:
        problem_names = "—"
    rows = [
        "| 月度绩效 | 完成情况 | 关键详情 |",
        "| --- | --- | --- |",
        (
            "| 月平均绩效得分（不含其他奖惩） | "
            f"{_fmt_number(chapter_data.performance_score.actual)}分（{_top_text(chapter_data.performance_score)}） | "
            f"{problem_names} |"
        ),
    ]
    for item in chapter_data.underperforming_items:
        rows.append(
            f"| {item.name} | 达成率：{_fmt_number(item.achievement_rate)}% | "
            f"全年总扣分{_fmt_number(item.deduction)}分，"
            f"月平均得分{_fmt_number(item.monthly_score if item.monthly_score is not None else _monthly_average_score(item.weight, item.deduction))}分"
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
    potential_overdue = _sum_optional(bonus.overdue_amount, bonus.due_amount)
    overdue_limit = (
        Decimal(str(bonus.same_period_overdue)) * Decimal("0.7")
        if bonus.same_period_overdue is not None
        else None
    )
    month_text = f"{month}月底" if month else "月底"
    next_year = _previous_year_suffix(chapter_data.metadata.get("month"))

    return "\n".join(
        [
            "| 奖金影响因素 | 情形 | 数值 |",
            "| --- | --- | --- |",
            f"| 个人季度实际销量 | 本季度累计销量 | {_fmt_number(bonus.sales_actual)}万 |",
            f"|  | 当前达成率 | {_percent_or_pending(bonus.achievement_rate)} |",
            "|  | 距离80%达成率（发放硬性条件） | 待补充 |",
            "|  | 距离同期销量持平（负增长将同比例打折） | 待补充 |",
            "|  | 距离100%达成率还差 | 待补充 |",
            f"| 发放规则（与逾期金额同比挂钩） | 截止{month_text}逾期金额 | {_amount_or_pending(bonus.overdue_amount)} |",
            f"|  | 本季度预计到期款 | {_amount_or_pending(bonus.due_amount)} |",
            f"|  | 合计（潜在逾期总额） | {_amount_or_pending(potential_overdue)} |",
            f"|  | {next_year}年同期逾期金额（含法诉，仅考虑{next_year}年同期，不考虑交接后的逾期） | {_amount_or_pending(bonus.same_period_overdue)} |",
            f"|  | 逾期金额同比下降30%，本季度末逾期金额不超过（含法诉，仅考虑{next_year}年同期，不考虑交接后的逾期） | {_amount_or_pending(overdue_limit)} |",
            f"|  | 本季度末逾期金额对应的各类情形 | {_overdue_rule_text()} |",
        ]
    )


def _build_year_end_profit_text(chapter_data: Chapter1Data, month: Optional[int]) -> str:
    profit = chapter_data.year_end_profit.accumulated_profit
    base, next_tip = profit_bonus_base(profit)
    if chapter_data.year_end_profit.bonus_base is not None:
        base = f"{_fmt_number(chapter_data.year_end_profit.bonus_base)}万"
    month_text = f"{month}月" if month else "当前"
    return f"截止{month_text}本年累计分摊前利润{_fmt_number(profit)}万，奖金基数为{base}。{next_tip}"


def _overdue_rule_text() -> str:
    return (
        "当季度先发50%，剩余50%奖金与逾期金额挂钩，情形如下：<br>"
        "（1）0逾期则奖金100%发放；<br>"
        "（2）若存在逾期金额且同比下降30%以内，剩余奖金按逾期金额同比下降率*3发放。例如:员工A当季度逾期金额同比下降率为20%，则奖金发放比例为50%+50%*20%*3=80%；<br>"
        "（3）若存在逾期金额且同比下降超过30%（含），剩余奖金按100%发放，例如:员工B当季度逾期金额同比下降率为30%，则奖金发放比例为50%+50%=100%；<br>"
        "（4）如当季度逾期金额(含法务)占循环12个月销量占比低于2%(含)，则剩余奖金100%发放；例如:员工C循环12个月销量为800万，当季度逾期金额为15万，则占比为1.87%，对应剩余奖金发放比例为100%；<br>"
        "（5）如当季度有逾期且同比持平或增长，则剩余奖金延后发放并打折。如剩余奖金延后发放，则剩余奖金金额逐季度按0.85打折，顺延至年底的剩余奖金发放条件参照信用管理制度中年终奖发放条件）"
    )


def _amount_or_pending(value: Any) -> str:
    return "待补充" if value is None else f"{_fmt_number(value)}万"


def _percent_or_pending(value: Any) -> str:
    return "待补充" if value is None else f"{_fmt_number(value)}%"


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


def _apply_underperforming_items_mapping(rows: List[Dict[str, Any]], data: Chapter1Data) -> None:
    matched: List[Dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        name = str(row.get("指标名称") or "").strip()
        path = str(row.get("指标路径") or "").strip()
        metric = row.get("指标数据") if isinstance(row, dict) else {}
        if not isinstance(metric, dict):
            continue
        if "未达百绩效项目" not in path:
            continue
        if name in {"月平均得分", "全年总扣分"} or "未达百绩效项目(扣分)" in path:
            continue

        item = _performance_item(name, metric)
        if item.achievement_rate is None:
            item.achievement_rate = _achievement_rate(item.actual, item.target)
        if item.achievement_rate is not None and item.achievement_rate < 100:
            data.underperforming_items.append(item)
            matched.append(
                {
                    "record_index": row_index,
                    "source": f"章节数据[{row_index}].指标数据",
                    "metric_name": name,
                    "metric": metric,
                }
            )

    data.field_sources["chapter1.performance.underperforming_items"] = {
        "status": "ok" if matched else "missing",
        "source": "按 指标路径 包含 未达百绩效项目 且排除 月平均得分/全年总扣分 的记录生成",
        "items": matched,
        "matched_count": len(matched),
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
        if all(_get_path(row, tuple(key.split("."))) == expected for key, expected in match.items()):
            result.append((index, row))
    return result


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


def _performance_item(name: str, metric: Dict[str, Any]) -> PerformanceItem:
    actual = _to_float(metric.get("实际值"))
    target = _to_float(metric.get("目标值"))
    weight = _to_float(metric.get("权重分数"))
    monthly_score = None
    if not weight:
        weight = target
        monthly_score = actual
    return PerformanceItem(
        name=name or "未达百绩效项目",
        actual=actual,
        target=target,
        achievement_rate=_rate_value(metric.get("达成率")),
        deduction=abs(_to_float(metric.get("扣分值")) or 0),
        weight=weight,
        monthly_score=monthly_score,
    )


def _rate_value(value: Any) -> Optional[float]:
    number = _to_float(value)
    if number is None:
        return None
    if 0 < number <= 1:
        return float(Decimal(str(number)) * Decimal("100"))
    return number


def _is_metric(path: str, name: str, candidates: Iterable[str]) -> bool:
    leaf = _path_leaf(path)
    return any(candidate == name or candidate == leaf for candidate in candidates)


def _path_leaf(path: str) -> str:
    return path.split("-")[-1].strip() if path else ""


def _achievement_rate(actual: Optional[float], target: Optional[float]) -> Optional[float]:
    if actual is None or target in (None, 0):
        return None
    return actual / target * 100


def _monthly_average_score(weight: Optional[float], deduction: Optional[float]) -> Optional[float]:
    if weight is None:
        return None
    return max(weight - (deduction or 0) / 12, 0)


def _rank_text(value: RankValue, level: str) -> str:
    if level == "province":
        rank, total = value.province_rank, value.province_total
    else:
        rank, total = value.business_rank, value.business_total
    if rank is None:
        return "—"
    if total:
        return f"{rank}/{total}"
    return str(rank)


def _amount_text(value: RankValue) -> str:
    if value.actual is None:
        return "—"
    unit = value.unit or "万"
    return f"{_fmt_number(value.actual)}{unit}"


def _top_text(value: RankValue) -> str:
    if not value.province_rank or not value.province_total:
        return "TOP 待补充"
    pct = value.province_rank / value.province_total * 100
    bucket = int(((pct + 9.999) // 10) * 10)
    return f"TOP {bucket}%"


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
