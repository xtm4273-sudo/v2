"""从第 1-7 章清洗结果派生第八章事实包。

本模块只负责事实选择、计算和溯源；文案生成留给 chapter8_generator 和
chapter8_ai_writer。调用方只需要知道 build_chapter8_source 这一个接口。
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional


def build_chapter8_source(
    cleaned_by_chapter: Dict[int, Dict[str, Any]],
    person_config: Optional[Dict[str, Any]] = None,
    calmonth: str = "",
) -> Dict[str, Any]:
    """把第 1-7 章清洗结果聚合为第八章可直接消费的事实包。"""
    person = person_config or {}
    c1 = _chapter(cleaned_by_chapter, 1)
    c2 = _chapter(cleaned_by_chapter, 2)
    c3 = _chapter(cleaned_by_chapter, 3)
    c4 = _chapter(cleaned_by_chapter, 4)
    c5 = _chapter(cleaned_by_chapter, 5)
    c6 = _chapter(cleaned_by_chapter, 6)
    c7 = _chapter(cleaned_by_chapter, 7)

    facts: List[Dict[str, Any]] = []
    positive: List[Dict[str, Any]] = []
    negative: List[Dict[str, Any]] = []

    performance = _build_performance(c1)
    _append_performance_signals(performance, facts, positive, negative)

    rows2 = c2.get("rows") if isinstance(c2.get("rows"), list) else []
    for metric_name in ("营业收入（不含税）", "毛利额", "分摊前利润"):
        metric = _find_metric(rows2, metric_name, "年")
        actual = _actual(metric)
        if actual is not None:
            fact = _fact("利润", metric_name, actual, None, str(_dict(metric).get("单位") or ""), 2)
            facts.append(fact)
            if metric_name == "分摊前利润" and performance.get("分摊前利润") in (None, ""):
                (positive if actual >= 0 else negative).append(_signal(fact, outstanding=actual > 0))

    rows3 = c3.get("rows") if isinstance(c3.get("rows"), list) else []
    annual_project = _find_metric(rows3, "100个出货项目", "年")
    monthly_landing = _find_metric(rows3, "有效项目落地", "月")
    annual_channel = _find_metric(rows3, "招商生效客户", "年")
    annual_customer = _find_metric(rows3, "20个存量生效客户", "年")

    _append_target_signal(monthly_landing, "项目", "月度有效项目落地", 3, facts, positive, negative)
    _append_target_signal(annual_project, "项目", "年度出货项目", 3, facts, positive, negative)
    _append_target_signal(annual_channel, "渠道", "招商生效客户", 3, facts, positive, negative)
    _append_target_signal(annual_customer, "客户", "存量生效客户", 3, facts, positive, negative)

    products = c4.get("products") if isinstance(c4.get("products"), list) else []
    top_growing = [p for p in products if _product_direction(p) == "up"][:3]
    top_declining = [p for p in products if _product_direction(p) == "down"][:3]
    for product in top_growing:
        _append_product_signal(product, True, facts, positive)
    for product in top_declining:
        _append_product_signal(product, False, facts, negative)

    overdue = _sum_leaf_overdue(c5.get("receivable_tree"))
    impairment = _to_float(_dict(c5.get("impairment_summary")).get("current_year_increase"))
    finance_cost = _to_float(_dict(c5.get("financial_expense")).get("expense"))
    if overdue is not None:
        fact = _fact("应收", "逾期应收", overdue, None, "万元", 5, severity="high")
        facts.append(fact)
        negative.append(_signal(fact))

    sampling_total = _dict(_dict(c6.get("sample_paint_expense")).get("total"))
    sample_expense = _to_float(sampling_total.get("value"))
    sample_yoy = _to_float(sampling_total.get("yoy_value", sampling_total.get("same_period")))
    sample_direction = _direction(sample_expense, sample_yoy)
    if sample_expense is not None:
        fact = _fact(
            "打样",
            "样板样漆费用",
            sample_expense,
            sample_yoy,
            "元",
            6,
            change_display=_sample_change_display(sample_direction),
            severity="medium",
        )
        facts.append(fact)
        negative.append(_signal(fact))

    total_visit = _dict(c7.get("total_visit"))
    visit_actual = _to_float(total_visit.get("actual"))
    visit_target = _to_float(total_visit.get("target"))
    visit_rate = _to_float(total_visit.get("achievement_rate"))
    visit_fact = _fact(
        "行销",
        "拜访总频次",
        visit_actual,
        visit_target,
        "次",
        7,
        change_display=f"达成{_format_percent(visit_rate)}%" if visit_rate is not None else "数据待补充",
        severity="high" if visit_actual is None or (visit_rate is not None and visit_rate < 60) else "medium",
    )
    facts.append(visit_fact)
    if visit_actual is not None:
        (positive if visit_rate is not None and visit_rate >= 100 else negative).append(_signal(visit_fact))

    dimension_summary = {
        "产品": {"top_growing": top_growing, "top_declining": top_declining},
        "项目": {
            "project_count": _actual(annual_project),
            "project_target": _target(annual_project),
            "achievement_rate": _achievement(annual_project),
            "single_project_revenue": None,
            "yoy_change_pct": None,
        },
        "渠道": {
            "channel_count": _actual(annual_channel),
            "channel_target": _target(annual_channel),
            "achievement_rate": _achievement(annual_channel),
            "yoy_change_pct": None,
        },
        "客户": {
            "customer_count": _actual(annual_customer),
            "customer_target": _target(annual_customer),
            "achievement_rate": _achievement(annual_customer),
            "avg_revenue_per_customer": None,
            "yoy_change_pct": None,
        },
        "应收": {
            "overdue_amount": overdue,
            "impairment_amount": impairment,
            "finance_cost": finance_cost,
        },
        "打样": {
            "sample_expense": sample_expense,
            "yoy_direction": sample_direction,
        },
        "风控": {
            "overdue_amount": overdue,
            "impairment_amount": impairment,
            "finance_cost": finance_cost,
            "risk_level": "high" if overdue is not None and overdue > 0 else "normal",
        },
    }

    return {
        "code": 1,
        "message": "derived_from_chapters_1_to_7",
        "data": {
            "月份": calmonth,
            "区域经理工号": str(person.get("job_id") or ""),
            "区域经理姓名": str(person.get("sale_name") or ""),
            "部门名称": str(person.get("city_operation_department") or ""),
            "章节名称": "八、总结",
            "performance": performance,
            "facts": facts,
            "positive_signals": positive,
            "negative_signals": negative,
            "dimension_summary": dimension_summary,
        },
    }


def _chapter(chapters: Dict[int, Dict[str, Any]], number: int) -> Dict[str, Any]:
    value = chapters.get(number, {})
    return value if isinstance(value, dict) else {}


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build_performance(c1: Dict[str, Any]) -> Dict[str, Any]:
    score = _dict(c1.get("performance_score"))
    sales = _dict(c1.get("sales"))
    profit = _dict(c1.get("profit"))
    year_profit = _dict(c1.get("year_end_profit"))
    return {
        "绩效得分": _to_float(score.get("actual")),
        "省区内排名": _rank(score, "province"),
        "事业部内排名": _rank(score, "business"),
        "销量": _to_float(sales.get("actual")),
        "销量省区排名": _to_float(sales.get("province_rank")),
        "分摊前利润": _to_float(profit.get("actual")) or _to_float(year_profit.get("accumulated_profit")),
        "利润省区排名": _to_float(profit.get("province_rank")),
    }


def _rank(metric: Dict[str, Any], prefix: str) -> str:
    rank = metric.get(f"{prefix}_rank")
    total = metric.get(f"{prefix}_total")
    if rank in (None, ""):
        return ""
    return f"{rank}/{total}" if total not in (None, "") else str(rank)


def _append_performance_signals(
    performance: Dict[str, Any],
    facts: List[Dict[str, Any]],
    positive: List[Dict[str, Any]],
    negative: List[Dict[str, Any]],
) -> None:
    score = _to_float(performance.get("绩效得分"))
    if score is not None:
        fact = _fact("绩效", "绩效得分", score, 100.0, "分", 1, severity="high" if score < 90 else "medium")
        facts.append(fact)
        (positive if score >= 100 else negative).append(_signal(fact, outstanding=score >= 110))

    profit = _to_float(performance.get("分摊前利润"))
    if profit is not None and profit > 0:
        rank = performance.get("利润省区排名")
        change = f"省区第{int(rank)}" if _to_float(rank) is not None else ""
        fact = _fact("绩效", "分摊前利润", profit, None, "万元", 1, change_display=change)
        facts.append(fact)
        positive.append(_signal(fact, outstanding=_to_float(rank) is not None and _to_float(rank) <= 10))


def _find_metric(rows: Iterable[Any], name: str, date_type: str) -> Optional[Dict[str, Any]]:
    for row in rows:
        if not isinstance(row, dict) or not _row_matches_metric_name(row, name):
            continue
        metric = _dict(row.get("指标数据"))
        if str(metric.get("日期类型") or "") == date_type:
            return metric
    return None


def _row_matches_metric_name(row: Dict[str, Any], name: str) -> bool:
    metric_name = str(row.get("指标名称") or "").strip()
    if metric_name == name:
        return True

    path_parts = [
        part.strip()
        for part in str(row.get("指标路径") or "").strip().rstrip("-").split("-")
        if part.strip()
    ]
    return name in path_parts


def _append_target_signal(
    metric: Optional[Dict[str, Any]],
    dimension: str,
    name: str,
    chapter: int,
    facts: List[Dict[str, Any]],
    positive: List[Dict[str, Any]],
    negative: List[Dict[str, Any]],
) -> None:
    actual = _actual(metric)
    target = _target(metric)
    if actual is None:
        return
    rate = _achievement(metric)
    change = f"达成{_format_percent(rate)}%" if rate is not None else ""
    severity = "high" if rate is not None and rate < 60 else "medium"
    fact = _fact(dimension, name, actual, target, str(_dict(metric).get("单位") or ""), chapter, change_display=change, severity=severity)
    facts.append(fact)
    (positive if rate is not None and rate >= 100 else negative).append(_signal(fact, outstanding=rate is not None and rate >= 100))


def _append_product_signal(product: Dict[str, Any], is_positive: bool, facts: List[Dict[str, Any]], target: List[Dict[str, Any]]) -> None:
    name = str(product.get("product_name") or "")
    value = _to_float(product.get("price"))
    direction = "均价上升" if is_positive else "均价下降"
    fact = _fact("产品", f"{name}均价", value, None, "元/KG", 4, change_display=direction, severity="medium")
    facts.append(fact)
    target.append(_signal(fact, outstanding=is_positive))


def _product_direction(product: Dict[str, Any]) -> str:
    revenue_direction = str(product.get("revenue_share_direction") or "")
    price_direction = str(product.get("price_direction") or "")
    if revenue_direction == price_direction and revenue_direction in {"up", "down"}:
        return revenue_direction
    return revenue_direction if revenue_direction in {"up", "down"} else price_direction


def _sum_leaf_overdue(tree: Any) -> Optional[float]:
    if not isinstance(tree, dict):
        return None
    total = 0.0
    found = False

    def visit(node: Dict[str, Any]) -> None:
        nonlocal total, found
        children = [child for child in node.get("children", []) if isinstance(child, dict)] if isinstance(node.get("children"), list) else []
        name = str(node.get("name") or "")
        if "逾期" in name and not children:
            value = _to_float(_dict(node.get("amount")).get("value"))
            if value is not None:
                total += value
                found = True
        for child in children:
            visit(child)

    visit(tree)
    return round(total, 3) if found else None


def _fact(
    dimension: str,
    metric_name: str,
    actual: Optional[float],
    target: Optional[float],
    unit: str,
    source_chapter: int,
    change_display: str = "",
    severity: str = "medium",
) -> Dict[str, Any]:
    gap = None
    if actual is not None and target is not None:
        gap = round(max(target - actual, 0), 3)
    return {
        "dimension": dimension,
        "metric_name": metric_name,
        "actual": actual,
        "target": target,
        "gap": gap,
        "unit": unit,
        "source_chapter": source_chapter,
        "change_display": change_display,
        "severity": severity,
    }


def _signal(fact: Dict[str, Any], outstanding: bool = False) -> Dict[str, Any]:
    actual = fact.get("actual")
    unit = str(fact.get("unit") or "")
    return {
        "dimension": fact.get("dimension", ""),
        "dimension_label": fact.get("dimension", ""),
        "metric_name": fact.get("metric_name", ""),
        "value_display": f"{_format_display_number(actual, unit)}{unit}" if actual is not None else "",
        "change_display": fact.get("change_display", ""),
        "is_outstanding": outstanding,
        "severity": fact.get("severity", "medium"),
        "source_chapter": fact.get("source_chapter"),
    }


def _actual(metric: Optional[Dict[str, Any]]) -> Optional[float]:
    return _to_float(_dict(metric).get("实际值"))


def _target(metric: Optional[Dict[str, Any]]) -> Optional[float]:
    return _to_float(_dict(metric).get("目标值"))


def _achievement(metric: Optional[Dict[str, Any]]) -> Optional[float]:
    data = _dict(metric)
    actual = _to_float(data.get("实际值"))
    target = _to_float(data.get("目标值"))
    if target not in (None, 0):
        return round((actual or 0) / target * 100, 1)
    return _to_float(data.get("达成率"))


def _direction(value: Optional[float], previous: Optional[float]) -> str:
    if value is None or previous is None:
        return "unknown"
    if previous == 0:
        if value > 0:
            return "new"
        if value == 0:
            return "flat"
        return "down"
    if value > previous:
        return "up"
    if value < previous:
        return "down"
    return "flat"


def _sample_change_display(direction: str) -> str:
    if direction == "new":
        return "同比新增"
    if direction == "up":
        return "同比增加"
    if direction == "down":
        return "同比下降"
    if direction == "flat":
        return "同比持平"
    return "同期数据待补充"


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _format_number(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return ""
    return str(int(number)) if number.is_integer() else f"{number:.3f}".rstrip("0").rstrip(".")


def _format_display_number(value: Any, unit: str) -> str:
    number = _to_float(value)
    if number is None:
        return ""
    if unit == "万元":
        return f"{Decimal(str(number)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):.1f}"
    if unit == "元":
        return f"{Decimal(str(number)).quantize(Decimal('1'), rounding=ROUND_HALF_UP):.0f}"
    return _format_number(number)


def _format_percent(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return ""
    rounded = round(number)
    if abs(number - rounded) < 0.5:
        return str(int(rounded))
    return _format_number(number)
