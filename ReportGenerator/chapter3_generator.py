"""第三章生成器 - 销量分析（严格字段映射版）。

本模块只使用 MOUDLE=3 返回的明确字段。记录必须由“指标名称 +
指标路径 + 日期类型”精确命中；不按数组顺序、数值大小或相似名称猜测。
直接取值保留 JSON 原始精度，缺失或冲突时显示红色“待补充”。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import logging

from Data import EMPTY_DATA_MESSAGE, ChapterDataError
from ReportGenerator.report_period import current_and_ytd_labels

logger = logging.getLogger(__name__)

TIME_DIMENSIONS = ("月", "季", "年")
MISSING = '<span style="color:#c00000;font-weight:700">待补充</span>'


@dataclass(frozen=True)
class MetricRecord:
    name: str
    path: str
    date_type: str
    actual: Any
    target: Any
    yoy: Any
    deduction: Any
    achievement_rate: Any
    unit: str
    customer_code: str = ""
    customer_name: str = ""

    @property
    def group(self) -> str:
        return _path_group_and_leaf(self.path)[0]

    @property
    def leaf(self) -> str:
        return _path_group_and_leaf(self.path)[1] or self.name


def format_chapter3_data(
    raw_data: Any,
    period: str = "",
    action_guide_text: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    records = normalize_chapter3_records(raw_data)
    grouped = group_chapter3_records(records)
    markdown = build_chapter3_markdown(grouped, period, action_guide_text)
    stats = build_chapter3_stats(records, grouped)
    stats["field_audit"] = build_chapter3_field_audit(records, period)
    return markdown, stats


async def format_chapter3_data_async(
    raw_data: Any,
    period: str = "",
    action_guide_writer: Optional[Any] = None,
) -> Tuple[str, Dict[str, Any]]:
    records = normalize_chapter3_records(raw_data)
    grouped = group_chapter3_records(records)
    fallback = build_rule_based_action_guide(grouped)
    text = fallback
    if action_guide_writer is not None:
        try:
            context = build_chapter3_action_context(grouped, period)
            if hasattr(action_guide_writer, "generate"):
                text = await action_guide_writer.generate(context, fallback_text=fallback)
            else:
                text = await action_guide_writer(context, fallback)
        except Exception as exc:
            logger.warning("第三章 AI 行动指南生成失败，使用固定模板: %s", exc)
            text = fallback
    markdown = build_chapter3_markdown(grouped, period, text)
    stats = build_chapter3_stats(records, grouped)
    stats["field_audit"] = build_chapter3_field_audit(records, period)
    stats["行动指南来源"] = "ai" if text != fallback else "fixed_template"
    return markdown, stats


def normalize_chapter3_records(raw_data: Any) -> List[MetricRecord]:
    rows = _extract_chapter_rows(raw_data)
    records: List[MetricRecord] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("指标数据"), dict):
            continue
        data = row["指标数据"]
        name = str(row.get("指标名称") or "").strip()
        path = _normalize_metric_path(str(row.get("指标路径") or ""))
        if not name:
            name = _path_group_and_leaf(path)[1]
        date_type = str(data.get("日期类型") or "").strip()
        if not path:
            continue
        records.append(MetricRecord(
            name=name,
            path=path,
            date_type=date_type,
            actual=data.get("实际值"),
            target=data.get("目标值"),
            yoy=data.get("同期数"),
            deduction=data.get("扣分值"),
            achievement_rate=data.get("达成率"),
            unit=str(data.get("单位") or "").strip(),
            customer_code=str(row.get("客户编码") or row.get("customer_code") or "").strip(),
            customer_name=str(row.get("客户名称") or row.get("customer_name") or "").strip(),
        ))
    if not records:
        raise ChapterDataError(f"第三章数据清洗失败: 清洗后没有有效指标记录。{EMPTY_DATA_MESSAGE}")
    return records


def group_chapter3_records(records: Iterable[MetricRecord]) -> Dict[str, Any]:
    all_records = list(records)
    return {
        "all_records": all_records,
        "sales_overview": {
            dim: _sales_overview_record(all_records, dim)
            for dim in TIME_DIMENSIONS
        },
        "active_customer": {
            dim: _unique_record(all_records, "招商生效客户", "三、销量分析-招商生效客户", dim)[0]
            for dim in TIME_DIMENSIONS
        },
        "landing_project": {
            dim: _unique_record(all_records, "有效项目落地", "三、销量分析-有效项目落地", dim)[0]
            for dim in TIME_DIMENSIONS
        },
        "sample_project": {
            dim: _unique_record(all_records, "打样项目数", "三、销量分析-打样项目数", dim)[0]
            for dim in TIME_DIMENSIONS
        },
        "annual_customer": _unique_record(all_records, "20个存量生效客户", "三、销量分析-20个存量生效客户", "年")[0],
        "annual_project": _unique_record(all_records, "100个出货项目", "三、销量分析-100个出货项目", "年")[0],
        "product_amount": _records_with_path_prefix(all_records, "三、销量分析-各产品销量-"),
        "product_volume": _records_with_path_prefix(all_records, "三、销量分析-各产品销售量-"),
        "industry_volume": _records_with_path_prefix(all_records, "三、销量分析-各行业销量-"),
        "industry_share": _records_with_path_prefix(all_records, "三、销量分析-各行业销量占比-"),
        "customer_sales": _customer_sales_records(all_records),
        "process": {
            name: _unique_by_name_path(all_records, name, path)
            for name, path in (
                ("产销客户数", "三、销量分析-销量-产销客户数"),
                ("客均销量", "三、销量分析-销量-客均销量"),
                ("产销项目数", "三、销量分析-销量-产销项目数"),
                ("单项目销量", "三、销量分析-销量-单项目销量"),
            )
        },
    }


def build_chapter3_risk_product_names(raw_data: Any) -> List[str]:
    """返回 3.3 风险指标产品名称，口径与第三章正文保持一致。"""
    records = normalize_chapter3_records(raw_data)
    grouped = group_chapter3_records(records)
    return [amount.name for amount, _volume in _risk_product_pairs(grouped)]


def build_chapter3_markdown(grouped: Dict[str, Any], period: str = "", action_guide_text: Optional[str] = None) -> str:
    month_label, ytd_label = month_labels(period)
    lines = [
        "# 三、销量分析", "", "## 3.1 销量概况", "",
        _build_sales_table(grouped["sales_overview"], month_label, ytd_label), "",
        "## 3.2 过程指标预警", "",
    ]
    lines.extend(_build_process_section(grouped, month_label, ytd_label))
    lines.extend(["", "## 3.3 产品、产销客户、产销项目及行业", ""])
    lines.extend(_build_dimension_section(grouped, ytd_label.replace("累计", ""), action_guide_text))
    return "\n".join(lines).rstrip() + "\n"


def _build_sales_table(sales: Dict[str, Optional[MetricRecord]], month_label: str, ytd_label: str) -> str:
    lines = [f"| 销量 | {month_label} | 本季度累计 | {ytd_label} |", "| --- | --- | --- | --- |"]
    for label, field in (("目标", "target"), ("实际", "actual"), ("达成率", "achievement_rate")):
        cells = [_sales_direct_field(sales.get(dim), field) for dim in TIME_DIMENSIONS]
        lines.append(f"| {label} | {' | '.join(cells)} |")
    calculated_rows = (
        ("达成差额", _sales_achievement_gap),
        ("同比增长率", _sales_yoy_growth_rate),
        ("同比差额", _sales_yoy_gap),
    )
    for label, calculator in calculated_rows:
        cells = [calculator(sales.get(dim)) for dim in TIME_DIMENSIONS]
        lines.append(f"| {label} | {' | '.join(cells)} |")
    return "\n".join(lines)


def _build_process_section(grouped: Dict[str, Any], month_label: str, ytd_label: str) -> List[str]:
    annual_customer = grouped["annual_customer"]
    annual_project = grouped["annual_project"]
    sample_year = grouped["sample_project"].get("年")
    negative_count_items = ["打样项目数"] if _is_count_negative(sample_year) else []
    lines = [
        f"未达百（{ytd_label.replace('累计', '')}）指标包含：招商生效客户、有效落地项目",
        "",
    ]
    if negative_count_items:
        lines.extend([
            f"负增长（{ytd_label.replace('累计', '')}）指标包含：{'、'.join(negative_count_items)}",
            "",
        ])
    lines.extend([
        (
            f"年度{_integer_record_field(annual_customer, 'target', '个')}存量生效客户目标已完成"
            f"{_integer_record_field(annual_customer, 'actual', '个')}（差距{_integer_record_field(annual_customer, 'deduction', '个')}），"
            f"{_integer_record_field(annual_project, 'target', '个')}出货项目目标已完成"
            f"{_integer_record_field(annual_project, 'actual', '个')}（差距{_integer_record_field(annual_project, 'deduction', '个')}）"
        ),
        "",
        f"| 过程指标 | 目标与实际 | {month_label} | 本季度累计 | {ytd_label} |",
        "| --- | --- | --- | --- | --- |",
    ])
    lines.extend(_process_rows("招商生效客户（家）", grouped["active_customer"], "家"))
    lines.extend(_process_rows("有效落地项目（个）", grouped["landing_project"], "个"))
    lines.extend(_sample_rows(grouped["sample_project"]))
    return lines


def _process_rows(label: str, records: Dict[str, Optional[MetricRecord]], unit: str) -> List[str]:
    output = []
    for row_label, field in (("目标", "target"), ("实际", "actual"), ("差距", "deduction"), ("达成率", "achievement_rate")):
        values = [
            _integer_record_field(records.get(dim), field, "%" if field == "achievement_rate" else unit)
            for dim in TIME_DIMENSIONS
        ]
        output.append(f"| {label if not output else ''} | {row_label} | {' | '.join(values)} |")
    return output


def _sample_rows(records: Dict[str, Optional[MetricRecord]]) -> List[str]:
    actual = [_integer_record_field(records.get(dim), "actual", "个") for dim in TIME_DIMENSIONS]
    yoy = [_integer_record_field(records.get(dim), "yoy", "个") for dim in TIME_DIMENSIONS]
    gap = [_integer_sample_gap(records.get(dim)) for dim in TIME_DIMENSIONS]
    growth = [_integer_sample_growth_rate(records.get(dim)) for dim in TIME_DIMENSIONS]
    return [
        f"| 打样项目数（个） | 26年 | {' | '.join(actual)} |",
        f"|  | 25年同期 | {' | '.join(yoy)} |",
        f"|  | 差距 | {' | '.join(gap)} |",
        f"|  | 增长率 | {' | '.join(growth)} |",
    ]


def _build_dimension_section(grouped: Dict[str, Any], period_label: str, action_guide_text: Optional[str]) -> List[str]:
    amount_by_name = {record.name: record for record in grouped["product_amount"]}
    industry_by_name = {record.name: record for record in grouped["industry_volume"]}
    share_by_name = {record.name: record for record in grouped["industry_share"]}

    positive_products = sorted(
        [record for record in amount_by_name.values() if (_growth_percent(record) or Decimal("0")) > 0],
        key=lambda record: _decimal(record.actual) or Decimal("0"),
        reverse=True,
    )[:3]
    risk_product_pairs = _risk_product_pairs(grouped)
    positive_industries = sorted(
        [
            (record, share_by_name[record.name])
            for record in industry_by_name.values()
            if record.name in share_by_name
            and (_growth_percent(record) or Decimal("0")) > 0
            and _share_change(share_by_name[record.name]) is not None
            and (_share_change(share_by_name[record.name]) or Decimal("0")) > 0
        ],
        key=lambda pair: _decimal(pair[1].actual) or Decimal("0"),
        reverse=True,
    )[:3]
    risk_industries = sorted(
        [
            (record, share_by_name[record.name])
            for record in industry_by_name.values()
            if record.name in share_by_name
            and (_growth_percent(record) or Decimal("0")) < 0
            and _share_change(share_by_name[record.name]) is not None
        ],
        key=lambda pair: _decimal(pair[1].actual) or Decimal("0"),
        reverse=True,
    )[:3]

    customer = grouped["process"].get("产销客户数")
    project = grouped["process"].get("产销项目数")
    customer_average = grouped["process"].get("客均销量")
    project_average = grouped["process"].get("单项目销量")
    risk_customers = _customer_sales_decline_top3(grouped.get("customer_sales", []))
    customer_decline_text = _customer_decline_names_with_amount_or_empty(risk_customers)

    positive_lines = [
        f"### 正向指标（{period_label}）",
        f"* **产品：**{_positive_product_text(positive_products)}{'表现突出' if positive_products else ''}",
    ]
    if not _process_change_is_negative(customer):
        positive_lines.append(f"* **客户：**{_process_change_text(customer, '产销客户数')}")
    if not _process_change_is_negative(project):
        positive_lines.append(f"* **项目：**{_process_change_text(project, '产销项目数')}")
    positive_lines.append(f"* **行业：**{_positive_industry_text(positive_industries)}")

    customer_risk_parts = []
    if _process_change_is_negative(customer):
        customer_risk_parts.append(_process_change_text(customer, "产销客户数"))
    customer_risk_parts.append(
        f"客均销量{_dimension_amount_field(customer_average)}（↓{_absolute_growth_text(customer_average)}）"
    )
    if customer_decline_text:
        customer_risk_parts.append(f"{period_label}销量下降金额前三的客户包含：{customer_decline_text}")

    project_risk_parts = []
    if _process_change_is_negative(project):
        project_risk_parts.append(_process_change_text(project, "产销项目数"))
    project_risk_parts.append(
        f"单项目销量{_dimension_amount_field(project_average)}（↓{_absolute_growth_text(project_average)}）"
    )

    lines = positive_lines + [
        f"### 风险指标（{period_label}）",
        f"* **产品：**{_risk_product_text(risk_product_pairs)}",
        f"* **客户：**{'；'.join(customer_risk_parts)}",
        f"* **项目：**{'；'.join(project_risk_parts)}",
        f"* **行业：**{_risk_industry_text(risk_industries)}",
        "## 3.4 行动指南",
        f"◇ {action_guide_text or build_rule_based_action_guide(grouped)}",
    ]
    return lines


def build_rule_based_action_guide(grouped: Dict[str, Any]) -> str:
    return "优先复盘收入与销售量同时下降的产品，同步关注客均销量、单项目销量及收入与占比下降的行业，逐项制定补量动作。"


def build_chapter3_action_context(grouped: Dict[str, Any], period: str = "") -> Dict[str, Any]:
    customer_declines = _customer_sales_decline_top3(grouped.get("customer_sales", []))
    return {
        "period": month_labels(period)[1].replace("累计", ""),
        "fixed_mapping_only": True,
        "missing_fields": [],
        "sales_actual": {dim: _record_field(grouped["sales_overview"].get(dim), "actual") for dim in TIME_DIMENSIONS},
        "customer_decline_top3": [
            {
                "客户编码": record.customer_code,
                "客户名称": _customer_display_name(record),
                "下降金额": _record_field(record, "actual"),
            }
            for record in customer_declines
        ],
    }


def build_chapter3_stats(records: List[MetricRecord], grouped: Dict[str, Any]) -> Dict[str, Any]:
    conflicts = _find_conflicts(records)
    warnings = ["3.1 达成差额、同比增长率、同比差额按已确认公式计算"]
    return {
        "有效指标数": len(records),
        "销量概况数": sum(v is not None for v in grouped["sales_overview"].values()),
        "过程指标数": sum(v is not None for block in (grouped["active_customer"], grouped["landing_project"], grouped["sample_project"]) for v in block.values()),
        "产品销量金额指标数": len(grouped["product_amount"]),
        "产品销售量指标数": len(grouped["product_volume"]),
        "行业销量指标数": len(grouped["industry_volume"]),
        "行业占比指标数": len(grouped["industry_share"]),
        "conflicts": conflicts,
        "warnings": warnings,
    }


def build_chapter3_field_audit(records: Sequence[MetricRecord], period: str = "") -> List[Dict[str, str]]:
    """生成 ApiPost 核对行。每个搜索串均可直接复制。"""
    rows: List[Dict[str, str]] = []
    for record in records:
        if record.path.startswith("三、销量分析-各产品") or record.path.startswith("三、销量分析-各行业"):
            position = "3.3/明细"
            fields = (("实际值", record.actual), ("同期数", record.yoy))
        elif record.path == "三、销量分析-销量-销量":
            position = f"3.1/{record.date_type}"
            fields = (("目标值", record.target), ("实际值", record.actual), ("达成率", record.achievement_rate))
        elif record.path in {"三、销量分析-招商生效客户", "三、销量分析-有效项目落地"}:
            position = f"3.2/{record.name}/{record.date_type}"
            fields = (("目标值", record.target), ("实际值", record.actual), ("扣分值", record.deduction), ("达成率", record.achievement_rate))
        elif record.path == "三、销量分析-打样项目数":
            position = f"3.2/打样项目数/{record.date_type}"
            fields = (("实际值", record.actual), ("同期数", record.yoy))
        elif record.path in {
            "三、销量分析-销量-产销客户数",
            "三、销量分析-销量-产销项目数",
            "三、销量分析-销量-客均销量",
            "三、销量分析-销量-单项目销量",
        }:
            position = f"3.3/{record.name}"
            fields = (("实际值", record.actual), ("同期数", record.yoy))
        elif _is_customer_decline_detail(record):
            position = f"3.3/客户下降金额前三/{_customer_display_name(record)}"
            fields = (("客户名称", record.customer_name), ("实际值", record.actual))
        elif record.name in {"20个存量生效客户", "100个出货项目"}:
            position = f"3.2/年度目标/{record.name}"
            fields = (("目标值", record.target), ("实际值", record.actual), ("扣分值", record.deduction))
        else:
            continue
        search = f'"指标路径": "{record.path}"<br>"日期类型": "{record.date_type}"'
        if record.customer_name:
            search += f'<br>"客户名称": "{record.customer_name}"'
        for field, value in fields:
            raw = _raw_text(value)
            report = _with_unit(raw, record.unit, percent=(field == "达成率")) if raw is not None else "待补充"
            rows.append({
                "report_position": position,
                "search": search,
                "value_field": f'"指标数据"."{field}"',
                "raw_value": raw or "待补充",
                "report_value": report,
                "processing": "原值+单位，不舍入" if raw is not None else "不计算",
                "status": "正常" if raw is not None else "待补充",
            })
    return rows


def build_chapter3_apipost_checklist(records: Sequence[MetricRecord], period: str = "") -> str:
    """按第一章格式生成五列 ApiPost 核对清单。"""
    lines = [
        "# 第三章 ApiPost 取数核对清单", "",
        "使用方法：复制“ApiPost 搜索内容”到响应 JSON 中搜索，然后查看“取值字段”。", "",
        "| 报告位置 | ApiPost 搜索内容 | 取值字段 | 报告值 | 状态 |",
        "| --- | --- | --- | --- | --- |",
    ]

    for record in records:
        if record.path == "三、销量分析-销量-销量":
            position = f"3.1/销量概况/{record.date_type}"
            fields = (("目标值", record.target), ("实际值", record.actual), ("达成率", record.achievement_rate))
        elif record.path in {"三、销量分析-招商生效客户", "三、销量分析-有效项目落地"}:
            position = f"3.2/{record.name}/{record.date_type}"
            fields = (("目标值", record.target), ("实际值", record.actual), ("扣分值", record.deduction), ("达成率", record.achievement_rate))
        elif record.name in {"20个存量生效客户", "100个出货项目"}:
            position = f"3.2/年度目标/{record.name}"
            fields = (("目标值", record.target), ("实际值", record.actual), ("扣分值", record.deduction))
        elif record.path == "三、销量分析-打样项目数":
            position = f"3.2/打样项目数/{record.date_type}"
            fields = (("实际值", record.actual), ("同期数", record.yoy))
        elif record.path.startswith("三、销量分析-各产品销量-"):
            position = f"3.3/产品收入/{record.name}"
            fields = (("实际值", record.actual), ("同期数", record.yoy))
        elif record.path.startswith("三、销量分析-各产品销售量-"):
            position = f"3.3/产品销售量/{record.name}"
            fields = (("实际值", record.actual), ("同期数", record.yoy))
        elif record.path.startswith("三、销量分析-各行业销量占比-"):
            position = f"3.3/行业占比/{record.name}"
            fields = (("实际值", record.actual), ("同期数", record.yoy))
        elif record.path.startswith("三、销量分析-各行业销量-"):
            position = f"3.3/行业销量/{record.name}"
            fields = (("实际值", record.actual), ("同期数", record.yoy))
        elif _is_customer_decline_detail(record):
            position = f"3.3/客户下降金额前三/{_customer_display_name(record)}"
            fields = (("客户名称", record.customer_name), ("实际值", record.actual))
        else:
            continue

        search_name = record.name if record.name else ""
        search = (
            f'`"指标名称": "{search_name}"` '
            f'`"指标路径": "{record.path}"` '
            f'`"日期类型": "{record.date_type}"`'
        )
        if record.customer_name:
            search += f' `"客户名称": "{record.customer_name}"`'
        field_text = " ".join(f'`"{name}"`' for name, _value in fields)
        values = " / ".join(_raw_text(value) or "待补充" for _name, value in fields)
        lines.append(f"| {position} | {search} | {field_text} | `{values}` | 正常 |")
        if record.path == "三、销量分析-打样项目数":
            gap = _calculated_gap(record, include_unit=False)
            growth = _calculated_growth_rate(record)
            lines.append(
                f"| 3.2/打样项目数/{record.date_type}/差距 | {search} | `\"实际值\"` `\"同期数\"` | `{gap}` | "
                "代码计算：实际值 - 同期数 |"
            )
            lines.append(
                f"| 3.2/打样项目数/{record.date_type}/增长率 | {search} | `\"实际值\"` `\"同期数\"` | `{growth}` | "
                "代码计算：（实际值 - 同期数）÷同期数×100%，四舍五入保留2位小数 |"
            )
        if record.date_type == "年" and (
            record.path.startswith("三、销量分析-各产品")
            or record.path.startswith("三、销量分析-各行业销量-")
            or record.path in {
                "三、销量分析-销量-产销客户数",
                "三、销量分析-销量-产销项目数",
                "三、销量分析-销量-客均销量",
                "三、销量分析-销量-单项目销量",
            }
        ):
            growth = _calculated_growth_rate(record)
            lines.append(
                f"| {position}/同比增长率 | {search} | `\"实际值\"` `\"同期数\"` | `{growth}` | "
                "代码计算：（实际值 - 同期数）÷同期数×100%，四舍五入保留2位小数 |"
            )
        if record.date_type == "年" and record.path.startswith("三、销量分析-各行业销量占比-"):
            change = _share_change_text(record)
            lines.append(
                f"| {position}/占比变化 | {search} | `\"实际值\"` `\"同期数\"` | `{change}` | "
                "代码计算：|本期占比 - 同期占比|，四舍五入保留2位小数 |"
            )

    customer_sales_records = _customer_sales_records(records)
    has_customer_decline_detail = any(
        _is_customer_decline_detail(record) and record.customer_name
        for record in records
    )
    has_negative_customer_decline = bool(_customer_sales_decline_top3(customer_sales_records))
    if not has_customer_decline_detail:
        lines.append('| 3.3/客户下降金额前三明细 | `"指标名称": "客户销量下降金额"` |  | `不展示` | 接口未提供客户下降明细 |')

    if has_negative_customer_decline:
        customer_confirm_text = "客户下降金额前三明细已按接口行级 `\"客户名称\"` 与 `\"实际值\"` 取数，仅展示负数下降金额。"
    elif has_customer_decline_detail:
        customer_confirm_text = "客户下降金额前三明细未出现负数下降金额，报告不展示该句。"
    else:
        customer_confirm_text = "客户下降金额前三明细未提供，报告不展示该句。"
    lines.extend([
        "", "## 需要特别确认", "",
        f"第三章接口中的同名记录通过 `\"日期类型\"` 区分月、季、年口径。3.1 目标、实际、达成率直接取数据集；达成差额、同比增长率、同比差额按已确认公式计算。{customer_confirm_text}",
    ])
    return "\n".join(lines) + "\n"


class Chapter3Generator:
    def __init__(self, data: Any, guideline: str = "", period: str = "", sale_id: Optional[str] = None, sale_name: Optional[str] = None):
        self.raw_data, self.guideline, self.period = data, guideline, period
        self.sale_id, self.sale_name = sale_id, sale_name

    def run(self) -> str:
        return format_chapter3_data(self.raw_data, self.period)[0]

    async def run_async(self) -> str:
        return self.run()


def _unique_record(records: Sequence[MetricRecord], name: str, path: str, date_type: str) -> Tuple[Optional[MetricRecord], str]:
    matches = [r for r in records if r.name == name and r.path == path and r.date_type == date_type]
    if not matches:
        return None, "missing"
    signatures = {(str(r.actual), str(r.target), str(r.yoy), str(r.deduction), str(r.achievement_rate), r.unit) for r in matches}
    if len(signatures) != 1:
        return None, "conflict"
    return matches[0], "normal" if len(matches) == 1 else "duplicate_same_value"


def _sales_overview_record(records: Sequence[MetricRecord], date_type: str) -> Optional[MetricRecord]:
    """合并销量概况中的目标记录与实际记录。

    数据集将销量目标与销量实际分别放在两个明确路径下，
    本函数按字段职责取值，不依赖数组顺序。
    """
    allowed_paths = {"三、销量分析-销量", "三、销量分析-销量-销量"}
    matches = [
        record for record in records
        if record.name == "销量" and record.path in allowed_paths and record.date_type == date_type
    ]
    if not matches:
        return None

    actual_candidates = [record for record in matches if (_decimal(record.actual) or Decimal("0")) != 0]
    actual_record = _single_consistent_record(actual_candidates, "actual")
    if actual_record is None:
        actual_record = _single_consistent_record(matches, "actual")
    target_record = _single_consistent_record(
        [record for record in matches if (_decimal(record.target) or Decimal("0")) != 0],
        "target",
    )
    rate_record = _single_consistent_record(
        [record for record in matches if (_decimal(record.achievement_rate) or Decimal("0")) != 0],
        "achievement_rate",
    )
    if actual_record is None and target_record is None and rate_record is None:
        return None
    source = actual_record or target_record or rate_record
    calculated_rate = None
    if rate_record is None and actual_record is not None and target_record is not None:
        actual_value = _decimal(actual_record.actual)
        target_value = _decimal(target_record.target)
        if actual_value is not None and target_value not in (None, Decimal("0")):
            calculated_rate = actual_value / target_value * Decimal("100")
    return MetricRecord(
        name="销量",
        path="三、销量分析-销量-销量",
        date_type=date_type,
        actual=actual_record.actual if actual_record else None,
        target=target_record.target if target_record else None,
        yoy=(target_record.yoy if target_record and target_record.yoy is not None else actual_record.yoy if actual_record else None),
        deduction=None,
        achievement_rate=rate_record.achievement_rate if rate_record else calculated_rate,
        unit=source.unit,
    )


def _single_consistent_record(records: Sequence[MetricRecord], field: str) -> Optional[MetricRecord]:
    values = {str(getattr(record, field)) for record in records if getattr(record, field) is not None}
    if len(values) != 1:
        return None
    return records[0] if records else None


def _unique_by_name_path(records: Sequence[MetricRecord], name: str, path: str) -> Optional[MetricRecord]:
    matches = [r for r in records if r.name == name and r.path == path]
    return matches[0] if len(matches) == 1 else None


def _records_with_path_prefix(records: Sequence[MetricRecord], prefix: str) -> List[MetricRecord]:
    selected = [r for r in records if r.path.startswith(prefix) and r.date_type == "年"]
    keys: Dict[Tuple[str, str, str], List[MetricRecord]] = {}
    for record in selected:
        keys.setdefault((record.name, record.path, record.date_type), []).append(record)
    return sorted([items[0] for items in keys.values() if len({str(x) for x in items}) == 1], key=lambda r: (r.name, r.path))


def _customer_sales_records(records: Sequence[MetricRecord]) -> List[MetricRecord]:
    """提取客户级销量明细；汇总指标不会被当作客户名称。"""
    prefixes = (
        "三、销量分析-各客户销量-",
        "三、销量分析-客户销量-",
        "三、销量分析-客户销量下降金额-",
    )
    aggregate_names = {"产销客户数", "客均销量", "招商生效客户", "20个存量生效客户"}
    return [
        record
        for record in records
        if record.date_type == "年"
        and record.name not in aggregate_names
        and (any(record.path.startswith(prefix) for prefix in prefixes) or _is_customer_decline_detail(record))
    ]


def _record_field(record: Optional[MetricRecord], field: str, percent: bool = False) -> str:
    if record is None:
        return MISSING
    raw = _raw_text(getattr(record, field))
    return MISSING if raw is None else _with_unit(raw, record.unit, percent)


def _dimension_amount_field(record: Optional[MetricRecord], field: str = "actual") -> str:
    """第三章 3.3 摘要金额展示：万口径取整，避免影响表格和核对清单。"""
    if record is None:
        return MISSING
    value = _decimal(getattr(record, field))
    if value is None:
        return MISSING
    if record.unit in {"万", "万元"}:
        return f"{_format_fixed(value, 0)}{record.unit}"
    return _record_field(record, field)


def _integer_record_field(record: Optional[MetricRecord], field: str, unit: str) -> str:
    if record is None:
        return MISSING
    value = _decimal(getattr(record, field))
    if value is None:
        return MISSING
    return f"{_format_fixed(value, 0)}{unit}"


def _integer_sample_gap(record: Optional[MetricRecord]) -> str:
    if record is None:
        return MISSING
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return MISSING
    return f"{_format_fixed(actual - yoy, 0)}个"


def _integer_sample_growth_rate(record: Optional[MetricRecord]) -> str:
    if record is None:
        return MISSING
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return MISSING
    if yoy == 0:
        return "100%" if actual != 0 else "0%"
    rate = (actual - yoy) / yoy * Decimal("100")
    return f"{_format_fixed(rate, 0)}%"


def _format_fixed(value: Decimal, places: int) -> str:
    quantizer = Decimal("1").scaleb(-places)
    rounded = value.quantize(quantizer, rounding=ROUND_HALF_UP)
    return format(rounded, f".{places}f")


def _sales_direct_field(record: Optional[MetricRecord], field: str) -> str:
    if record is None:
        return MISSING
    value = _decimal(getattr(record, field))
    if value is None:
        return MISSING
    if field == "achievement_rate":
        return f"{_format_fixed(value, 1)}%"
    return _format_fixed(value, 2)


def _sales_achievement_gap(record: Optional[MetricRecord]) -> str:
    if record is None:
        return MISSING
    target, actual = _decimal(record.target), _decimal(record.actual)
    if target is None or actual is None:
        return MISSING
    return _format_fixed(target - actual, 2)


def _sales_yoy_gap(record: Optional[MetricRecord]) -> str:
    if record is None:
        return MISSING
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return MISSING
    return _format_fixed(actual - yoy, 2)


def _sales_yoy_growth_rate(record: Optional[MetricRecord]) -> str:
    if record is None:
        return MISSING
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return MISSING
    if yoy == 0:
        rate = Decimal("100")
    elif yoy < 0:
        rate = (actual - yoy) / abs(yoy) * Decimal("100")
    else:
        rate = (actual / yoy - Decimal("1")) * Decimal("100")
    return f"{_format_fixed(rate, 1)}%"


def _with_unit(raw: str, unit: str, percent: bool = False) -> str:
    if percent:
        return f"{raw}%"
    return f"{raw}{unit}" if unit else raw


def _raw_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)


def _direction_names(records: Sequence[MetricRecord]) -> Tuple[List[str], List[str]]:
    positive, risk = [], []
    for record in records:
        actual, yoy = _decimal(record.actual), _decimal(record.yoy)
        if actual is None or yoy is None:
            continue
        if actual > yoy:
            positive.append(record.name)
        elif actual < yoy:
            risk.append(record.name)
    return sorted(set(positive)), sorted(set(risk))


def _process_direction_names(process: Dict[str, Optional[MetricRecord]]) -> Tuple[List[str], List[str]]:
    return _direction_names([r for r in process.values() if r is not None])


def _names_or_missing(names: Sequence[str]) -> str:
    return "、".join(names) if names else MISSING


def _decimal(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value)) if value is not None and str(value).strip() else None
    except InvalidOperation:
        return None


def _is_count_negative(record: Optional[MetricRecord]) -> bool:
    if record is None:
        return False
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    return actual is not None and yoy is not None and actual < yoy


def _calculated_gap(record: Optional[MetricRecord], include_unit: bool = True) -> str:
    if record is None:
        return MISSING
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return MISSING
    difference = actual - yoy
    value = _format_fixed(difference, 0) if record.unit in {"个", "家", "人", "项", "次"} else str(difference)
    return f"{value}{record.unit}" if include_unit and record.unit else value


def _process_change_is_negative(record: Optional[MetricRecord]) -> bool:
    actual = _decimal(record.actual) if record else None
    yoy = _decimal(record.yoy) if record else None
    return actual is not None and yoy is not None and actual - yoy < 0


def _process_change_text(record: Optional[MetricRecord], label: str) -> str:
    if record is None:
        return f"{label}同比{MISSING}（增减{MISSING}）"
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return f"{label}同比{MISSING}（增减{MISSING}）"

    difference = actual - yoy
    rate = _growth_percent(record)
    if rate is None:
        return f"{label}同比{MISSING}（增减{MISSING}）"

    unit = record.unit or ""
    difference_text = _format_fixed(abs(difference), 0) if unit in {"个", "家", "人", "项", "次"} else str(abs(difference))
    rate_text = abs(rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rate > 0:
        return f"{label}同比增长{rate_text:.2f}%（增加{difference_text}{unit}）"
    if rate < 0:
        return f"{label}同比下降{rate_text:.2f}%（减少{difference_text}{unit}）"
    return f"{label}同比持平（增减{difference_text}{unit}）"


def _calculated_growth_rate(record: Optional[MetricRecord]) -> str:
    if record is None:
        return MISSING
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return MISSING
    if yoy == 0:
        return "100.00%" if actual != 0 else "0.00%"
    rate = ((actual - yoy) / yoy * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rate:.2f}%"


def _growth_percent(record: Optional[MetricRecord]) -> Optional[Decimal]:
    if record is None:
        return None
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return None
    if yoy == 0:
        return Decimal("100") if actual != 0 else Decimal("0")
    return (actual - yoy) / yoy * Decimal("100")


def _absolute_growth_text(record: Optional[MetricRecord]) -> str:
    rate = _growth_percent(record)
    if rate is None:
        return MISSING
    rounded = abs(rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:.2f}%"


def _share_change(record: Optional[MetricRecord]) -> Optional[Decimal]:
    if record is None:
        return None
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None:
        return None
    return actual - yoy


def _share_change_text(record: Optional[MetricRecord]) -> str:
    change = _share_change(record)
    if change is None:
        return MISSING
    rounded = abs(change).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:.2f}%"


def _positive_product_text(records: Sequence[MetricRecord]) -> str:
    if not records:
        return "无明显增长产品"
    return "、".join(
        f"{record.name}{_dimension_amount_field(record)}（↑{_absolute_growth_text(record)}）"
        for record in records
    )


def _risk_product_text(records: Sequence[Tuple[MetricRecord, MetricRecord]]) -> str:
    if not records:
        return "无明显下降产品"
    return "；".join(
        f"{amount.name}{_dimension_amount_field(amount)}（↓{_absolute_growth_text(amount)}），销售量下降{_absolute_growth_text(volume)}"
        for amount, volume in records
    )


def _risk_product_pairs(grouped: Dict[str, Any]) -> List[Tuple[MetricRecord, MetricRecord]]:
    amount_by_name = {record.name: record for record in grouped["product_amount"]}
    volume_by_name = {record.name: record for record in grouped["product_volume"]}
    return sorted(
        [
            (amount, volume_by_name[amount.name])
            for amount in amount_by_name.values()
            if amount.name in volume_by_name
            and (_growth_percent(amount) or Decimal("0")) < 0
            and (_growth_percent(volume_by_name[amount.name]) or Decimal("0")) < 0
        ],
        key=lambda pair: _decimal(pair[0].actual) or Decimal("0"),
        reverse=True,
    )[:3]


def _positive_industry_text(records: Sequence[Tuple[MetricRecord, MetricRecord]]) -> str:
    if not records:
        return "无明显增长行业"
    return "；".join(
        f"{amount.name}行业收入增长{_absolute_growth_text(amount)}，占比增长{_share_change_text(share)}"
        for amount, share in records
    )


def _risk_industry_text(records: Sequence[Tuple[MetricRecord, MetricRecord]]) -> str:
    if not records:
        return "无明显下降行业"
    output = []
    for amount, share in records:
        change = _share_change(share)
        direction = "下降" if change is not None and change < 0 else "增长"
        output.append(
            f"{amount.name}行业收入下降{_absolute_growth_text(amount)}，占比{direction}{_share_change_text(share)}"
        )
    return "；".join(output)


def _customer_sales_decline_top3(records: Sequence[MetricRecord]) -> List[MetricRecord]:
    candidates = [(record, _customer_decline_amount(record)) for record in records]
    negative = [(record, value) for record, value in candidates if value is not None and value < 0]
    return [record for record, _value in sorted(negative, key=lambda item: item[1])[:3]]


def _customer_decline_amount(record: MetricRecord) -> Optional[Decimal]:
    actual = _decimal(record.actual)
    yoy = _decimal(record.yoy)
    if "下降金额" in record.path:
        return actual
    if actual is None or yoy is None:
        return None
    return actual - yoy


def _customer_names_or_missing(records: Sequence[MetricRecord]) -> str:
    names = [_customer_display_name(record) for record in records]
    names = [name for name in names if name]
    return "、".join(names) if names else MISSING


def _customer_decline_names_with_amount_or_empty(records: Sequence[MetricRecord]) -> str:
    items = []
    for record in records:
        name = _customer_display_name(record)
        amount = _customer_decline_amount(record)
        if not name or amount is None:
            continue
        unit = record.unit or "万"
        rounded_amount = abs(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        items.append(f"{name}（↓{rounded_amount:.0f}{unit}）")
    return "、".join(items)


def _customer_display_name(record: MetricRecord) -> str:
    return (record.customer_name or record.name or record.customer_code).strip()


def _is_customer_decline_detail(record: MetricRecord) -> bool:
    return record.path == "三、销量分析-销量-销量下降金额前三的客户"


def _find_conflicts(records: Sequence[MetricRecord]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, str, str], List[MetricRecord]] = {}
    for r in records:
        grouped.setdefault((r.name, r.path, r.date_type, r.customer_code, r.customer_name), []).append(r)
    output = []
    for key, items in grouped.items():
        signatures = {(str(r.actual), str(r.target), str(r.yoy), str(r.deduction), str(r.achievement_rate), r.unit) for r in items}
        if len(signatures) > 1:
            output.append({"match": key, "values": sorted(signatures)})
    return output


def _extract_chapter_rows(raw_data: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_data, list):
        rows = raw_data
    elif isinstance(raw_data, dict) and isinstance(raw_data.get("章节数据"), list):
        rows = raw_data["章节数据"]
    elif isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
        rows = raw_data["data"].get("章节数据")
    else:
        rows = None
    if not isinstance(rows, list) or not rows:
        raise ChapterDataError(f"第三章数据清洗失败: 章节数据为空或结构错误。{EMPTY_DATA_MESSAGE}")
    return rows


def _normalize_metric_path(path: str) -> str:
    return path.strip().rstrip("-").strip()


def _path_group_and_leaf(path: str) -> Tuple[str, str]:
    parts = [part.strip() for part in _normalize_metric_path(path).split("-")]
    group = parts[1] if len(parts) > 1 else ""
    leaf = next((p for p in reversed(parts[1:]) if p), "")
    return group, leaf


def month_labels(period: str) -> Tuple[str, str]:
    return current_and_ytd_labels(period)
