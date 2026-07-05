"""第六章“费用分析”唯一生成器。

公开接口只有 ``format_chapter6_data`` 和核对清单生成函数。所有调用方均通过
这一个 seam 使用严格字段映射：不按数组顺序、数值大小或相似名称猜测。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
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
    _spec("chapter6.travel.total", "差旅费/报告月总额", "差旅费总额", f"{CHAPTER}-差旅费-差旅费总额", unit="元"),
    _spec("chapter6.travel.transport", "差旅费/交通费", "交通费", f"{CHAPTER}-差旅费-交通费", unit="元"),
    _spec("chapter6.travel.hotel", "差旅费/住宿费", "住宿费", f"{CHAPTER}-差旅费-住宿费", unit="元"),
    _spec("chapter6.travel.vehicle", "差旅费/车辆费", "车辆费", f"{CHAPTER}-差旅费-车辆费", unit="元"),
    _spec("chapter6.travel.other", "差旅费/其他费用", "其他费用", f"{CHAPTER}-差旅费-其他费用", unit="元"),
    _spec("chapter6.efficiency.days", "出差效率/出差天数", "出差天数", f"{CHAPTER}-差旅费-出差天数", unit="天"),
    _spec("chapter6.efficiency.transport", "出差效率/日均交通费", "交通费/天", f"{CHAPTER}-差旅费-每天花费金额-交通费/天", unit="元"),
    _spec("chapter6.efficiency.hotel", "出差效率/日均住宿费", "住宿费/天", f"{CHAPTER}-差旅费-每天花费金额-住宿费/天", unit="元"),
    _spec("chapter6.efficiency.vehicle", "出差效率/日均车辆费", "车辆费/天", f"{CHAPTER}-差旅费-每天花费金额-车辆费/天", unit="元"),
    _spec("chapter6.efficiency.other", "出差效率/日均其他费用", "其他费用/天", f"{CHAPTER}-差旅费-每天花费金额-其他费用/天", unit="元"),
    _spec("chapter6.sample.total", "样板样漆费用/报告月总额", "样板样漆费用", f"{CHAPTER}-样板样漆费用-样板样漆费用", unit="元"),
)


def format_chapter6_data(raw_data: Any, period: str = "", context_raw_data: Any = None) -> Tuple[str, Dict[str, Any]]:
    """严格清洗 MODULE=6 响应并生成第六章 Markdown。"""
    subject = _subject(raw_data)
    rows = subject.get("章节数据")
    if not isinstance(rows, list) or not rows:
        raise ChapterDataError("第六章字段映射失败：章节数据为空。")

    values: Dict[str, Optional[Dict[str, Any]]] = {}
    sources: Dict[str, Dict[str, Any]] = {}
    for spec in CHAPTER6_FIELD_MAP:
        values[spec.field_id], sources[spec.field_id] = _select_unique(rows, spec)
    _add_computed_values(values, sources)
    products, product_source = _select_monthly_sample_products(rows)
    sources["chapter6.sample.top_products"] = product_source
    action_items, action_sources = _build_action_guide(values, products, context_raw_data)
    sources.update(action_sources)

    metadata = {
        key: subject.get(key, "")
        for key in ("月份", "部门编码", "区域经理工号", "部门名称", "区域经理姓名", "岗位名称", "章节名称")
    }
    metadata["月份"] = metadata["月份"] or period
    cleaned = _build_cleaned_data(metadata, values, sources, products)
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
        "样板样漆产品数": len(products),
        "行动指南": action_items,
    }
    return _build_markdown(values, products, period or metadata["月份"], action_items), stats


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
        match = source.get("match", {})
        search_items = []
        if match.get("指标名称"):
            search_items.append(f'`"指标名称": "{match["指标名称"]}"`')
        if match.get("指标路径"):
            search_items.append(f'`"指标路径": "{match["指标路径"]}"`')
        if match.get("指标路径前缀"):
            search_items.append(f'`"指标路径"前缀: "{match["指标路径前缀"]}"`')
        if match.get("来源"):
            search_items.append(match["来源"])
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
        "接口已提供具名的月度差旅费、出差天数、日均分类费用、样板样漆总额和产品明细；同比及平均每天花费按已确认公式计算。",
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
        if not isinstance(row, dict):
            continue
        path = _normalize_metric_path(str(row.get("指标路径") or ""))
        name = str(row.get("指标名称") or "").strip()
        if path != spec.path:
            continue
        if name and name != spec.name:
            continue
        if not name and _path_leaf(path) != spec.name:
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


def _select_unique(rows: List[Dict[str, Any]], spec: FieldSpec) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    matched = _matching(rows, spec)
    named_matched = [
        row for row in matched
        if str(row.get("指标名称") or "").strip() == spec.name
    ]
    if named_matched:
        matched = named_matched
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
    matched_row = matched[valid.index(value)]
    metric = matched_row.get("指标数据") if isinstance(matched_row.get("指标数据"), dict) else {}
    same_period = _to_decimal(metric.get("同期数"))
    report_value = _format_number(value, spec.unit)
    source.update(status="正常" if len(matched) == 1 else "重复但值一致", report_value=report_value)
    source["same_period"] = str(metric.get("同期数", ""))
    return {
        "raw_value": value,
        "value": _to_decimal(value),
        "same_period": same_period,
        "unit": spec.unit,
        "report_value": report_value,
    }, source


def _select_monthly_sample_products(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    prefix = f"{CHAPTER}-样板样漆费用-样板样漆费用-"
    products = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("指标名称") or "").strip()
        path = _normalize_metric_path(str(row.get("指标路径") or ""))
        metric = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
        if not path.startswith(prefix) or str(metric.get("日期类型") or "") != "月":
            continue
        name = name or path[len(prefix):].strip()
        if not name:
            continue
        value = _to_decimal(metric.get("实际值"))
        if value is None:
            continue
        products.append({
            "name": name,
            "value": value,
            "same_period": _to_decimal(metric.get("同期数")),
            "unit": str(metric.get("单位") or "元"),
            "source_path": path,
        })
    products.sort(key=lambda item: item["value"], reverse=True)
    source = {
        "field_id": "chapter6.sample.top_products",
        "report_position": "样板样漆费用/费用排名前三产品",
        "match": {"指标路径前缀": prefix, "指标数据.日期类型": "月"},
        "value_path": "指标数据.实际值",
        "unit_path": "指标数据.单位",
        "calculation": "按接口产品名称分组后，以报告月实际值降序取前三",
        "matched_count": len(products),
        "raw_values": [f'{item["name"]}:{item["value"]}{item["unit"]}' for item in products],
        "report_value": "、".join(f'{item["name"]}{_format_decimal(item["value"])}{item["unit"]}' for item in products[:3]) or PENDING,
        "status": "正常" if len(products) >= 3 else "产品不足3项",
    }
    return products[:3], source


def _normalize_metric_path(path: str) -> str:
    return path.strip().rstrip("-").strip()


def _path_leaf(path: str) -> str:
    return _normalize_metric_path(path).split("-")[-1].strip() if path else ""


def _add_computed_values(values: Dict[str, Optional[Dict[str, Any]]], sources: Dict[str, Dict[str, Any]]) -> None:
    def add(
        field_id: str,
        report_position: str,
        value: Optional[Decimal],
        unit: str,
        calculation: str,
        report_value: Optional[str] = None,
        status: Optional[str] = None,
    ):
        display = report_value or (_format_decimal(value) + unit if value is not None else PENDING)
        values[field_id] = None if value is None and report_value is None else {
            "raw_value": str(value), "value": value, "unit": unit, "report_value": display,
        }
        sources[field_id] = {
            "field_id": field_id,
            "report_position": report_position,
            "match": {"来源": "已映射接口字段"},
            "value_path": "程序计算",
            "unit_path": "程序指定",
            "calculation": calculation,
            "matched_count": 1 if value is not None else 0,
            "raw_values": [str(value)] if value is not None else [],
            "report_value": display,
            "status": status or ("正常" if value is not None else "计算条件缺失"),
        }

    total = values.get("chapter6.travel.total")
    if total:
        rate, note = _growth_rate(total.get("value"), total.get("same_period"))
        rate_text = _format_percent(rate) + ("（同期数为0）" if note else "") if rate is not None else PENDING
        add("chapter6.travel.yoy_rate", "差旅费/同比增长率", rate, "%", "按实际值与同期数计算；同期数为0时增长率按100%展示", rate_text)

    for key, label in (("transport", "交通费"), ("hotel", "住宿费"), ("vehicle", "车辆费"), ("other", "其他费用")):
        item = values.get(f"chapter6.travel.{key}")
        delta = item.get("value") - item.get("same_period") if item and item.get("value") is not None and item.get("same_period") is not None else None
        add(f"chapter6.travel.{key}_delta", f"差旅费/{label}同比差额", delta, "元", "接口实际值-接口同期数")

    days = values.get("chapter6.efficiency.days")
    daily = None
    daily_display = None
    daily_status = None
    if total and days and total.get("value") is not None and days.get("value") not in (None, Decimal("0")):
        daily = total["value"] / days["value"]
    elif total and days and days.get("value") == Decimal("0"):
        daily_display = "不适用（出差天数为0）"
        daily_status = "不适用"
    add(
        "chapter6.efficiency.daily_total",
        "出差效率/平均每天花费",
        daily,
        "元",
        "差旅费总额/出差天数；出差天数为0时不计算日均值",
        daily_display,
        daily_status,
    )

    sample = values.get("chapter6.sample.total")
    sample_delta = None
    sample_rate = None
    if sample and sample.get("value") is not None and sample.get("same_period") is not None:
        sample_delta = sample["value"] - sample["same_period"]
        sample_rate, _ = _growth_rate(sample["value"], sample["same_period"])
    add("chapter6.sample.yoy_delta", "样板样漆费用/同比差额", sample_delta, "元", "接口实际值-接口同期数")
    add("chapter6.sample.yoy_rate", "样板样漆费用/同比增长率", sample_rate, "%", "按接口实际值与同期数计算", _format_percent(sample_rate) if sample_rate is not None else None)


def _build_action_guide(
    values: Dict[str, Optional[Dict[str, Any]]],
    products: List[Dict[str, Any]],
    context_raw_data: Any,
) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    rows = list(_iter_context_rows(context_raw_data))
    items: List[str] = []
    sources: Dict[str, Dict[str, Any]] = {}

    travel_total = values.get("chapter6.travel.total")
    travel_increased = _actual_gt_same(travel_total)
    sales_row = _find_context_metric(rows, module=3, name="销量", path="三、销量分析-销量", date_type="月")
    sales_down = _metric_actual_lt_same(sales_row)
    overdue_row = _find_context_metric(rows, module=5, name="个人本月新增到期款", path="五、应收分析-个人本月新增到期款")
    overdue_increased = _metric_actual_gt_same(overdue_row) or _metric_actual_positive(overdue_row)
    if travel_increased and sales_down and overdue_increased:
        items.append("本月差旅费增长、但收入下滑且本月新增逾期，需警惕出差效率与出差质量。")
    sources["chapter6.action.travel"] = _action_source(
        "行动指南/差旅费效率与质量",
        {
            "差旅费增长": travel_increased,
            "收入下滑": sales_down,
            "本月新增逾期增加": overdue_increased,
        },
        [travel_total, sales_row, overdue_row],
        "差旅费增长 且 收入下滑 且 本月新增逾期增加时输出固定建议",
        items[-1] if items and items[-1].startswith("本月差旅费") else PENDING,
    )

    sample_total = values.get("chapter6.sample.total")
    sample_increased = _actual_gt_same(sample_total)
    matched_down_products = _sample_products_with_sales_down(rows, products)
    if sample_increased and matched_down_products:
        product_text = "、".join(matched_down_products[:3])
        items.append(f"样板样漆费用增加但{product_text}等对应产品收入下滑，需关注样板样漆费用投入产出效率。")
    sources["chapter6.action.sample"] = _action_source(
        "行动指南/样板样漆费用控制",
        {
            "样板样漆费用增加": sample_increased,
            "对应产品收入下滑": bool(matched_down_products),
        },
        [sample_total],
        "样板样漆费用增加 且 费用前三产品存在对应销售额下滑时输出固定建议",
        items[-1] if items and items[-1].startswith("样板样漆") else PENDING,
    )
    return items, sources


def _iter_context_rows(context_raw_data: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(context_raw_data, dict):
        return
    iterable = context_raw_data.items() if all(isinstance(k, int) for k in context_raw_data.keys()) else [(None, context_raw_data)]
    for module, response in iterable:
        data = response.get("data") if isinstance(response, dict) else None
        rows = data.get("章节数据") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                copied = dict(row)
                if module is not None:
                    copied["module"] = module
                yield copied


def _find_context_metric(
    rows: Iterable[Dict[str, Any]],
    *,
    module: Optional[int] = None,
    name: str = "",
    path: str = "",
    date_type: str = "",
) -> Optional[Dict[str, Any]]:
    for row in rows:
        if module is not None and row.get("module") != module:
            continue
        if name and row.get("指标名称") != name:
            continue
        if path and row.get("指标路径") != path:
            continue
        metric = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
        if date_type and str(metric.get("日期类型") or "") != date_type:
            continue
        return row
    return None


def _sample_products_with_sales_down(rows: List[Dict[str, Any]], products: List[Dict[str, Any]]) -> List[str]:
    down: List[str] = []
    for product in products:
        name = product["name"]
        row = _find_context_metric(
            rows,
            module=3,
            name=name,
            path=f"三、销量分析-各产品销量-{name}",
            date_type="年",
        )
        if _metric_actual_lt_same(row):
            down.append(name)
    return down


def _metric_values(row: Optional[Dict[str, Any]]) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    if row is None:
        return None, None
    metric = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
    return _to_decimal(metric.get("实际值")), _to_decimal(metric.get("同期数"))


def _actual_gt_same(item: Optional[Dict[str, Any]]) -> bool:
    if not item:
        return False
    actual, same = item.get("value"), item.get("same_period")
    return actual is not None and same is not None and actual > same


def _metric_actual_gt_same(row: Optional[Dict[str, Any]]) -> bool:
    actual, same = _metric_values(row)
    return actual is not None and same is not None and actual > same


def _metric_actual_lt_same(row: Optional[Dict[str, Any]]) -> bool:
    actual, same = _metric_values(row)
    return actual is not None and same is not None and actual < same


def _metric_actual_positive(row: Optional[Dict[str, Any]]) -> bool:
    actual, _ = _metric_values(row)
    return actual is not None and actual > 0


def _action_source(
    report_position: str,
    conditions: Dict[str, bool],
    source_items: List[Optional[Dict[str, Any]]],
    calculation: str,
    report_value: str,
) -> Dict[str, Any]:
    raw_values = []
    for item in source_items:
        if not item:
            continue
        if "report_value" in item:
            raw_values.append(item["report_value"])
            continue
        metric = item.get("指标数据") if isinstance(item.get("指标数据"), dict) else {}
        raw_values.append(f'{item.get("指标名称", "")}:实际值{metric.get("实际值", "")},同期数{metric.get("同期数", "")}')
    return {
        "field_id": report_position,
        "report_position": report_position,
        "match": {"来源": "跨章节规则判断"},
        "value_path": "程序计算",
        "unit_path": "无",
        "calculation": calculation,
        "matched_count": len(raw_values),
        "raw_values": raw_values,
        "conditions": conditions,
        "report_value": report_value,
        "status": "正常" if report_value != PENDING else "未触发",
    }


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _growth_rate(actual: Optional[Decimal], same_period: Optional[Decimal]) -> Tuple[Optional[Decimal], bool]:
    if actual is None or same_period is None:
        return None, False
    if same_period == 0:
        if actual == 0:
            return Decimal("0"), False
        return Decimal("100"), True
    if same_period < 0:
        return (actual - same_period) / abs(same_period) * 100, False
    return (actual / same_period - 1) * 100, False


def _format_decimal(value: Optional[Decimal], precision: int = 0) -> str:
    if value is None:
        return ""
    quantum = Decimal("1") if precision == 0 else Decimal("1").scaleb(-precision)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{rounded:.{precision}f}"


def _format_number(value: Any, unit: str) -> str:
    decimal_value = _to_decimal(value)
    return f"{_format_decimal(decimal_value)}{unit}" if decimal_value is not None else PENDING


def _format_percent(value: Optional[Decimal]) -> str:
    if value is None:
        return PENDING
    if value == value.to_integral_value():
        return f"{_format_decimal(value)}%"
    return f"{_format_decimal(value, 1)}%"


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


def _raw_value(values: Dict[str, Optional[Dict[str, Any]]], field_id: str) -> Optional[str]:
    item = values.get(field_id)
    return item["raw_value"] if item else None


def _display(values: Dict[str, Optional[Dict[str, Any]]], field_id: str) -> str:
    item = values.get(field_id)
    return item["report_value"] if item else PENDING


def _display_yoy_delta(values: Dict[str, Optional[Dict[str, Any]]], field_id: str) -> str:
    item = values.get(field_id)
    if not item or item.get("value") is None:
        return PENDING
    value = item["value"]
    if value == 0:
        return "持平"
    direction = "增加" if value > 0 else "减少"
    unit = item.get("unit") or ""
    return f"{direction}{_format_decimal(abs(value))}{unit}"


def _display_yoy_rate_direction(values: Dict[str, Optional[Dict[str, Any]]], field_id: str) -> str:
    item = values.get(field_id)
    if not item or item.get("value") is None:
        return PENDING
    value = item["value"]
    if value == 0:
        return "持平"
    if value > 0:
        return f"增长{item.get('report_value') or _format_percent(value)}"
    return f"下降{_format_percent(abs(value))}"


def _month(period: Any) -> str:
    text = str(period or "")
    return str(int(text[-2:])) if len(text) >= 6 and text[-2:].isdigit() else PENDING


def _is_zero_actual_and_same_period(item: Optional[Dict[str, Any]]) -> bool:
    return bool(
        item
        and item.get("value") == Decimal("0")
        and item.get("same_period") == Decimal("0")
    )


def _is_zero_value(item: Optional[Dict[str, Any]]) -> bool:
    return bool(item and item.get("value") == Decimal("0"))


def _build_cleaned_data(
    metadata: Dict[str, Any],
    values: Dict[str, Optional[Dict[str, Any]]],
    sources: Dict[str, Dict[str, Any]],
    products: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """提供严格审计数据，并保留完整报告下游所需的稳定视图。"""
    return {
        "metadata": metadata,
        "values": _json_safe(values),
        "field_sources": _json_safe(sources),
        "travel_expense": {
            "total": {"value": _raw_value(values, "chapter6.travel.total"), "unit": "元"},
            "efficiency": {"days": _raw_value(values, "chapter6.efficiency.days")},
        },
        "sample_paint_expense": {
            "total": {
                "value": _raw_value(values, "chapter6.sample.total"),
                "same_period": _raw_same_period(values, "chapter6.sample.total"),
                "yoy_value": _raw_same_period(values, "chapter6.sample.total"),
                "unit": "元",
            },
            "by_product": [
                {"name": item["name"], "value": str(item["value"]), "same_period": str(item["same_period"] or 0), "unit": item["unit"]}
                for item in products
            ],
        },
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _raw_same_period(values: Dict[str, Optional[Dict[str, Any]]], field_id: str) -> Optional[str]:
    item = values.get(field_id)
    if not item or item.get("same_period") is None:
        return None
    return str(item["same_period"])


def _build_markdown(
    values: Dict[str, Optional[Dict[str, Any]]],
    products: List[Dict[str, Any]],
    period: Any,
    action_items: Optional[List[str]] = None,
) -> str:
    d = lambda field_id: _display(values, field_id)
    yd = lambda field_id: _display_yoy_delta(values, field_id)
    yr = lambda field_id: _display_yoy_rate_direction(values, field_id)
    month = _month(period)
    product_text = "、".join(
        f'{item["name"]}{_format_decimal(item["value"])}{item["unit"]}' for item in products
    )
    action_text = "\n\n".join(action_items or ["本月费用未触发重点预警，持续跟踪差旅投入、样板样漆费用与销售转化。"])
    travel_total = values.get("chapter6.travel.total")
    travel_summary = f"{month}月差旅费{d('chapter6.travel.total')}，同比{yr('chapter6.travel.yoy_rate')}。"
    if not _is_zero_actual_and_same_period(travel_total):
        travel_summary += (
            f"其中交通费同比{yd('chapter6.travel.transport_delta')}、"
            f"住宿费同比{yd('chapter6.travel.hotel_delta')}、"
            f"车辆费同比{yd('chapter6.travel.vehicle_delta')}、"
            f"其他同比{yd('chapter6.travel.other_delta')}。"
        )

    travel_days = values.get("chapter6.efficiency.days")
    travel_efficiency = f"出差效率：{month}月出差天数{d('chapter6.efficiency.days')}。"
    if not _is_zero_value(travel_days):
        travel_efficiency = (
            f"出差效率：{month}月出差天数{d('chapter6.efficiency.days')}，"
            f"平均每天花费{d('chapter6.efficiency.daily_total')}，"
            f"其中交通费{d('chapter6.efficiency.transport')}/天、"
            f"住宿费{d('chapter6.efficiency.hotel')}/天、"
            f"车辆费{d('chapter6.efficiency.vehicle')}/天、"
            f"其他{d('chapter6.efficiency.other')}/天。"
        )
    travel_days_note = (
        f"（备注：{month}月出差天数是按差旅报销流程申请日期，"
        "例：张三5月报销了实际3-4月的出差，出差天数就是两个月的合计出差天数）"
    )
    sample_summary = f"{month}月费用{d('chapter6.sample.total')}，同比{yd('chapter6.sample.yoy_delta')}。"
    if product_text:
        sample_summary += f"其中费用排名前三的产品为{product_text}。"
    return "\n".join([
        "# 六、费用分析", "", "## 6.1 差旅费", "",
        travel_summary, "",
        travel_efficiency, "",
        travel_days_note, "",
        "## 6.2 样板样漆费用", "",
        sample_summary, "",
        "## 6.3 行动指南", "",
        action_text,
    ]) + "\n"
