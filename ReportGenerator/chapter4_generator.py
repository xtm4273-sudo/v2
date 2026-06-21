"""第四章生成器 - 毛利率与产品结构。

本模块对接 MOUDLE=4 的真实字段结构。映射只依赖完整的“指标路径”、
“指标名称”和“单位”；不依赖数组顺序、数值大小或近似名称。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple
import logging

from Data import EMPTY_DATA_MESSAGE, ChapterDataError

logger = logging.getLogger(__name__)

CHAPTER_NAME = "四、毛利率与产品结构"
PRICE_DIFF_CATEGORY = "各产品的均价差异"
SHARE_DIFF_CATEGORY = "各产品收入占比差异"
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


def format_chapter4_data(raw_data: Any, period: str = "") -> Tuple[str, Dict[str, Any]]:
    """严格清洗第四章数据并生成客户模板 Markdown。"""
    subject = _extract_subject(raw_data)
    _validate_subject(subject, period)
    rows = _extract_chapter_rows(subject)
    evidence, conflicts, warnings = collect_metric_evidence(rows)
    markdown = build_chapter4_markdown()
    stats = build_chapter4_stats(subject, evidence, conflicts, warnings, period)
    return markdown, stats


async def format_chapter4_data_async(
    raw_data: Any,
    period: str = "",
    action_guide_writer: Optional[Any] = None,
) -> Tuple[str, Dict[str, Any]]:
    """AI 不参与严格字段映射；保留异步签名以兼容现有调用。"""
    if action_guide_writer is not None:
        logger.info("第四章严格映射模式不使用 AI 补写缺失数据")
    markdown, stats = format_chapter4_data(raw_data, period=period)
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
        name = str(item.get("指标名称") or "").strip()
        path = str(item.get("指标路径") or "").strip()
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


def build_chapter4_markdown(*_args: Any, **_kwargs: Any) -> str:
    """保留 Word 章节结构，缺少可唯一映射字段时统一标红。"""
    lines = [
        "## 四、毛利率与产品结构",
        "",
        f"个人毛利率{MISSING_MARK}，主要影响因素{MISSING_MARK}。",
        "",
        "| 指标 | 详情 |",
        "| --- | --- |",
        f"| 价格变动 | **均价上升：** {MISSING_MARK}<br><br>**均价下降：** {MISSING_MARK} |",
        f"| 结构变化 | **收入占比排名前三的产品及占比变动：** {MISSING_MARK} |",
        "",
        "### 行动指南：",
        "",
        f"◇ **产品结构：** {MISSING_MARK}",
        "",
        f"◇ **价格：** {MISSING_MARK}",
    ]
    return "\n".join(lines) + "\n"


def build_chapter4_stats(
    subject: Dict[str, Any],
    evidence: List[MetricEvidence],
    conflicts: List[Dict[str, Any]],
    warnings: List[str],
    period: str = "",
) -> Dict[str, Any]:
    price = [item for item in evidence if item.category == PRICE_DIFF_CATEGORY]
    share = [item for item in evidence if item.category == SHARE_DIFF_CATEGORY]
    missing_fields = [
        "个人毛利率",
        "当前产品均价",
        "均价变动方向",
        "当前产品收入占比",
        "收入占比变动方向",
        "产品收入占比排名",
        "低毛利产品标识",
    ]
    cleaned = {
        "employee_id": str(subject.get("区域经理工号") or ""),
        "month": str(subject.get("月份") or period),
        "department_code": subject.get("部门编码", ""),
        "department_name": subject.get("部门名称", ""),
        "manager_name": subject.get("区域经理姓名", ""),
        "chapter_name": subject.get("章节名称", CHAPTER_NAME),
        "module": 4,
        "metric_evidence": [item.to_dict() for item in evidence],
        "conflicts": conflicts,
        "missing_fields": missing_fields,
        "calculations": [],
        "warnings": warnings,
    }
    return {
        "均价差异正常证据数": len(price),
        "收入占比差异正常证据数": len(share),
        "冲突数": len(conflicts),
        "缺失字段": missing_fields,
        "计算字段": [],
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
    for category in (PRICE_DIFF_CATEGORY, SHARE_DIFF_CATEGORY):
        if path == f"{CHAPTER_NAME}-{category}-{name}":
            return category
    return None


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
    if not isinstance(rows, list) or not rows:
        raise ChapterDataError(f"第四章数据清洗失败: 章节数据缺失或为空。{EMPTY_DATA_MESSAGE}")
    return rows


def _validate_subject(subject: Dict[str, Any], period: str) -> None:
    chapter_name = str(subject.get("章节名称") or "")
    if chapter_name and chapter_name != CHAPTER_NAME:
        raise ChapterDataError(f"第四章校验失败: 章节名称为 {chapter_name!r}")
    if period and str(subject.get("月份") or "") != str(period):
        raise ChapterDataError(f"第四章校验失败: 月份不是 {period}")
