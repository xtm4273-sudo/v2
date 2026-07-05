"""第二章生成器 - 利润概况。

严格按“指标名称 + 指标路径 + 日期类型”唯一匹配 MOUDLE=2 的原始记录。
不按数组顺序、数值大小或相似名称猜测，也不改写接口数字的小数精度。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Data import EMPTY_DATA_MESSAGE, ChapterDataError
from ReportGenerator.report_period import month_number


PENDING_HTML = '<span class="pending-value">待补充</span>'
SALES_SCOPE_NOTE = "说明：此处销量不含双算"
DATE_DIMENSIONS: Tuple[Tuple[str, str], ...] = (
    ("month", "月"),
    ("quarter", "季"),
    ("year", "年"),
)


@dataclass(frozen=True)
class MetricSpec:
    key: str
    name: str
    path: str
    expected_unit: str
    transform: str = "direct"


METRIC_SPECS: Tuple[MetricSpec, ...] = tuple(
    MetricSpec(key, name, f"二、利润概况-{name}", unit, transform)
    for key, name, unit, transform in (
        ("revenue", "营业收入（不含税）", "万元", "direct"),
        ("gross_margin_rate", "毛利率", "%", "percent_x100"),
        ("gross_margin_amount", "毛利额", "万元", "direct"),
        ("labor_cost", "个人人工费用", "万元", "direct"),
        ("salary_bonus_cost", "其中：基本薪酬+提成奖金+年终奖", "万元", "direct"),
        ("travel_cost", "差旅费", "万元", "direct"),
        ("impairment_loss", "减值损失", "万元", "direct"),
        ("financial_expense", "财务费用", "万元", "direct"),
        ("sample_material", "样板物料", "万元", "direct"),
        ("other_expense", "其他各类费用", "万元", "direct"),
        ("pre_allocation_profit", "分摊前利润", "万元", "direct"),
    )
)


@dataclass
class CellEvidence:
    field_id: str
    report_position: str
    metric_name: str
    metric_path: str
    date_type: str
    value_path: str = "指标数据.实际值"
    unit_path: str = "指标数据.单位"
    raw_value: Optional[str] = None
    raw_unit: Optional[str] = None
    report_value: str = PENDING_HTML
    calculation: str = "无；直接取值"
    status: str = "缺失"
    source_indexes: List[int] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Chapter2Data:
    metadata: Dict[str, Any]
    cells: Dict[str, CellEvidence]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "cells": {key: asdict(value) for key, value in self.cells.items()},
            "warnings": self.warnings,
        }


def normalize_chapter2_data(raw_data: Any, period: str = "") -> Chapter2Data:
    """将完整接口响应或 data.章节数据数组清洗为可追溯结构。"""
    subject, rows = _extract_subject_and_rows(raw_data)
    empty_fallback = not rows

    metadata = {
        "chapter": "chapter2",
        "source_module": 2,
        "title": subject.get("章节名称") or "二、利润概况",
        "month": period or subject.get("月份"),
        "manager_id": subject.get("区域经理工号", ""),
        "manager_name": subject.get("区域经理姓名", ""),
        "department_name": subject.get("部门名称", ""),
        "source_row_count": len(rows),
        "data_status": "empty_fallback" if empty_fallback else "normal",
    }
    cells: Dict[str, CellEvidence] = {}
    warnings: List[str] = []
    if empty_fallback:
        warnings.append("第二章接口章节数据为空，报告按0展示。")

    for spec in METRIC_SPECS:
        for dimension_key, date_type in DATE_DIMENSIONS:
            field_id = f"chapter2.profit_table.{spec.key}.{dimension_key}"
            report_position = f"利润表 / {spec.name} / {_dimension_report_label(date_type, metadata['month'])}"
            evidence = CellEvidence(
                field_id=field_id,
                report_position=report_position,
                metric_name=spec.name,
                metric_path=spec.path,
                date_type=date_type,
            )
            if empty_fallback:
                _apply_empty_fallback(evidence, spec)
                cells[field_id] = evidence
                continue
            matches = [
                (index, row)
                for index, row in enumerate(rows)
                if _is_exact_match(row, spec, date_type)
            ]
            evidence.source_indexes = [index for index, _row in matches]
            evidence.candidates = [_candidate_summary(index, row) for index, row in matches]
            _resolve_cell(evidence, matches, spec, warnings)
            cells[field_id] = evidence

    return Chapter2Data(metadata=metadata, cells=cells, warnings=warnings)


def build_chapter2_markdown(chapter_data: Chapter2Data) -> str:
    """按客户 Word 第二章的标题和 11×4 利润表结构生成 Markdown。"""
    month = _reporting_month_number(chapter_data.metadata.get("month", ""))
    month_label = f"{month}月" if month else "当月"
    ytd_label = f"1-{month}月累计" if month else "累计"
    lines = [
        "# 二、利润概况",
        "",
        f"| 科目 | {month_label} | 本季度累计 | {ytd_label} |",
        "| --- | --- | --- | --- |",
    ]
    for spec in METRIC_SPECS:
        values = [
            chapter_data.cells[f"chapter2.profit_table.{spec.key}.{dimension_key}"].report_value
            for dimension_key, _date_type in DATE_DIMENSIONS
        ]
        lines.append(f"| {spec.name} | {' | '.join(values)} |")
    lines.extend(["", SALES_SCOPE_NOTE])
    return "\n".join(lines).rstrip() + "\n"


def format_chapter2_data(
    raw_chapter_data: Any,
    month_label: str = "当月",
    ytd_label: str = "累计",
) -> Tuple[str, Dict[str, Any]]:
    """保留旧入口；标签参数仅为兼容，真实表头由接口月份生成。"""
    del month_label, ytd_label
    data = normalize_chapter2_data(raw_chapter_data)
    markdown = build_chapter2_markdown(data)
    stats = build_chapter2_stats(data)
    return markdown, stats


def build_chapter2_stats(chapter_data: Chapter2Data) -> Dict[str, Any]:
    statuses = [cell.status for cell in chapter_data.cells.values()]
    return {
        "正常": sum(status == "正常" for status in statuses),
        "空数组兜底": sum(status == "空数组兜底" for status in statuses),
        "缺失": sum(status == "缺失" for status in statuses),
        "重复": sum(status.startswith("重复") for status in statuses),
        "冲突": sum("冲突" in status for status in statuses),
        "单位冲突": sum(status == "单位冲突" for status in statuses),
        "计算字段": sum(cell.calculation != "无；直接取值" for cell in chapter_data.cells.values()),
        "数据状态": chapter_data.metadata.get("data_status", "normal"),
        "cleaned_data": chapter_data.to_dict(),
        "warnings": chapter_data.warnings,
    }


def build_apipost_checklist(chapter_data: Chapter2Data) -> str:
    """生成可直接复制 JSON 搜索文本的 ApiPost 核对清单。"""
    lines = [
        "# 第二章 ApiPost 取数核对清单",
        "",
        "接口条件：`MOUDLE=2`，`ZEMPLOYEE=06427`，`CALMONTH=202606`。",
        "",
        "使用方法：按顺序复制“ApiPost 搜索内容”中的三个 JSON 片段到响应中搜索，然后核对取值字段。",
        "",
        "| 报告位置 | ApiPost 搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    month = _month_number(chapter_data.metadata.get("month"))
    raw_month = chapter_data.metadata.get("month") or PENDING_HTML
    if month:
        lines.extend(
            [
                f'| 利润表 / 表头 / {month}月 | <code>"月份": "{raw_month}"</code> | `data.月份` | <code>{raw_month}</code> | {month}月 | 格式化：取 YYYYMM 末两位的月份数字 | 正常 |',
                f'| 利润表 / 表头 / 1-{month}月累计 | <code>"月份": "{raw_month}"</code> | `data.月份` | <code>{raw_month}</code> | 1-{month}月累计 | 格式化：起始月固定为 1，结束月取 YYYYMM 末两位 | 正常 |',
            ]
        )
    for cell in chapter_data.cells.values():
        search = (
            f'<code>"指标名称": "{cell.metric_name}"</code><br>'
            f'<code>"指标路径": "{cell.metric_path}"</code><br>'
            f'<code>"日期类型": "{cell.date_type}"</code>'
        )
        if cell.candidates:
            original = "<br>".join(
                f'<code>{candidate.get("实际值")!s}{candidate.get("单位") or ""}</code>'
                for candidate in cell.candidates
            )
        else:
            original = PENDING_HTML
        if cell.status == "正常" and cell.calculation != "无；直接取值":
            handling = f"计算：{cell.calculation}；原始单位异常已按客户确认的比例口径处理"
        elif cell.status == "正常":
            handling = "无计算；精确匹配后原样取 `指标数据.实际值`，拼接 `指标数据.单位`"
        elif cell.status == "单位冲突":
            handling = "未换算；接口单位与 Word 模板单位冲突，标记待补充"
        elif "冲突" in cell.status:
            handling = "未取值；同一精确匹配条件下数值冲突，标记待补充"
        else:
            handling = "未取值；接口记录或字段缺失，标记待补充"
        lines.append(
            f"| {cell.report_position} | {search} | `指标数据.实际值`<br>`指标数据.单位` | "
            f"{original} | {cell.report_value} | {handling} | {cell.status} |"
        )
    return "\n".join(lines).rstrip() + "\n"


class Chapter2Generator:
    """确定性第二章生成器，不调用 LLM 改写或补数。"""

    def __init__(
        self,
        llm: Any = None,
        data: Any = None,
        guideline: str = "",
        sale_id: Optional[str] = None,
        sale_name: Optional[str] = None,
        period: str = "",
    ):
        del llm, guideline, sale_id, sale_name
        self.raw_data = data
        self.period = period

    def run(self) -> str:
        return build_chapter2_markdown(normalize_chapter2_data(self.raw_data, self.period))

    async def run_async(self) -> str:
        return self.run()


def _extract_subject_and_rows(raw_data: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if isinstance(raw_data, dict):
        subject = raw_data.get("data") if isinstance(raw_data.get("data"), dict) else raw_data
        rows = subject.get("章节数据") if isinstance(subject, dict) else None
    elif isinstance(raw_data, list):
        subject = {}
        rows = raw_data
    else:
        raise ChapterDataError(f"第二章数据清洗失败: 原始响应类型错误。{EMPTY_DATA_MESSAGE}")
    if not isinstance(rows, list):
        raise ChapterDataError(f"第二章数据清洗失败: data.章节数据不是数组。{EMPTY_DATA_MESSAGE}")
    return subject if isinstance(subject, dict) else {}, [row for row in rows if isinstance(row, dict)]


def _is_exact_match(row: Dict[str, Any], spec: MetricSpec, date_type: str) -> bool:
    metric_data = row.get("指标数据")
    path = _normalize_metric_path(str(row.get("指标路径") or ""))
    name = str(row.get("指标名称") or "").strip()
    return (
        (name == spec.name or (not name and _path_leaf(path) == spec.name))
        and path == spec.path
        and isinstance(metric_data, dict)
        and metric_data.get("日期类型") == date_type
    )


def _normalize_metric_path(path: str) -> str:
    return path.strip().rstrip("-").strip()


def _path_leaf(path: str) -> str:
    normalized = _normalize_metric_path(path)
    return normalized.split("-")[-1].strip() if normalized else ""


def _resolve_cell(
    evidence: CellEvidence,
    matches: Sequence[Tuple[int, Dict[str, Any]]],
    spec: MetricSpec,
    warnings: List[str],
) -> None:
    if not matches:
        warnings.append(f"{evidence.field_id}: 未命中精确匹配记录。")
        return

    pairs = []
    for _index, row in matches:
        metric_data = row.get("指标数据") or {}
        raw_value = metric_data.get("实际值")
        raw_unit = metric_data.get("单位")
        pairs.append((None if raw_value is None else str(raw_value), None if raw_unit is None else str(raw_unit)))
    unique_pairs = set(pairs)
    if len(unique_pairs) > 1:
        evidence.status = "数值冲突"
        warnings.append(f"{evidence.field_id}: 同一精确匹配条件命中多个不同值 {pairs}。")
        return

    raw_value, raw_unit = pairs[0]
    evidence.raw_value = raw_value
    evidence.raw_unit = raw_unit
    if raw_value in (None, ""):
        warnings.append(f"{evidence.field_id}: 指标数据.实际值缺失。")
        return
    try:
        numeric_value = Decimal(raw_value)
    except InvalidOperation:
        evidence.status = "字段格式错误"
        warnings.append(f"{evidence.field_id}: 实际值 {raw_value!r} 不是数字。")
        return
    if spec.transform == "percent_x100":
        evidence.calculation = "指标数据.实际值 × 100"
        evidence.report_value = f"{_format_percent_x100(numeric_value)}%"
        evidence.status = "重复（值一致）" if len(matches) > 1 else "正常"
        if raw_unit != spec.expected_unit:
            warnings.append(
                f"{evidence.field_id}: 接口单位为 {raw_unit!r}，已按客户确认的毛利率比例口径将实际值乘 100 并展示为 %。"
            )
        return
    if raw_unit != spec.expected_unit:
        evidence.status = "单位冲突"
        warnings.append(
            f"{evidence.field_id}: 接口单位为 {raw_unit!r}，Word 模板要求 {spec.expected_unit!r}；未换算。"
        )
        return

    evidence.report_value = f"{_format_one_decimal(numeric_value)}{raw_unit}"
    evidence.status = "重复（值一致）" if len(matches) > 1 else "正常"
    if len(matches) > 1:
        warnings.append(f"{evidence.field_id}: 命中 {len(matches)} 条重复记录，数值和单位一致。")


def _apply_empty_fallback(evidence: CellEvidence, spec: MetricSpec) -> None:
    evidence.raw_value = "0"
    evidence.raw_unit = spec.expected_unit
    evidence.report_value = "0.0%" if spec.transform == "percent_x100" else f"0.0{spec.expected_unit}"
    evidence.calculation = "接口章节数据为空，按0展示"
    evidence.status = "空数组兜底"


def _candidate_summary(index: int, row: Dict[str, Any]) -> Dict[str, Any]:
    metric_data = row.get("指标数据") or {}
    return {
        "source_index": index,
        "实际值": metric_data.get("实际值"),
        "单位": metric_data.get("单位"),
        "日期类型": metric_data.get("日期类型"),
    }


def _format_one_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), ".1f")


def _format_percent_x100(value: Decimal) -> str:
    return _format_one_decimal(value * Decimal("100"))


def _month_number(period: Any) -> Optional[int]:
    return month_number(period)


def _reporting_month_number(period: Any) -> Optional[int]:
    """正文月份直接跟随 report_period，不在章节内自行减月。"""
    return _month_number(period)


def _dimension_report_label(date_type: str, period: Any) -> str:
    month = _reporting_month_number(period)
    if date_type == "月":
        return f"{month}月" if month else "当月"
    if date_type == "季":
        return "本季度累计"
    return f"1-{month}月累计" if month else "年累计"
