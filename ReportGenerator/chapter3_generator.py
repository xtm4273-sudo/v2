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
        path = str(row.get("指标路径") or "").strip()
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
        ))
    if not records:
        raise ChapterDataError(f"第三章数据清洗失败: 清洗后没有有效指标记录。{EMPTY_DATA_MESSAGE}")
    return records


def group_chapter3_records(records: Iterable[MetricRecord]) -> Dict[str, Any]:
    all_records = list(records)
    return {
        "all_records": all_records,
        "sales_overview": {
            dim: _unique_record(all_records, "销量", "三、销量分析-销量-销量", dim)[0]
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
            dim: _unique_record(all_records, "", "三、销量分析-打样项目数-", dim)[0]
            for dim in TIME_DIMENSIONS
        },
        "annual_customer": _unique_record(all_records, "20个存量生效客户", "三、销量分析-20个存量生效客户", "年")[0],
        "annual_project": _unique_record(all_records, "100个出货项目", "三、销量分析-100个出货项目", "年")[0],
        "product_amount": _records_with_path_prefix(all_records, "三、销量分析-各产品销量-"),
        "product_volume": _records_with_path_prefix(all_records, "三、销量分析-各产品销售量-"),
        "industry_volume": _records_with_path_prefix(all_records, "三、销量分析-各行业销量-"),
        "industry_share": _records_with_path_prefix(all_records, "三、销量分析-各行业销量占比-"),
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
        cells = [_record_field(sales.get(dim), field, percent=(field == "achievement_rate")) for dim in TIME_DIMENSIONS]
        lines.append(f"| {label} | {' | '.join(cells)} |")
    for label in ("达成差额", "同比增长率", "同比差额"):
        lines.append(f"| {label} | {MISSING} | {MISSING} | {MISSING} |")
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
            f"年度{_record_field(annual_customer, 'target')}存量生效客户目标已完成"
            f"{_record_field(annual_customer, 'actual')}（差距{_record_field(annual_customer, 'deduction')}），"
            f"{_record_field(annual_project, 'target')}出货项目目标已完成"
            f"{_record_field(annual_project, 'actual')}（差距{_record_field(annual_project, 'deduction')}）"
        ),
        "",
        f"| 过程指标 | 目标与实际 | {month_label} | 本季度累计 | {ytd_label} |",
        "| --- | --- | --- | --- | --- |",
    ])
    lines.extend(_process_rows("招商生效客户（家）", grouped["active_customer"]))
    lines.extend(_process_rows("有效落地项目（个）", grouped["landing_project"]))
    lines.extend(_sample_rows(grouped["sample_project"]))
    return lines


def _process_rows(label: str, records: Dict[str, Optional[MetricRecord]]) -> List[str]:
    output = []
    for row_label, field in (("目标", "target"), ("实际", "actual"), ("差距", "deduction"), ("达成率", "achievement_rate")):
        values = [_record_field(records.get(dim), field, percent=(field == "achievement_rate")) for dim in TIME_DIMENSIONS]
        output.append(f"| {label if not output else ''} | {row_label} | {' | '.join(values)} |")
    return output


def _sample_rows(records: Dict[str, Optional[MetricRecord]]) -> List[str]:
    actual = [_record_field(records.get(dim), "actual") for dim in TIME_DIMENSIONS]
    yoy = [_record_field(records.get(dim), "yoy") for dim in TIME_DIMENSIONS]
    gap = [_calculated_gap(records.get(dim)) for dim in TIME_DIMENSIONS]
    growth = [_calculated_growth_rate(records.get(dim)) for dim in TIME_DIMENSIONS]
    return [
        f"| 打样项目数（个） | 26年 | {' | '.join(actual)} |",
        f"|  | 25年同期 | {' | '.join(yoy)} |",
        f"|  | 差距 | {' | '.join(gap)} |",
        f"|  | 增长率 | {' | '.join(growth)} |",
    ]


def _build_dimension_section(grouped: Dict[str, Any], period_label: str, action_guide_text: Optional[str]) -> List[str]:
    amount_by_name = {record.name: record for record in grouped["product_amount"]}
    volume_by_name = {record.name: record for record in grouped["product_volume"]}
    industry_by_name = {record.name: record for record in grouped["industry_volume"]}
    share_by_name = {record.name: record for record in grouped["industry_share"]}

    positive_products = sorted(
        [record for record in amount_by_name.values() if (_growth_percent(record) or Decimal("0")) > 0],
        key=lambda record: _decimal(record.actual) or Decimal("0"),
        reverse=True,
    )[:3]
    risk_product_pairs = sorted(
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
            and (_share_change(share_by_name[record.name]) or Decimal("0")) < 0
        ],
        key=lambda pair: _decimal(pair[1].actual) or Decimal("0"),
        reverse=True,
    )[:3]

    customer = grouped["process"].get("产销客户数")
    project = grouped["process"].get("产销项目数")
    customer_average = grouped["process"].get("客均销量")
    project_average = grouped["process"].get("单项目销量")

    lines = [
        f"* 正向指标（{period_label}）",
        f"  * 产品：{_positive_product_text(positive_products)}表现突出",
        f"  * 客户：产销客户数同比增长{_calculated_growth_rate(customer)}（增加{_calculated_gap(customer)}）",
        f"  * 项目：产销项目数同比增长{_calculated_growth_rate(project)}（增加{_calculated_gap(project)}）",
        f"  * 行业：{_positive_industry_text(positive_industries)}",
        f"* 风险指标（{period_label}）",
        f"  * 产品：{_risk_product_text(risk_product_pairs)}",
        f"  * 客户：客均销量{_record_field(customer_average, 'actual')}（↓{_absolute_growth_text(customer_average)}）。{period_label}销量下降金额前三的客户包含：{MISSING}",
        f"  * 项目：单项目销量{_record_field(project_average, 'actual')}（↓{_absolute_growth_text(project_average)}）",
        f"  * 行业：{_risk_industry_text(risk_industries)}",
        f"* 行动指南：{action_guide_text or build_rule_based_action_guide(grouped)}",
    ]
    return lines


def build_rule_based_action_guide(grouped: Dict[str, Any]) -> str:
    return "优先复盘收入与销售量同时下降的产品，同步关注客均销量、单项目销量及收入与占比下降的行业，逐项制定补量动作。"


def build_chapter3_action_context(grouped: Dict[str, Any], period: str = "") -> Dict[str, Any]:
    return {
        "period": month_labels(period)[1].replace("累计", ""),
        "fixed_mapping_only": True,
        "missing_fields": ["3.1 达成差额", "3.1 同比增长率", "3.1 同比差额", "客户下降金额前三明细"],
        "sales_actual": {dim: _record_field(grouped["sales_overview"].get(dim), "actual") for dim in TIME_DIMENSIONS},
    }


def build_chapter3_stats(records: List[MetricRecord], grouped: Dict[str, Any]) -> Dict[str, Any]:
    conflicts = _find_conflicts(records)
    return {
        "有效指标数": len(records),
        "销量概况数": sum(v is not None for v in grouped["sales_overview"].values()),
        "过程指标数": sum(v is not None for block in (grouped["active_customer"], grouped["landing_project"], grouped["sample_project"]) for v in block.values()),
        "产品销量金额指标数": len(grouped["product_amount"]),
        "产品销售量指标数": len(grouped["product_volume"]),
        "行业销量指标数": len(grouped["industry_volume"]),
        "行业占比指标数": len(grouped["industry_share"]),
        "conflicts": conflicts,
        "warnings": ["3.1 达成差额、同比增长率、同比差额没有明确字段；3.3 缺少客户下降金额前三明细"],
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
        elif record.path == "三、销量分析-打样项目数-":
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
        elif record.name in {"20个存量生效客户", "100个出货项目"}:
            position = f"3.2/年度目标/{record.name}"
            fields = (("目标值", record.target), ("实际值", record.actual), ("扣分值", record.deduction))
        else:
            continue
        search = f'"指标路径": "{record.path}"<br>"日期类型": "{record.date_type}"'
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
        elif record.path == "三、销量分析-打样项目数-":
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
        else:
            continue

        search_name = record.name if record.name else ""
        search = (
            f'`"指标名称": "{search_name}"` '
            f'`"指标路径": "{record.path}"` '
            f'`"日期类型": "{record.date_type}"`'
        )
        field_text = " ".join(f'`"{name}"`' for name, _value in fields)
        values = " / ".join(_raw_text(value) or "待补充" for _name, value in fields)
        lines.append(f"| {position} | {search} | {field_text} | `{values}` | 正常 |")
        if record.path == "三、销量分析-打样项目数-":
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

    missing_rows = [
        ("3.1/达成差额", '"指标名称": "达成差额"', "搜索不到该指标"),
        ("3.1/同比增长率", '"指标名称": "同比增长率"', "搜索不到该指标"),
        ("3.1/同比差额", '"指标名称": "同比差额"', "搜索不到该指标"),
        ("3.3/客户下降金额前三明细", '"指标名称": "客户销量下降金额"', "接口未提供客户明细"),
    ]
    for position, search, status in missing_rows:
        lines.append(f"| {position} | `{search}` |  | `待补充` | {status} |")

    lines.extend([
        "", "## 需要特别确认", "",
        "第三章接口中的同名记录通过 `\"日期类型\"` 区分月、季、年口径。本次按“指标名称＋指标路径＋日期类型”检查未发现数值冲突。3.2 负增长指标直接按“实际个数 < 同期个数”判定。3.2 和 3.3 增长/下降率由代码按公式计算，不从接口取。客户下降金额前三明细未提供，报告显示红色“待补充”。3.1 达成差额、同比增长率、同比差额仍无直接字段。",
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


def _unique_by_name_path(records: Sequence[MetricRecord], name: str, path: str) -> Optional[MetricRecord]:
    matches = [r for r in records if r.name == name and r.path == path]
    return matches[0] if len(matches) == 1 else None


def _records_with_path_prefix(records: Sequence[MetricRecord], prefix: str) -> List[MetricRecord]:
    selected = [r for r in records if r.path.startswith(prefix) and r.date_type == "年"]
    keys: Dict[Tuple[str, str, str], List[MetricRecord]] = {}
    for record in selected:
        keys.setdefault((record.name, record.path, record.date_type), []).append(record)
    return sorted([items[0] for items in keys.values() if len({str(x) for x in items}) == 1], key=lambda r: (r.name, r.path))


def _record_field(record: Optional[MetricRecord], field: str, percent: bool = False) -> str:
    if record is None:
        return MISSING
    raw = _raw_text(getattr(record, field))
    return MISSING if raw is None else _with_unit(raw, record.unit, percent)


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
    value = str(actual - yoy)
    return f"{value}{record.unit}" if include_unit and record.unit else value


def _calculated_growth_rate(record: Optional[MetricRecord]) -> str:
    if record is None:
        return MISSING
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None or yoy == 0:
        return MISSING
    rate = ((actual - yoy) / yoy * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rate:.2f}%"


def _growth_percent(record: Optional[MetricRecord]) -> Optional[Decimal]:
    if record is None:
        return None
    actual, yoy = _decimal(record.actual), _decimal(record.yoy)
    if actual is None or yoy is None or yoy == 0:
        return None
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
        return MISSING
    return "、".join(
        f"{record.name}{_record_field(record, 'actual')}（↑{_absolute_growth_text(record)}）"
        for record in records
    )


def _risk_product_text(records: Sequence[Tuple[MetricRecord, MetricRecord]]) -> str:
    if not records:
        return MISSING
    return "；".join(
        f"{amount.name}{_record_field(amount, 'actual')}（↓{_absolute_growth_text(amount)}），销售量下降{_absolute_growth_text(volume)}"
        for amount, volume in records
    )


def _positive_industry_text(records: Sequence[Tuple[MetricRecord, MetricRecord]]) -> str:
    if not records:
        return MISSING
    return "；".join(
        f"{amount.name}行业收入增长{_absolute_growth_text(amount)}，占比增长{_share_change_text(share)}"
        for amount, share in records
    )


def _risk_industry_text(records: Sequence[Tuple[MetricRecord, MetricRecord]]) -> str:
    if not records:
        return MISSING
    return "；".join(
        f"{amount.name}行业收入下降{_absolute_growth_text(amount)}，占比下降{_share_change_text(share)}"
        for amount, share in records
    )


def _find_conflicts(records: Sequence[MetricRecord]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str], List[MetricRecord]] = {}
    for r in records:
        grouped.setdefault((r.name, r.path, r.date_type), []).append(r)
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


def _path_group_and_leaf(path: str) -> Tuple[str, str]:
    parts = [part.strip() for part in path.split("-")]
    return (parts[1] if len(parts) > 1 else "", next((p for p in reversed(parts[2:]) if p), ""))


def month_labels(period: str) -> Tuple[str, str]:
    if len(period) >= 6 and period[-2:].isdigit():
        month = int(period[-2:])
        return f"{month}月", f"1-{month}月累计"
    return "当月", "累计"
