"""第五章严格字段映射。

仅使用 ``指标名称 + 指标路径`` 定位真实 MODULE=5 指标。重复记录既不按数组
顺序拼组，也不按数值大小或近似名称推断；无法唯一定位时统一标红待补充。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

from Data import ChapterDataError


PENDING = '<span style="color:#c00000">待补充</span>'
CHAPTER = "五、应收分析"


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    report_position: str
    name: str
    path: str
    calculation: str = "无，直接取值"


def _spec(field_id: str, position: str, name: str, path: str, calculation: str = "无，直接取值") -> FieldSpec:
    return FieldSpec(field_id, position, name, path, calculation)


CHAPTER5_FIELD_MAP: Tuple[FieldSpec, ...] = (
    _spec("chapter5.receivable.total", "5.1/应收款项总额", "应收款项", f"{CHAPTER}-应收款项"),
    _spec("chapter5.receivable.notes", "5.1/结构/应收票据", "应收票据", f"{CHAPTER}-应收票据"),
    _spec("chapter5.receivable.deposit", "5.1/结构/保证金", "保证金", f"{CHAPTER}-保证金"),
    _spec("chapter5.receivable.supply_chain", "5.1/结构/供应链票证", "供应链票证", f"{CHAPTER}-供应链票证"),
    _spec("chapter5.receivable.accounts", "5.1/结构/应收账款", "应收账款", f"{CHAPTER}-应收账款"),
    _spec("chapter5.receivable.distribution", "5.1/结构/经销", "经销", f"{CHAPTER}-应收账款-经销"),
    _spec("chapter5.receivable.distribution_overdue", "5.1/结构/经销逾期", "逾期（含诉讼）", f"{CHAPTER}-应收账款-经销-逾期（含诉讼）"),
    _spec("chapter5.receivable.direct", "5.1/结构/直销", "直销", f"{CHAPTER}-应收账款-直销"),
    _spec("chapter5.receivable.risk_direct", "5.1/结构/暴雷直销应收", "暴雷直销应收", f"{CHAPTER}-应收账款-直销-暴雷直销应收"),
    _spec("chapter5.receivable.risk_direct_overdue", "5.1/结构/暴雷直销逾期", "逾期", f"{CHAPTER}-应收账款-直销-暴雷直销应收-逾期"),
    _spec("chapter5.receivable.normal_direct", "5.1/结构/非暴雷直销应收", "非暴雷直销应收", f"{CHAPTER}-应收账款-直销-非暴雷直销应收"),
    _spec("chapter5.receivable.normal_direct_overdue", "5.1/结构/非暴雷直销逾期", "逾期", f"{CHAPTER}-应收账款-直销-非暴雷直销应收-逾期"),
    _spec("chapter5.due.total", "5.1/次月新增到期款总额", "个人本月新增到期款", f"{CHAPTER}-个人本月新增到期款"),
    _spec("chapter5.impairment.total", "5.2/当年增加减值损失", "当年增加减值损失", f"{CHAPTER}-当年增加减值损失"),
    _spec("chapter5.impairment.receivable", "5.2/应收减值", "应收减值（含坏账）", f"{CHAPTER}-当年增加减值损失-应收减值（含坏账）"),
    _spec("chapter5.impairment.offset_house", "5.2/工抵房减值", "工抵房减值", f"{CHAPTER}-当年增加减值损失-工抵房减值"),
    _spec("chapter5.impairment.other", "5.2/其他类型减值", "其他类型减值", f"{CHAPTER}-当年增加减值损失-其他类型减值"),
    _spec("chapter5.impairment.aging_change", "5.2/账龄变动增加减值", "账龄变动增加减值", f"{CHAPTER}-当年增加减值损失-账龄变动增加减值"),
    _spec("chapter5.impairment.scale_change", "5.2/规模变动增加减值", "规模变动增加减值", f"{CHAPTER}-当年增加减值损失-规模变动增加减值"),
    _spec("chapter5.impairment.litigation_change", "5.2/诉讼变动增加减值", "诉讼变动增加减值", f"{CHAPTER}-当年增加减值损失-诉讼变动增加减值"),
    _spec("chapter5.finance.expense", "5.3/财务费用", "本月财务费用", f"{CHAPTER}-本月财务费用", "指标数据.实际值（万元）×10000，转换为元"),
    _spec("chapter5.finance.interest_expense", "5.3/利息支出", "利息支出", f"{CHAPTER}-本月财务费用-利息支出", "指标数据.实际值（万元）×10000，转换为元"),
    _spec("chapter5.finance.interest_income", "5.3/利息收入", "利息收入", f"{CHAPTER}-本月财务费用-利息收入", "指标数据.实际值（万元）×10000，转换为元"),
    _spec("chapter5.finance.receivable_fee", "5.3/应收账款资金占用费", "应收账款资金占用费", f"{CHAPTER}-本月财务费用-利息支出-应收账款资金占用费", "指标数据.实际值（万元）×10000，转换为元"),
    _spec("chapter5.finance.note_fee", "5.3/应收票据资金占用费", "应收票据资金占用费", f"{CHAPTER}-本月财务费用-利息支出-应收票据资金占用费", "指标数据.实际值（万元）×10000，转换为元"),
    _spec("chapter5.finance.other_fee", "5.3/其他类型资金占用费", "其他类型资金占用费", f"{CHAPTER}-本月财务费用-利息支出-其他类型资金占用费", "指标数据.实际值（万元）×10000，转换为元"),
)

GROUP_SPECS = (
    ("chapter5.overdue_top", "5.1/逾期金额前五客户", "逾期账款", f"{CHAPTER}-逾期金额前五客户-应收账款-逾期账款"),
    ("chapter5.due_top", "5.1/次月新增到期款前五客户", "本月新增到期款", f"{CHAPTER}-本月新增到期款前五客户-本月新增到期款"),
    ("chapter5.impairment_top", "5.2/减值损失影响金额TOP5客户", "当年增加减值损失", f"{CHAPTER}-减值损失影响金额TOP5客户-当年增加减值损失"),
    ("chapter5.aging_top", "5.2/预计跳账龄TOP5客户", "净增加减值金额", f"{CHAPTER}-本月若未清收预计跳账龄的TOP5客户-净增加减值金额"),
    ("chapter5.finance_top", "5.3/财务费用排名前三客户", "财务费用排名前三的客户", f"{CHAPTER}-本月财务费用-财务费用排名前三的客户"),
)


def format_chapter5_strict(raw_data: Any, period: str = "") -> Tuple[str, Dict[str, Any]]:
    subject = _subject(raw_data)
    rows = subject.get("章节数据")
    if not isinstance(rows, list) or not rows:
        raise ChapterDataError("第五章严格映射失败：章节数据为空。")
    sources: Dict[str, Dict[str, Any]] = {}
    values: Dict[str, Optional[Dict[str, str]]] = {}
    for spec in CHAPTER5_FIELD_MAP:
        values[spec.field_id], sources[spec.field_id] = _select_unique(rows, spec)
    for field_id, position, name, path in GROUP_SPECS:
        sources[field_id] = _audit_group(rows, field_id, position, name, path)

    metadata = {key: subject.get(key, "") for key in ("月份", "部门编码", "区域经理工号", "部门名称", "区域经理姓名", "岗位名称", "章节名称")}
    metadata["月份"] = metadata["月份"] or period
    month = _month(metadata["月份"])
    next_month = 1 if month == 12 else month + 1
    previous_month = 12 if month == 1 else month - 1
    markdown = _build_markdown(values, sources, month, next_month, previous_month)
    total = values.get("chapter5.receivable.total")
    omit = _omit_result(total)
    cleaned = {"metadata": metadata, "values": values, "field_sources": sources, "omit": omit}
    stats = {"cleaned_data": cleaned, "field_sources": sources, "省略判断": omit, "warnings": _warnings(sources)}
    return ("" if omit["是否省略第五章"] else markdown), stats


def build_chapter5_apipost_checklist(stats: Dict[str, Any]) -> str:
    sources = stats["field_sources"]
    lines = [
        "# 第五章 ApiPost 取数核对清单", "",
        "接口参数：`MOUDLE=5`，`ZEMPLOYEE=06427`，`CALMONTH=202606`。", "",
        "复制“ApiPost 搜索内容”中的任一完整键值对到响应 JSON 搜索；最终匹配条件同时使用指标名称和指标路径。", "",
        "| 报告位置 | ApiPost搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for source in sources.values():
        search = f'`"指标名称": "{source["match"]["指标名称"]}"`<br>`"指标路径": "{source["match"]["指标路径"]}"`'
        raw = "；".join(source.get("raw_values", [])) or "搜索不到"
        lines.append("| " + " | ".join([
            source["report_position"], search, "`指标数据.实际值` / `指标数据.单位`",
            raw, source.get("report_value", PENDING), source["calculation"], source["status"],
        ]) + " |")
    lines.extend(["", "## 结论", "", "所有 TOP 客户明细均缺少客户编码/名称等记录级唯一键；重复记录不能可靠归组，因此未按数组顺序或金额大小生成客户名单。"])
    return "\n".join(lines) + "\n"


def _subject(raw_data: Any) -> Dict[str, Any]:
    if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
        return raw_data["data"]
    if isinstance(raw_data, dict):
        return raw_data
    raise ChapterDataError("第五章严格映射失败：原始数据不是对象。")


def _matching(rows: Iterable[Any], name: str, path: str) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict) and r.get("指标名称") == name and r.get("指标路径") == path]


def _raw(row: Dict[str, Any]) -> Tuple[Optional[str], str]:
    data = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
    value = data.get("实际值")
    return (None if value is None or str(value).strip() == "" else str(value).strip(), str(data.get("单位") or ""))


def _select_unique(rows: List[Dict[str, Any]], spec: FieldSpec) -> Tuple[Optional[Dict[str, str]], Dict[str, Any]]:
    matched = _matching(rows, spec.name, spec.path)
    raw_pairs = [_raw(row) for row in matched]
    valid = [(value, unit) for value, unit in raw_pairs if value is not None]
    distinct = {(value, unit) for value, unit in valid}
    source = _source_base(spec.field_id, spec.report_position, spec.name, spec.path, spec.calculation)
    source["matched_count"] = len(matched)
    source["raw_values"] = [f"{value}{unit}" if value is not None else "null" for value, unit in raw_pairs]
    if not valid:
        source.update(status="缺失", report_value=PENDING)
        return None, source
    if len(distinct) != 1:
        source.update(status="重复冲突", report_value=PENDING)
        return None, source
    value, unit = valid[0]
    report = _converted_report(value, unit) if "×10000" in spec.calculation else f"{value}{unit}"
    if report == PENDING:
        source.update(status="单位缺失或不支持", report_value=PENDING)
        return None, source
    source.update(status="正常" if len(matched) == 1 else "重复但值一致", report_value=report)
    return {"raw_value": value, "unit": unit, "report_value": report}, source


def _audit_group(rows: List[Dict[str, Any]], field_id: str, position: str, name: str, path: str) -> Dict[str, Any]:
    matched = _matching(rows, name, path)
    source = _source_base(field_id, position, name, path, "不计算；缺少客户唯一键，禁止按数组顺序或数值大小归组")
    source["matched_count"] = len(matched)
    source["raw_values"] = [f"{v}{u}" if v is not None else "null" for v, u in map(_raw, matched)]
    source["report_value"] = PENDING
    if not matched:
        source["status"] = "缺失"
    elif len({pair for pair in map(_raw, matched)}) > 1:
        source["status"] = "重复冲突（且缺客户唯一键）"
    else:
        source["status"] = "缺客户唯一键"
    values = [_decimal_or_none(value) for value, _unit in map(_raw, matched)]
    values = [value for value in values if value is not None]
    if values:
        source["data_status"] = "nonzero" if any(value != 0 for value in values) else "zero"
    else:
        source["data_status"] = "missing"
    return source


def _decimal_or_none(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _source_base(field_id: str, position: str, name: str, path: str, calculation: str) -> Dict[str, Any]:
    return {"field_id": field_id, "report_position": position, "match": {"指标名称": name, "指标路径": path}, "value_path": "指标数据.实际值", "unit_path": "指标数据.单位", "calculation": calculation}


def _converted_report(value: str, unit: str) -> str:
    if unit != "万元":
        return PENDING
    try:
        return f"{Decimal(value) * Decimal(10000)}元"
    except InvalidOperation:
        return PENDING


def _display(values: Dict[str, Optional[Dict[str, str]]], field_id: str) -> str:
    item = values.get(field_id)
    return item["report_value"] if item else PENDING


def _build_markdown(values: Dict[str, Optional[Dict[str, str]]], sources: Dict[str, Dict[str, Any]], month: int, next_month: int, previous_month: int) -> str:
    d = lambda field_id: _display(values, field_id)
    pending_row_3 = f"| {PENDING} | {PENDING} | {PENDING} |"
    pending_row_2 = f"| {PENDING} | {PENDING} |"
    aging_jump_block = _strict_aging_jump_block(sources.get("chapter5.aging_top", {}), next_month, PENDING)
    lines = [
        "# 五、应收分析", "", "## 5.1 应收款项概况", "",
        f"应收款项总额：{d('chapter5.receivable.total')}", "", "应收款项结构：",
        f"- 应收款项 {d('chapter5.receivable.total')}",
        f"  - 应收票据 {d('chapter5.receivable.notes')}",
        f"  - 保证金 {d('chapter5.receivable.deposit')}",
        f"  - 供应链票证 {d('chapter5.receivable.supply_chain')}",
        f"  - 应收账款 {d('chapter5.receivable.accounts')}",
        f"    - 经销 {d('chapter5.receivable.distribution')}",
        f"      - 逾期（含诉讼） {d('chapter5.receivable.distribution_overdue')}",
        f"    - 直销 {d('chapter5.receivable.direct')}",
        f"      - 暴雷直销应收 {d('chapter5.receivable.risk_direct')}",
        f"        - 逾期 {d('chapter5.receivable.risk_direct_overdue')}",
        f"      - 非暴雷直销应收 {d('chapter5.receivable.normal_direct')}",
        f"        - 逾期 {d('chapter5.receivable.normal_direct_overdue')}", "",
        "备注：逾期金额含诉讼，保证金不含保函。", "", "◇ **逾期金额前五客户**", "",
        "| 客户名称 | 应收账款 | 其中：逾期账款 |", "| --- | --- | --- |", pending_row_3, "",
        "备注：接口未提供客户编码/名称，重复指标无法唯一归组；更详细名单请见销售日报应收数据。", "",
        f"◇ **{next_month}月新增到期款{d('chapter5.due.total')}，金额排名前五客户：**", "",
        f"| 客户名称 | {next_month}月新增到期款 |", "| --- | --- |", pending_row_2, "",
        "## 5.2 当年增加减值损失", "",
        f"◇ 当年增加减值损失{d('chapter5.impairment.total')}=应收减值{d('chapter5.impairment.receivable')}+工抵房减值{d('chapter5.impairment.offset_house')}+其他类型减值{d('chapter5.impairment.other')}（保证金、商票、票证等）。", "",
        f"账龄变动增加减值{d('chapter5.impairment.aging_change')}、规模变动增加减值{d('chapter5.impairment.scale_change')}、诉讼变动增加减值{d('chapter5.impairment.litigation_change')}。", "",
        "◇ **减值损失影响金额 TOP5 客户**", "",
        f"| 客户名称 | 截止{previous_month}月应收金额 | 当年增加减值损失 | 其中：应收减值（含坏账） | 工抵房减值 | 其他类型减值（保证金、商票、票证等） |",
        "| --- | --- | --- | --- | --- | --- |", f"| {PENDING} | {PENDING} | {PENDING} | {PENDING} | {PENDING} | {PENDING} |", "",
        aging_jump_block, "",
        "## 5.3 财务费用", "",
        f"◇ {month}月财务费用{d('chapter5.finance.expense')}=利息支出{d('chapter5.finance.interest_expense')}-利息收入{d('chapter5.finance.interest_income')}，其中利息支出{d('chapter5.finance.interest_expense')}=应收账款资金占用费{d('chapter5.finance.receivable_fee')}+应收票据资金占用费{d('chapter5.finance.note_fee')}+其他类型资金占用费{d('chapter5.finance.other_fee')}。", "",
        f"◇ {month}月财务费用排名前三的客户为{PENDING}。", "", "| 客户名称 | 财务费用 |", "| --- | --- |", pending_row_2, "",
        "## 5.4 行动指南", "", "◇ 当年补提减值损失，需要减少应收、缩短账龄；针对逾期需加大清收力度，如找担保人催收、发送律师函、诉讼催收等。",
    ]
    return "\n".join(lines) + "\n"


def _strict_aging_jump_block(source: Dict[str, Any], next_month: int, pending: str) -> str:
    if source.get("data_status") == "zero":
        return f"◇ **暂无{next_month}月未清收预计跳账龄的客户**"
    return "\n\n".join([
        f"◇ **{next_month}月未清收预计跳账龄的 TOP5 客户**",
        "预计跳账龄客户明细：",
        "| 账龄跳到 | 净增加减值金额 | 1 年≤账龄＜2 年 |  | 2 年≤账龄＜3 年 |  | 账龄≥3 年 |  |",
        "| 客户名称 |  | 应收金额 | 减值损失 | 应收金额 | 减值损失 | 应收金额 | 减值损失 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        f"| {pending} | {pending} | {pending} | {pending} | {pending} | {pending} | {pending} | {pending} |",
    ])


def _omit_result(total: Optional[Dict[str, str]]) -> Dict[str, Any]:
    if not total:
        return {"是否省略第五章": False, "判断": "保留", "原因": "应收款项总额缺失，禁止推断"}
    try:
        value = Decimal(total["raw_value"])
    except InvalidOperation:
        return {"是否省略第五章": False, "判断": "保留", "原因": "应收款项总额不可解析"}
    if total["unit"] == "元":
        value = value / Decimal(10000)
    elif total["unit"] != "万元":
        return {"是否省略第五章": False, "判断": "保留", "原因": "应收款项总额单位待确认"}
    omit = value < Decimal(10)
    return {"是否省略第五章": omit, "判断": "省略" if omit else "保留", "原因": f"应收款项总额{value}万元{'低于' if omit else '不低于'}10万元", "计算公式": "若单位为元：实际值÷10000；再与10万元比较"}


def _month(period: Any) -> int:
    text = str(period or "")
    return int(text[-2:]) if len(text) >= 6 and text[-2:].isdigit() else 0


def _warnings(sources: Dict[str, Dict[str, Any]]) -> List[str]:
    return [f'{s["report_position"]}：{s["status"]}' for s in sources.values() if s["status"] not in {"正常", "重复但值一致"}]
