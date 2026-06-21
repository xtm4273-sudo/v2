"""第六章“费用分析”唯一生成器。

公开接口只有 ``format_chapter6_data`` 和核对清单生成函数。所有调用方均通过
这一个 seam 使用严格字段映射：不按数组顺序、数值大小或相似名称猜测。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from Data import ChapterDataError


PENDING = '<span style="color:#c00000;font-weight:700">待补充</span>'
CHAPTER = "六、费用分析"


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    report_position: str
    name: str
    path: str
    value_path: str = "指标数据.实际值"
    unit: str = ""
    date_type: str = "月"
    calculation: str = "无，直接取接口原始值并保持原始精度"


def _spec(field_id: str, position: str, name: str, path: str, **kwargs: str) -> FieldSpec:
    return FieldSpec(field_id, position, name, path, **kwargs)


CHAPTER6_FIELD_MAP: Tuple[FieldSpec, ...] = (
    _spec("chapter6.travel.total", "差旅费/报告月总额", "差旅费", f"{CHAPTER}-差旅费", unit="元"),
    _spec(
        "chapter6.travel.yoy_rate", "差旅费/同比增长率", "差旅费", f"{CHAPTER}-差旅费",
        value_path="指标数据.同比增长率", unit="元",
        calculation="不计算；接口无同比增长率字段，不根据实际值与同期数计算",
    ),
    _spec("chapter6.travel.transport_delta", "差旅费/交通费同比差额", "交通费", f"{CHAPTER}-差旅费-交通费", value_path="指标数据.同比差额", calculation="不计算；接口无具名记录和同比差额字段"),
    _spec("chapter6.travel.hotel_delta", "差旅费/住宿费同比差额", "住宿费", f"{CHAPTER}-差旅费-住宿费", value_path="指标数据.同比差额", calculation="不计算；接口无具名记录和同比差额字段"),
    _spec("chapter6.travel.vehicle_delta", "差旅费/车辆费同比差额", "车辆费", f"{CHAPTER}-差旅费-车辆费", value_path="指标数据.同比差额", calculation="不计算；接口无具名记录和同比差额字段"),
    _spec("chapter6.travel.other_delta", "差旅费/其他同比差额", "其他", f"{CHAPTER}-差旅费-其他", value_path="指标数据.同比差额", calculation="不计算；接口无具名记录和同比差额字段"),
    # 实时接口把出差天数编码为“差旅费”记录；月口径 + 天单位在响应中唯一。
    _spec("chapter6.efficiency.days", "出差效率/出差天数", "差旅费", f"{CHAPTER}-差旅费", unit="天"),
    _spec("chapter6.efficiency.daily_total", "出差效率/平均每天花费", "每天花费金额", f"{CHAPTER}-差旅费-每天花费金额", unit="元"),
    _spec("chapter6.efficiency.transport", "出差效率/日均交通费", "交通费", f"{CHAPTER}-差旅费-每天花费金额-交通费", unit="元"),
    _spec("chapter6.efficiency.hotel", "出差效率/日均住宿费", "住宿费", f"{CHAPTER}-差旅费-每天花费金额-住宿费", unit="元"),
    _spec("chapter6.efficiency.vehicle", "出差效率/日均车辆费", "车辆费", f"{CHAPTER}-差旅费-每天花费金额-车辆费", unit="元"),
    _spec("chapter6.efficiency.other", "出差效率/日均其他费用", "其他", f"{CHAPTER}-差旅费-每天花费金额-其他", unit="元"),
    _spec("chapter6.sample.total", "样板样漆费用/报告月总额", "样板样漆费用", f"{CHAPTER}-样板样漆费用", unit="元"),
    _spec(
        "chapter6.sample.yoy_delta", "样板样漆费用/同比差额", "样板样漆费用", f"{CHAPTER}-样板样漆费用",
        value_path="指标数据.同比差额", unit="元",
        calculation="不计算；接口无同比差额字段，不以扣分值代替",
    ),
)

PRODUCT_SPECS: Tuple[Tuple[str, str], ...] = (
    ("chapter6.sample.product1", "样板样漆费用/产品1及费用"),
    ("chapter6.sample.product2", "样板样漆费用/产品2及费用"),
    ("chapter6.sample.product3", "样板样漆费用/产品3及费用"),
)


def format_chapter6_data(raw_data: Any, period: str = "") -> Tuple[str, Dict[str, Any]]:
    """严格清洗 MODULE=6 响应并生成第六章 Markdown。"""
    subject = _subject(raw_data)
    rows = subject.get("章节数据")
    if not isinstance(rows, list) or not rows:
        raise ChapterDataError("第六章字段映射失败：章节数据为空。")

    values: Dict[str, Optional[Dict[str, str]]] = {}
    sources: Dict[str, Dict[str, Any]] = {}
    for spec in CHAPTER6_FIELD_MAP:
        values[spec.field_id], sources[spec.field_id] = _select_unique(rows, spec)
    for field_id, position in PRODUCT_SPECS:
        sources[field_id] = _audit_products(rows, field_id, position)
        values[field_id] = None

    metadata = {
        key: subject.get(key, "")
        for key in ("月份", "部门编码", "区域经理工号", "部门名称", "区域经理姓名", "岗位名称", "章节名称")
    }
    metadata["月份"] = metadata["月份"] or period
    cleaned = _build_cleaned_data(metadata, values, sources)
    warnings = [
        f'{source["report_position"]}：{source["status"]}'
        for source in sources.values()
        if source["status"] not in {"正常", "重复但值一致"}
    ]
    stats = {
        "cleaned_data": cleaned,
        "field_sources": sources,
        "warnings": warnings,
        "差旅费总额": _raw_value(values, "chapter6.travel.total"),
        "出差天数": _raw_value(values, "chapter6.efficiency.days"),
        "样板样漆总额": _raw_value(values, "chapter6.sample.total"),
        "样板样漆产品数": 0,
    }
    return _build_markdown(values, metadata["月份"]), stats


def build_chapter6_apipost_checklist(stats: Dict[str, Any]) -> str:
    metadata = stats["cleaned_data"]["metadata"]
    lines = [
        "# 第六章 ApiPost 取数核对清单", "",
        f'接口参数：`MOUDLE=6`，`ZEMPLOYEE={metadata.get("区域经理工号", "")}`，`CALMONTH={metadata.get("月份", "")}`。', "",
        "复制“ApiPost搜索内容”中的完整键值对到响应 JSON 搜索；实际定位同时使用表内列出的全部条件。", "",
        "| 报告位置 | ApiPost搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for source in stats["field_sources"].values():
        search_items = [
            f'`"指标名称": "{source["match"]["指标名称"]}"`',
            f'`"指标路径": "{source["match"]["指标路径"]}"`',
        ]
        if source["match"].get("指标数据.单位"):
            search_items.append(f'`"单位": "{source["match"]["指标数据.单位"]}"`')
        if source["match"].get("指标数据.日期类型"):
            search_items.append(f'`"日期类型": "{source["match"]["指标数据.日期类型"]}"`')
        raw = "；".join(source.get("raw_values", [])) or "搜索不到"
        lines.append("| " + " | ".join([
            source["report_position"], "<br>".join(search_items), f'`{source["value_path"]}`',
            raw, source.get("report_value", PENDING), source["calculation"], source["status"],
        ]) + " |")
    lines.extend([
        "", "## 核对结论", "",
        "接口可唯一定位月度出差天数和样板样漆费用总额。其余差旅费、每天花费金额和样板样漆产品明细存在同名同路径冲突或缺少业务标识；未按数组顺序、数值大小或相似名称归类，也未自行计算同比。",
    ])
    return "\n".join(lines) + "\n"


def _subject(raw_data: Any) -> Dict[str, Any]:
    if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
        return raw_data["data"]
    if isinstance(raw_data, dict):
        return raw_data
    raise ChapterDataError("第六章字段映射失败：原始数据不是对象。")


def _matching(rows: Iterable[Any], spec: FieldSpec) -> List[Dict[str, Any]]:
    matched = []
    for row in rows:
        if not isinstance(row, dict) or row.get("指标名称") != spec.name or row.get("指标路径") != spec.path:
            continue
        data = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
        if spec.unit and str(data.get("单位") or "") != spec.unit:
            continue
        if spec.date_type and str(data.get("日期类型") or "") != spec.date_type:
            continue
        matched.append(row)
    return matched


def _nested_value(row: Dict[str, Any], value_path: str) -> Optional[str]:
    current: Any = row
    for part in value_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if current is None or str(current).strip() == "":
        return None
    return str(current).strip()


def _select_unique(rows: List[Dict[str, Any]], spec: FieldSpec) -> Tuple[Optional[Dict[str, str]], Dict[str, Any]]:
    matched = _matching(rows, spec)
    raw_values = [_nested_value(row, spec.value_path) for row in matched]
    valid = [value for value in raw_values if value is not None]
    source = _source_base(spec)
    source["matched_count"] = len(matched)
    source["raw_values"] = [
        f"{value}{spec.unit}" if value is not None and spec.unit and spec.value_path == "指标数据.实际值" else (value or "字段不存在/null")
        for value in raw_values
    ]
    if not matched:
        source.update(status="缺失", report_value=PENDING)
        return None, source
    if not valid:
        source.update(status="取值字段缺失", report_value=PENDING)
        return None, source
    if len(set(valid)) != 1:
        source.update(status="重复冲突", report_value=PENDING)
        return None, source
    value = valid[0]
    report_value = f"{value}{spec.unit}" if spec.unit else value
    source.update(status="正常" if len(matched) == 1 else "重复但值一致", report_value=report_value)
    return {"raw_value": value, "unit": spec.unit, "report_value": report_value}, source


def _audit_products(rows: List[Dict[str, Any]], field_id: str, position: str) -> Dict[str, Any]:
    spec = FieldSpec(
        field_id, position, "样板样漆费用", f"{CHAPTER}-样板样漆费用-样板样漆费用",
        unit="元", calculation="不计算；缺少产品名称/编码，禁止按数组顺序或金额大小选取产品",
    )
    matched = _matching(rows, spec)
    source = _source_base(spec)
    source["matched_count"] = len(matched)
    source["raw_values"] = [f'{_nested_value(row, "指标数据.实际值")}元' for row in matched]
    source["report_value"] = PENDING
    source["status"] = "重复冲突且缺产品唯一标识" if matched else "缺失"
    return source


def _source_base(spec: FieldSpec) -> Dict[str, Any]:
    match = {"指标名称": spec.name, "指标路径": spec.path}
    if spec.unit:
        match["指标数据.单位"] = spec.unit
    if spec.date_type:
        match["指标数据.日期类型"] = spec.date_type
    return {
        "field_id": spec.field_id, "report_position": spec.report_position, "match": match,
        "value_path": spec.value_path, "unit_path": "指标数据.单位", "calculation": spec.calculation,
    }


def _raw_value(values: Dict[str, Optional[Dict[str, str]]], field_id: str) -> Optional[str]:
    item = values.get(field_id)
    return item["raw_value"] if item else None


def _display(values: Dict[str, Optional[Dict[str, str]]], field_id: str) -> str:
    item = values.get(field_id)
    return item["report_value"] if item else PENDING


def _month(period: Any) -> str:
    text = str(period or "")
    return str(int(text[-2:])) if len(text) >= 6 and text[-2:].isdigit() else PENDING


def _build_cleaned_data(metadata: Dict[str, Any], values: Dict[str, Optional[Dict[str, str]]], sources: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """提供严格审计数据，并保留完整报告下游所需的稳定视图。"""
    return {
        "metadata": metadata,
        "values": values,
        "field_sources": sources,
        "travel_expense": {
            "total": {"value": _raw_value(values, "chapter6.travel.total"), "unit": "元"},
            "efficiency": {"days": _raw_value(values, "chapter6.efficiency.days")},
        },
        "sample_paint_expense": {
            "total": {"value": _raw_value(values, "chapter6.sample.total"), "unit": "元"},
            "by_product": [],
        },
    }


def _build_markdown(values: Dict[str, Optional[Dict[str, str]]], period: Any) -> str:
    d = lambda field_id: _display(values, field_id)
    month = _month(period)
    return "\n".join([
        "# 六、费用分析", "", "## 差旅费", "",
        f"{month}月差旅费{d('chapter6.travel.total')}，同比{d('chapter6.travel.yoy_rate')}。其中交通费同比差额{d('chapter6.travel.transport_delta')}、住宿费同比差额{d('chapter6.travel.hotel_delta')}、车辆费同比差额{d('chapter6.travel.vehicle_delta')}、其他同比差额{d('chapter6.travel.other_delta')}。", "",
        f"出差效率：{month}月出差天数{d('chapter6.efficiency.days')}，平均每天花费{d('chapter6.efficiency.daily_total')}，其中交通费{d('chapter6.efficiency.transport')}、住宿费{d('chapter6.efficiency.hotel')}、车辆费{d('chapter6.efficiency.vehicle')}、其他{d('chapter6.efficiency.other')}。", "",
        "## 样板样漆费用", "",
        f"{month}月费用{d('chapter6.sample.total')}，同比差额{d('chapter6.sample.yoy_delta')}。其中产品1及费用{PENDING}、产品2及费用{PENDING}、产品3及费用{PENDING}。", "",
        "## 行动指南", "",
        PENDING, "",
        "固定模板规则：若本月差旅费增长且收入下滑，或本月差旅费增长且本月新增逾期增加，可建议警惕出差效率与出差质量。", "",
        "固定模板规则：样板样漆费用增加但对应产品收入下滑的，需要提示样板样漆费用的控制。",
    ]) + "\n"
