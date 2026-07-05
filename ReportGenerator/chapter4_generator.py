"""第四章生成器 - 毛利率与产品结构。

本模块对接 MOUDLE=4 的真实字段结构。映射只依赖完整的“指标路径”、
“指标名称”和“单位”；不依赖数组顺序、数值大小或近似名称。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple
import logging

from Data import EMPTY_DATA_MESSAGE, ChapterDataError

logger = logging.getLogger(__name__)

CHAPTER_NAME = "四、毛利率与产品结构"
PRICE_DIFF_CATEGORY = "各产品的均价差异"
SHARE_DIFF_CATEGORY = "各产品收入占比差异"
SHARE_DIFF_PATH_CATEGORIES = (SHARE_DIFF_CATEGORY, "各产品销量占比差异")
MISSING_MARK = '<span class="missing">待补充</span>'


@dataclass
class MetricEvidence:
    product_name: str
    category: str
    metric_path: str
    value_raw: str
    unit: str
    value_field: str = "指标数据.实际值"
    match_condition: str = ""
    status: str = "正常"
    raw_items: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "指标名称": self.product_name,
            "指标分类": self.category,
            "指标路径": self.metric_path,
            "匹配条件": self.match_condition,
            "取值字段": self.value_field,
            "原始值": self.value_raw,
            "单位": self.unit,
            "状态": self.status,
            "原始记录": self.raw_items,
        }


def format_chapter4_data(
    raw_data: Any,
    period: str = "",
    action_guide_actions: Optional[Dict[str, str]] = None,
    gross_margin_rate: Optional[str] = None,
    source_period: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """严格清洗第四章数据并生成客户模板 Markdown。"""
    subject = _extract_subject(raw_data)
    _validate_subject(subject, source_period or period)
    rows = _extract_chapter_rows(subject)
    empty_fallback = not rows
    evidence, conflicts, warnings = collect_metric_evidence(rows)
    if empty_fallback:
        warnings.append("第四章接口章节数据为空，报告按0展示。")
    analysis = analyze_chapter4_products(evidence)
    markdown = build_chapter4_markdown(
        evidence=evidence,
        gross_margin_rate=gross_margin_rate,
        analysis=analysis,
        empty_fallback=empty_fallback,
    )
    stats = build_chapter4_stats(
        subject,
        evidence,
        conflicts,
        warnings,
        period,
        analysis=analysis,
        empty_fallback=empty_fallback,
    )
    stats["接口校验月份"] = source_period or period
    stats["行动指南来源"] = "规则模板"
    return markdown, stats


async def format_chapter4_data_async(
    raw_data: Any,
    period: str = "",
    action_guide_writer: Optional[Any] = None,
    source_period: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """AI 不参与严格字段映射；保留异步签名以兼容现有调用。"""
    if action_guide_writer is not None:
        logger.info("第四章严格映射模式不使用 AI 补写缺失数据")
    markdown, stats = format_chapter4_data(raw_data, period=period, source_period=source_period)
    stats["行动指南来源"] = "strict_placeholder"
    return markdown, stats


def collect_metric_evidence(
    rows: Iterable[Dict[str, Any]],
) -> Tuple[List[MetricEvidence], List[Dict[str, Any]], List[str]]:
    """仅按完整路径 + 名称 + 单位收集接口证据。"""
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    warnings: List[str] = []

    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            warnings.append(f"第{index + 1}条记录不是对象")
            continue
        path = _normalize_metric_path(str(item.get("指标路径") or ""))
        name = str(item.get("指标名称") or "").strip() or _path_leaf(path)
        metric_data = item.get("指标数据")
        if not name or not path or not isinstance(metric_data, dict):
            warnings.append(f"第{index + 1}条记录缺少指标名称、指标路径或指标数据")
            continue

        category = _exact_category(path, name)
        if category is None:
            warnings.append(f"{name} 的指标路径无法精确匹配：{path}")
            continue
        unit = str(metric_data.get("单位") or "").strip()
        expected_unit = "%" if category == SHARE_DIFF_CATEGORY else None
        if expected_unit and unit != expected_unit:
            warnings.append(f"{path} 单位应为 {expected_unit}，实际为 {unit or '空'}")
            continue
        if category == PRICE_DIFF_CATEGORY and unit not in {"元/KG", "元/M2"}:
            warnings.append(f"{path} 均价差异单位未识别：{unit or '空'}")
            continue
        if "实际值" not in metric_data or metric_data.get("实际值") in (None, ""):
            warnings.append(f"{path} 缺少指标数据.实际值")
            continue
        groups.setdefault((name, path, unit), []).append(item)

    evidence: List[MetricEvidence] = []
    conflicts: List[Dict[str, Any]] = []
    for (name, path, unit), items in groups.items():
        raw_values = [str(item["指标数据"]["实际值"]) for item in items]
        category = _exact_category(path, name) or ""
        condition = (
            f'指标名称 == "{name}" 且 指标路径 == "{path}" '
            f'且 指标数据.单位 == "{unit}"'
        )
        if len(set(raw_values)) > 1:
            conflicts.append({
                "指标名称": name,
                "指标路径": path,
                "单位": unit,
                "冲突原始值": raw_values,
                "状态": "待补充",
            })
            continue
        evidence.append(MetricEvidence(
            product_name=name,
            category=category,
            metric_path=path,
            value_raw=raw_values[0],
            unit=unit,
            match_condition=condition,
            status="正常" if len(items) == 1 else "重复但值一致",
            raw_items=items,
        ))
    return evidence, conflicts, warnings


def normalize_chapter4_products(rows: Iterable[Dict[str, Any]]):
    """兼容旧入口；返回严格指标证据，不再合并猜测产品属性。"""
    evidence, conflicts, warnings = collect_metric_evidence(rows)
    warnings.extend(f"{item['指标名称']} 同名同路径数值冲突，待补充" for item in conflicts)
    return evidence, warnings


def analyze_chapter4_products(evidence: Iterable[MetricEvidence]) -> Dict[str, Any]:
    """计算价格升降、结构前三及固定行动指南所需产品集合。"""
    prices: Dict[str, Dict[str, Any]] = {}
    shares: Dict[str, Dict[str, Any]] = {}
    for item in evidence:
        if not item.raw_items:
            continue
        data = item.raw_items[0].get("指标数据") or {}
        actual, yoy = _decimal(data.get("实际值")), _decimal(data.get("同期数"))
        if actual is None:
            continue
        target = prices if item.category == PRICE_DIFF_CATEGORY else shares
        target[item.product_name] = {
            "name": item.product_name,
            "actual": actual,
            "yoy": yoy,
            "unit": item.unit,
        }

    structure_top3 = sorted(shares.values(), key=lambda item: item["actual"], reverse=True)[:3]
    comparable_prices = []
    for name, price in prices.items():
        share = shares.get(name)
        if share is None or price["yoy"] in (None, Decimal("0")):
            continue
        comparable_prices.append({**price, "share": share["actual"], "change": price["actual"] - price["yoy"]})

    price_up_top3 = sorted(
        (item for item in comparable_prices if item["change"] > 0),
        key=lambda item: item["share"],
        reverse=True,
    )[:3]
    price_down_top3 = sorted(
        (item for item in comparable_prices if item["change"] < 0),
        key=lambda item: item["share"],
        reverse=True,
    )[:3]
    for item in structure_top3:
        item["change"] = item["actual"] - item["yoy"] if item["yoy"] is not None else None

    return {
        "price_up_top3": price_up_top3,
        "price_down_top3": price_down_top3,
        "structure_top3": structure_top3,
    }


def build_rule_based_actions(analysis: Dict[str, Any]) -> Dict[str, str]:
    structure_up = [
        item["name"] for item in analysis.get("structure_top3", [])
        if item.get("change") is not None and item["change"] > 0
    ]
    price_down = [item["name"] for item in analysis.get("price_down_top3", [])]
    structure_action = (
        f"{'、'.join(structure_up)}产品收入占比提升。"
        if structure_up else "收入占比排名前三的产品中暂无占比提升产品。"
    )
    price_action = (
        f"稳住价格，重点稳住{'、'.join(price_down)}的价格。"
        if price_down else "稳住价格，当前暂无同比价格下降产品。"
    )
    return {"structure_action": structure_action, "price_action": price_action}


def extract_chapter2_gross_margin_rate(raw_data: Any) -> Optional[str]:
    """精确提取第二章本年累计毛利率，接口小数按百分比展示。"""
    subject = _extract_subject(raw_data)
    rows = subject.get("章节数据") if isinstance(subject, dict) else None
    if not isinstance(rows, list):
        return None
    matches = [
        row for row in rows
        if (str(row.get("指标名称") or "").strip() or _path_leaf(str(row.get("指标路径") or ""))) == "毛利率"
        and _normalize_metric_path(str(row.get("指标路径") or "")) == "二、利润概况-毛利率"
        and isinstance(row.get("指标数据"), dict)
        and row["指标数据"].get("日期类型") == "年"
    ]
    values = {_decimal(row["指标数据"].get("实际值")) for row in matches}
    values.discard(None)
    if len(values) != 1:
        return None
    return f"{_format_decimal(next(iter(values)) * Decimal('100'), 1)}%"


def _price_items_text(items: List[Dict[str, Any]], direction: str) -> str:
    if not items:
        return f"暂无明显均价{direction}产品"
    arrow = "↑" if direction == "上升" else "↓"
    return "、".join(
        f"{item['name']}{_format_price_value(item['actual'], item['unit'])}{item['unit']}"
        f"（同比{arrow}{_format_price_value(abs(item['change']), item['unit'])}{item['unit']}）"
        for item in items
    )


def _format_price_value(value: Decimal, unit: str) -> str:
    places = 1 if unit.lower() == "元/kg" else 2
    return _format_decimal(value, places)


def _structure_items_text(items: List[Dict[str, Any]]) -> str:
    if not items:
        return MISSING_MARK
    output = []
    for item in items:
        change = item.get("change")
        if change is None:
            change_text = "占比变化待确认"
        else:
            direction = "↑" if change >= 0 else "↓"
            change_text = f"占比{direction}{_format_decimal(abs(change), 1)}%"
        output.append(
            f"{item['name']}收入占比{_format_decimal(item['actual'], 1)}%（{change_text}）"
        )
    return "<br>".join(output)


def _decimal(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value)) if value is not None and str(value).strip() else None
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal, places: int) -> str:
    quantizer = Decimal("1").scaleb(-places)
    return format(value.quantize(quantizer, rounding=ROUND_HALF_UP), f".{places}f")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def build_chapter4_markdown(
    *_args: Any,
    action_guide_actions: Optional[Dict[str, str]] = None,
    evidence: Optional[List[MetricEvidence]] = None,
    gross_margin_rate: Optional[str] = None,
    analysis: Optional[Dict[str, Any]] = None,
    empty_fallback: bool = False,
    **_kwargs: Any,
) -> str:
    """按固定模板生成第四章；AI 参数仅为兼容旧调用，不覆盖规则结果。"""
    analysis = analysis or analyze_chapter4_products(evidence or [])
    price_up = _price_items_text(analysis["price_up_top3"], "上升")
    price_down = _price_items_text(analysis["price_down_top3"], "下降")
    structure = "暂无产品结构变化数据" if empty_fallback else _structure_items_text(analysis["structure_top3"])
    actions = build_rule_based_actions(analysis)
    margin = "0.0%" if empty_fallback else (gross_margin_rate or MISSING_MARK)
    lines = [
        "## 四、毛利率与产品结构",
        "",
        f"个人毛利率{margin}，主要受到产品价格下降以及低毛利产品占比增加影响。",
        "",
        "| 指标 | 详情 |",
        "| --- | --- |",
        f"| 价格变动 | **均价上升：** {price_up}<br>**均价下降：** {price_down} |",
        f"| 结构变化 | **收入占比排名前三的产品及占比变动：**<br>{structure} |",
    ]
    if not empty_fallback:
        lines.extend([
            "",
            "### 行动指南：",
            "",
            f"◇ **产品结构：** {actions['structure_action']}",
            "",
            f"◇ **价格：** {actions['price_action']}",
        ])
    return "\n".join(lines) + "\n"


def build_chapter4_stats(
    subject: Dict[str, Any],
    evidence: List[MetricEvidence],
    conflicts: List[Dict[str, Any]],
    warnings: List[str],
    period: str = "",
    analysis: Optional[Dict[str, Any]] = None,
    empty_fallback: bool = False,
) -> Dict[str, Any]:
    price = [item for item in evidence if item.category == PRICE_DIFF_CATEGORY]
    share = [item for item in evidence if item.category == SHARE_DIFF_CATEGORY]
    missing_fields = [] if empty_fallback else ["低毛利产品标识"]
    cleaned = {
        "employee_id": str(subject.get("区域经理工号") or ""),
        "month": str(subject.get("月份") or period),
        "department_code": subject.get("部门编码", ""),
        "department_name": subject.get("部门名称", ""),
        "manager_name": subject.get("区域经理姓名", ""),
        "chapter_name": subject.get("章节名称", CHAPTER_NAME),
        "module": 4,
        "metric_evidence": [item.to_dict() for item in evidence],
        "analysis": _json_safe(analysis or {}),
        "conflicts": conflicts,
        "missing_fields": missing_fields,
        "calculations": [
            "均价变化=当前均价-同期均价",
            "占比变化=当前占比-同期占比",
            "均价升降产品按当前收入占比排序取前三",
        ],
        "warnings": warnings,
        "data_status": "empty_fallback" if empty_fallback else "normal",
    }
    return {
        "均价差异正常证据数": len(price),
        "收入占比差异正常证据数": len(share),
        "冲突数": len(conflicts),
        "缺失字段": missing_fields,
        "计算字段": cleaned["calculations"],
        "数据状态": cleaned["data_status"],
        "warnings": warnings,
        "cleaned_data": cleaned,
    }


def build_chapter4_apipost_checklist(stats: Dict[str, Any]) -> str:
    """生成可直接复制 JSON 搜索片段的 ApiPost 核对清单。"""
    cleaned = stats["cleaned_data"]
    rows = [
        ("总结句/个人毛利率", '"指标名称": "个人毛利率"', "指标数据.实际值", "未提供", "待补充", "不计算，不推测", "待补充"),
        ("价格变动/当前均价", '"指标路径": "四、毛利率与产品结构-各产品的均价"', "指标数据.实际值", "未提供（只有均价差异）", "待补充", "不用差异值冒充当前均价", "待补充"),
        ("价格变动/方向", '"指标名称": "均价变动方向"', "指标数据.实际值", "未提供", "待补充", "不从扣分值正负猜测", "待补充"),
        ("结构变化/当前收入占比", '"指标路径": "四、毛利率与产品结构-各产品收入占比"', "指标数据.实际值", "未提供（只有收入占比差异）", "待补充", "不用差异值冒充当前占比", "待补充"),
        ("结构变化/占比排名前三", '"指标名称": "产品收入占比排名"', "指标数据.实际值", "未提供", "待补充", "不按差异值大小排序", "待补充"),
    ]
    for item in cleaned["metric_evidence"]:
        search = f'"指标路径": "{item["\u6307标\u8def\u5f84"]}"'
        raw = f'{item["\u539f\u59cb\u503c"]}{item["\u5355\u4f4d"]}'
        rows.append((
            f'接口证据/{item["指标分类"]}/{item["指标名称"]}',
            search,
            item["取值字段"],
            raw,
            "未展示",
            "保留原始精度；由于缺少当前值/方向/排名，不写入客户报告",
            item["状态"],
        ))
    for item in cleaned["conflicts"]:
        rows.append((
            f'接口冲突/{item["指标名称"]}',
            f'"指标路径": "{item["\u6307标\u8def\u5f84"]}"',
            "指标数据.实际值",
            " / ".join(item["冲突原始值"]),
            "待补充",
            "同名同路径值冲突，不取值",
            "待补充",
        ))

    lines = [
        "# 第四章 ApiPost 取数核对清单",
        "",
        "请将“ApiPost 搜索内容”整段复制到响应 JSON 中搜索。",
        "",
        "| 报告位置 | ApiPost 搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        escaped = [str(value).replace("|", "\\|") for value in row]
        lines.append("| " + " | ".join(f"`{v}`" if i in {1, 2, 3, 4} else v for i, v in enumerate(escaped)) + " |")
    return "\n".join(lines) + "\n"


def build_chapter4_action_context(subject: Dict[str, Any], *_args: Any, period: str = "", **_kwargs: Any) -> Dict[str, Any]:
    return {
        "manager_name": subject.get("区域经理姓名", ""),
        "employee_id": subject.get("区域经理工号", ""),
        "month": subject.get("月份", period),
        "chapter_name": subject.get("章节名称", CHAPTER_NAME),
        "missing_fields": ["个人毛利率", "当前产品均价", "当前产品收入占比", "收入占比排名", "明确方向字段"],
    }


class Chapter4Generator:
    def __init__(self, data: Any, guideline: str = "", period: str = "", sale_id: Optional[str] = None, sale_name: Optional[str] = None):
        self.raw_data = data
        self.period = period

    def run(self) -> str:
        return format_chapter4_data(self.raw_data, period=self.period)[0]

    async def run_async(self) -> str:
        return self.run()


def _exact_category(path: str, name: str) -> Optional[str]:
    path = _normalize_metric_path(path)
    if path == f"{CHAPTER_NAME}-{PRICE_DIFF_CATEGORY}-{name}":
        return PRICE_DIFF_CATEGORY
    if any(path == f"{CHAPTER_NAME}-{category}-{name}" for category in SHARE_DIFF_PATH_CATEGORIES):
        return SHARE_DIFF_CATEGORY
    return None


def _normalize_metric_path(path: str) -> str:
    return str(path or "").strip().rstrip("-").strip()


def _path_leaf(path: str) -> str:
    normalized = _normalize_metric_path(path)
    return normalized.rsplit("-", 1)[-1].strip() if normalized else ""


def _extract_subject(raw_data: Any) -> Dict[str, Any]:
    if raw_data is None:
        raise ChapterDataError(f"第四章数据清洗失败: 原始数据为 null。{EMPTY_DATA_MESSAGE}")
    if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
        return raw_data["data"]
    if isinstance(raw_data, dict):
        return raw_data
    if isinstance(raw_data, list):
        return {"章节数据": raw_data}
    raise ChapterDataError(f"第四章数据清洗失败: 原始数据不是数组或对象。{EMPTY_DATA_MESSAGE}")


def _extract_chapter_rows(subject: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = subject.get("章节数据")
    if not isinstance(rows, list):
        raise ChapterDataError(f"第四章数据清洗失败: 章节数据缺失或不是数组。{EMPTY_DATA_MESSAGE}")
    return rows


def _validate_subject(subject: Dict[str, Any], period: str) -> None:
    chapter_name = str(subject.get("章节名称") or "")
    if chapter_name and chapter_name != CHAPTER_NAME:
        raise ChapterDataError(f"第四章校验失败: 章节名称为 {chapter_name!r}")
    source_period = str(subject.get("月份") or "")
    if period and source_period and source_period != str(period):
        raise ChapterDataError(f"第四章校验失败: 月份不是 {period}")
