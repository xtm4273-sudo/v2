"""第五章生成器 - 应收分析。

当前真实接口字段尚未完全上线。本文件先定义第五章内部数据契约、接口适配入口、
省略判断和排序规则，后续只需要把接口原始 JSON 转换到该契约即可继续复用渲染
与报告生成逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple
import logging

from Data import EMPTY_DATA_MESSAGE, ChapterDataError

logger = logging.getLogger(__name__)


OMIT_RECEIVABLE_THRESHOLD_WAN = 10
TOP_CUSTOMER_LIMIT = 5
FINANCIAL_EXPENSE_CUSTOMER_LIMIT = 3
IMPAIRMENT_AGING_BUCKETS = ("账龄<1年", "1年<=账龄<2年", "2年<=账龄<3年", "账龄>=3年")
AGING_JUMP_BUCKETS = ("1年<=账龄<2年", "2年<=账龄<3年", "账龄>=3年")
DEFAULT_CHAPTER5_ACTION_GUIDE_TEXT = (
    "当年补提减值损失，需要减少应收、缩短账龄；针对逾期需加大清收力度，"
    "如找担保人催收、发送律师函、诉讼催收等。"
)


@dataclass(frozen=True)
class Amount:
    value: Optional[float]
    unit: str = "万元"

    def to_wan(self) -> Optional[float]:
        return amount_to_wan(self.value, self.unit)

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "unit": self.unit}


@dataclass
class ReceivableTreeNode:
    name: str
    amount: Amount = field(default_factory=lambda: Amount(None, "万元"))
    children: List["ReceivableTreeNode"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "amount": self.amount.to_dict(),
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class CustomerAmountRecord:
    customer_name: str
    amount: Amount
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_name": self.customer_name,
            "amount": self.amount.to_dict(),
            "extra": self.extra,
        }


@dataclass
class Chapter5Data:
    metadata: Dict[str, Any]
    receivable_tree: Optional[ReceivableTreeNode] = None
    overdue_top_customers: List[CustomerAmountRecord] = field(default_factory=list)
    next_month_due_top_customers: List[CustomerAmountRecord] = field(default_factory=list)
    impairment_summary: Dict[str, Any] = field(default_factory=dict)
    impairment_top_customers: List[CustomerAmountRecord] = field(default_factory=list)
    aging_jump_top_customers: List[CustomerAmountRecord] = field(default_factory=list)
    financial_expense: Dict[str, Any] = field(default_factory=dict)
    financial_expense_top_customers: List[CustomerAmountRecord] = field(default_factory=list)
    raw_items: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "receivable_tree": self.receivable_tree.to_dict() if self.receivable_tree else None,
            "overdue_top_customers": [row.to_dict() for row in self.overdue_top_customers],
            "next_month_due_top_customers": [row.to_dict() for row in self.next_month_due_top_customers],
            "impairment_summary": self.impairment_summary,
            "impairment_top_customers": [row.to_dict() for row in self.impairment_top_customers],
            "aging_jump_top_customers": [row.to_dict() for row in self.aging_jump_top_customers],
            "financial_expense": self.financial_expense,
            "financial_expense_top_customers": [row.to_dict() for row in self.financial_expense_top_customers],
            "raw_items": self.raw_items,
            "warnings": self.warnings,
        }


def format_chapter5_data(
    raw_data: Any,
    period: str = "",
    action_guide_text: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """将第五章数据清洗为内部契约，并生成正式 Markdown。"""
    chapter_data = normalize_chapter5_data(raw_data, period=period)
    omit = infer_chapter5_omit(chapter_data)
    markdown = build_chapter5_markdown(chapter_data, omit, action_guide_text=action_guide_text)
    stats = build_chapter5_stats(chapter_data, omit)
    stats["行动指南生成方式"] = "AI" if action_guide_text else "规则"
    return markdown, stats


async def format_chapter5_data_with_ai(
    raw_data: Any,
    period: str = "",
    model: Optional[Any] = None,
    action_writer: Optional[Any] = None,
) -> Tuple[str, Dict[str, Any]]:
    """生成第五章 Markdown，并可选用 AI 改写行动指南。

    AI 只参与「行动指南」段落；表格、公式、排序、省略规则仍全部由规则生成。
    未传入 model/action_writer、调用失败或输出为空时，回退到固定行动指南。
    """
    chapter_data = normalize_chapter5_data(raw_data, period=period)
    omit = infer_chapter5_omit(chapter_data)
    action_context = build_chapter5_action_context(chapter_data, omit)
    action_guide_text = DEFAULT_CHAPTER5_ACTION_GUIDE_TEXT

    if not omit.get("是否省略第五章"):
        if action_writer is not None:
            action_guide_text = await action_writer.generate(
                action_context=action_context,
                fallback_text=DEFAULT_CHAPTER5_ACTION_GUIDE_TEXT,
            )
        elif model is not None:
            from ReportGenerator.chapter5_ai_writer import generate_chapter5_action_guide

            action_guide_text = await generate_chapter5_action_guide(
                action_context=action_context,
                model=model,
                fallback_text=DEFAULT_CHAPTER5_ACTION_GUIDE_TEXT,
            )

    markdown = build_chapter5_markdown(chapter_data, omit, action_guide_text=action_guide_text)
    stats = build_chapter5_stats(chapter_data, omit, action_context=action_context)
    stats["行动指南生成方式"] = "AI" if action_guide_text != DEFAULT_CHAPTER5_ACTION_GUIDE_TEXT else "规则"
    return markdown, stats


def normalize_chapter5_data(raw_data: Any, period: str = "") -> Chapter5Data:
    """标准化第五章数据。

    支持三类输入：
    1. 真实接口完整响应：{"code": 1, "data": {...}}。
    2. 真实接口 data 对象：{"月份": "...", "章节数据": [...]}。
    3. 当前开发期标准 mock：直接包含 receivable_tree、TOP 客户等字段。
    """
    subject = _extract_subject(raw_data)
    metadata = _extract_metadata(subject, period=period)
    rows = subject.get("章节数据") if isinstance(subject.get("章节数据"), list) else []
    warnings: List[str] = []

    receivable_tree = _parse_receivable_tree(subject)
    overdue_top = _sort_customer_records(
        _customer_records_from_list(
            subject.get("overdue_top_customers"),
            amount_key="overdue_amount",
            fallback_amount_key="amount",
        ),
        limit=TOP_CUSTOMER_LIMIT,
    )
    next_month_due = _sort_customer_records(
        _customer_records_from_list(
            subject.get("next_month_due_top_customers"),
            amount_key="due_amount",
            fallback_amount_key="amount",
        ),
        limit=TOP_CUSTOMER_LIMIT,
    )
    impairment_top = _sort_customer_records(
        _customer_records_from_list(
            subject.get("impairment_top_customers"),
            amount_key="current_year_impairment_increase",
            fallback_amount_key="amount",
        ),
        limit=TOP_CUSTOMER_LIMIT,
    )
    aging_jump_top = _sort_customer_records(
        _customer_records_from_list(
            subject.get("aging_jump_top_customers"),
            amount_key="net_impairment_increase",
            fallback_amount_key="amount",
        ),
        limit=TOP_CUSTOMER_LIMIT,
    )
    financial_expense_top = _sort_customer_records(
        _customer_records_from_list(
            subject.get("financial_expense_top_customers"),
            amount_key="financial_expense",
            fallback_amount_key="amount",
        ),
        limit=FINANCIAL_EXPENSE_CUSTOMER_LIMIT,
    )

    if not receivable_tree and not rows:
        warnings.append("第五章接口章节数据为空，已保留接口元信息，等待应收分析字段上线。")
    elif rows and not receivable_tree:
        receivable_tree = _parse_receivable_tree_from_metric_rows(rows, warnings)
    if rows:
        flat = _normalize_from_metric_rows(rows, warnings)
        if flat.get("receivable_tree") and not receivable_tree:
            receivable_tree = flat["receivable_tree"]
        if not overdue_top:
            overdue_top = flat.get("overdue_top_customers", [])
        if not next_month_due:
            next_month_due = flat.get("next_month_due_top_customers", [])
        if not impairment_top:
            impairment_top = flat.get("impairment_top_customers", [])
        if not aging_jump_top:
            aging_jump_top = flat.get("aging_jump_top_customers", [])
        if not financial_expense_top:
            financial_expense_top = flat.get("financial_expense_top_customers", [])
        impairment_summary = _normalize_impairment_summary(subject.get("impairment_summary")) or flat.get("impairment_summary", {})
        financial_expense = _normalize_financial_expense(subject.get("financial_expense")) or flat.get("financial_expense", {})
    else:
        impairment_summary = _normalize_impairment_summary(subject.get("impairment_summary"))
        financial_expense = _normalize_financial_expense(subject.get("financial_expense"))

    return Chapter5Data(
        metadata=metadata,
        receivable_tree=receivable_tree,
        overdue_top_customers=overdue_top,
        next_month_due_top_customers=next_month_due,
        impairment_summary=impairment_summary,
        impairment_top_customers=impairment_top,
        aging_jump_top_customers=aging_jump_top,
        financial_expense=financial_expense,
        financial_expense_top_customers=financial_expense_top,
        raw_items=rows,
        warnings=warnings,
    )


def infer_chapter5_omit(chapter_data: Chapter5Data) -> Dict[str, Any]:
    """判断第五章是否省略。"""
    total = chapter_data.receivable_tree.amount if chapter_data.receivable_tree else Amount(None, "")
    total_wan = total.to_wan()

    if total.value is None:
        return {
            "是否省略第五章": False,
            "判断": "保留",
            "原因": "缺个人应收款项总额，按规则不能省略第五章。",
        }
    if total_wan is None:
        return {
            "是否省略第五章": False,
            "判断": "保留",
            "原因": "个人应收款项总额单位或口径待确认，按规则不能省略第五章。",
            "依据": total.to_dict(),
        }

    should_omit = total_wan <= OMIT_RECEIVABLE_THRESHOLD_WAN
    return {
        "是否省略第五章": should_omit,
        "判断": "省略" if should_omit else "保留",
        "原因": "个人应收款项小于等于 10 万" if should_omit else "个人应收款项大于 10 万",
        "依据": {"value_wan": total_wan, "source": total.to_dict()},
    }


def build_chapter5_markdown(
    chapter_data: Chapter5Data,
    omit: Dict[str, Any],
    action_guide_text: str = DEFAULT_CHAPTER5_ACTION_GUIDE_TEXT,
) -> str:
    """生成第五章正式 Markdown。"""
    if omit.get("是否省略第五章"):
        return ""

    period = str(chapter_data.metadata.get("月份") or "")
    month_label, next_month_label = month_labels(period)
    previous_month_label = previous_month(period)
    lines = [
        "# 五、应收分析",
        "",
        "## 5.1 应收款项概况",
        "",
        _build_receivable_tree_section(chapter_data.receivable_tree),
        "",
        "备注：逾期金额含诉讼，保证金不含保函。",
        "",
        "◇ **逾期金额前五客户**",
        "",
        _build_overdue_table(chapter_data.overdue_top_customers),
        "",
        "备注：更详细名单请见销售日报应收数据。",
        "",
        f"◇ **{next_month_label}新增到期款金额排名前五客户：**",
        "",
        _build_next_month_due_table(chapter_data.next_month_due_top_customers, next_month_label),
    ]

    impairment_text = _build_impairment_summary_text(chapter_data.impairment_summary)
    lines.extend(
        [
            "",
            "## 5.2 当年增加减值损失",
            "",
            f"◇ {impairment_text}",
            "",
            "◇ **减值损失影响金额 TOP5 客户**",
            "",
            _build_impairment_top_table(chapter_data.impairment_top_customers, previous_month_label),
            "",
            f"◇ **{next_month_label}若未清收预计跳账龄的 TOP5 客户**",
            "",
            _build_aging_jump_table(chapter_data.aging_jump_top_customers),
        ]
    )

    lines.extend(
        [
            "",
            "## 5.3 财务费用",
            "",
            f"◇ {_build_financial_expense_text(chapter_data.financial_expense, month_label)}",
            "",
            f"◇ {_build_financial_expense_top_sentence(chapter_data.financial_expense_top_customers, month_label)}",
            "",
            _build_financial_expense_table(chapter_data.financial_expense_top_customers),
        ]
    )
    lines.extend(
        [
            "",
            "### 行动指南：",
            "",
            f"◇ {action_guide_text or DEFAULT_CHAPTER5_ACTION_GUIDE_TEXT}",
        ]
    )

    if chapter_data.warnings:
        lines.extend(["", "<!-- " + "；".join(chapter_data.warnings) + " -->"])

    return "\n".join(lines).rstrip() + "\n"


def build_chapter5_stats(
    chapter_data: Chapter5Data,
    omit: Dict[str, Any],
    action_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "省略判断": omit,
        "接口月份": chapter_data.metadata.get("月份", ""),
        "逾期客户数": len(chapter_data.overdue_top_customers),
        "次月到期客户数": len(chapter_data.next_month_due_top_customers),
        "减值损失客户数": len(chapter_data.impairment_top_customers),
        "跳账龄客户数": len(chapter_data.aging_jump_top_customers),
        "财务费用客户数": len(chapter_data.financial_expense_top_customers),
        "warnings": chapter_data.warnings,
        "cleaned_data": chapter_data.to_dict(),
        "action_context": action_context or build_chapter5_action_context(chapter_data, omit),
    }


def build_chapter5_action_context(chapter_data: Chapter5Data, omit: Dict[str, Any]) -> Dict[str, Any]:
    """构造仅供行动指南使用的事实包。"""
    total = chapter_data.receivable_tree.amount if chapter_data.receivable_tree else Amount(None, "")
    return {
        "metadata": {
            "月份": chapter_data.metadata.get("月份", ""),
            "区域经理工号": chapter_data.metadata.get("区域经理工号", ""),
            "区域经理姓名": chapter_data.metadata.get("区域经理姓名", ""),
            "部门名称": chapter_data.metadata.get("部门名称", ""),
        },
        "省略判断": omit,
        "应收款项总额": _action_amount(total),
        "逾期金额前五客户": [
            _action_record(row, extra_amount_keys=("receivable_amount",), extra_text_keys=())
            for row in chapter_data.overdue_top_customers
        ],
        "次月新增到期款前五客户": [
            _action_record(row, extra_amount_keys=(), extra_text_keys=())
            for row in chapter_data.next_month_due_top_customers
        ],
        "减值损失汇总": {
            "当年增加减值损失": _action_amount(
                Amount(chapter_data.impairment_summary.get("current_year_increase"), chapter_data.impairment_summary.get("unit", "万元"))
            ),
            "应收减值": _action_amount(
                Amount(chapter_data.impairment_summary.get("receivable_impairment"), chapter_data.impairment_summary.get("unit", "万元"))
            ),
            "工抵房减值": _action_amount(
                Amount(chapter_data.impairment_summary.get("offset_house_impairment"), chapter_data.impairment_summary.get("unit", "万元"))
            ),
            "其他类型减值": _action_amount(
                Amount(chapter_data.impairment_summary.get("other_type_impairment"), chapter_data.impairment_summary.get("unit", "万元"))
            ),
        },
        "减值损失影响金额TOP5客户": [
            _action_record(
                row,
                extra_amount_keys=(
                    "receivable_amount",
                    "receivable_impairment",
                    "offset_house_impairment",
                    "other_type_impairment",
                ),
                extra_text_keys=(),
            )
            for row in chapter_data.impairment_top_customers
        ],
        "预计跳账龄TOP5客户": [
            _action_aging_jump_record(row)
            for row in chapter_data.aging_jump_top_customers
        ],
        "财务费用": {
            key: _action_amount(Amount(value, chapter_data.financial_expense.get("unit", "元")))
            for key, value in chapter_data.financial_expense.items()
            if key != "unit"
        },
        "财务费用前三客户": [
            _action_record(row, extra_amount_keys=(), extra_text_keys=())
            for row in chapter_data.financial_expense_top_customers
        ],
        "数据提示": chapter_data.warnings,
    }


def _action_amount(amount: Amount) -> Dict[str, Any]:
    return {
        "value": amount.value,
        "unit": amount.unit,
        "display": _format_amount(amount),
        "value_wan": amount.to_wan(),
    }


def _action_record(
    record: CustomerAmountRecord,
    extra_amount_keys: Iterable[str] = (),
    extra_text_keys: Iterable[str] = (),
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "客户名称": record.customer_name,
        "金额": _action_amount(record.amount),
    }
    for key in extra_amount_keys:
        result[key] = _action_amount(_extra_amount(record, key))
    for key in extra_text_keys:
        result[key] = record.extra.get(key, "")
    return result


def _action_aging_jump_record(record: CustomerAmountRecord) -> Dict[str, Any]:
    result = _action_record(record, extra_amount_keys=(), extra_text_keys=("jump_to_age",))
    result["账龄区间"] = {
        bucket: {
            "应收金额": _action_amount(_aging_bucket_amount(record, bucket, "receivable_amount")),
            "减值损失": _action_amount(_aging_bucket_amount(record, bucket, "impairment_loss")),
        }
        for bucket in AGING_JUMP_BUCKETS
    }
    return result


class Chapter5Generator:
    """第五章「应收分析」生成器。"""

    def __init__(
        self,
        data: Any,
        guideline: str = "",
        period: str = "",
        sale_id: Optional[str] = None,
        sale_name: Optional[str] = None,
        action_model: Optional[Any] = None,
        action_writer: Optional[Any] = None,
    ):
        self.raw_data = data
        self.guideline = guideline
        self.period = period
        self.sale_id = sale_id
        self.sale_name = sale_name
        self.action_model = action_model
        self.action_writer = action_writer

    def run(self) -> str:
        markdown, _stats = format_chapter5_data(self.raw_data, period=self.period)
        return markdown

    async def run_async(self) -> str:
        try:
            if self.action_model is None and self.action_writer is None:
                return self.run()
            markdown, _stats = await format_chapter5_data_with_ai(
                self.raw_data,
                period=self.period,
                model=self.action_model,
                action_writer=self.action_writer,
            )
            return markdown
        except Exception as e:
            logger.error(f"第五章生成失败: {e}")
            raise


def month_labels(period: str) -> Tuple[str, str]:
    if len(period) >= 6 and period[-2:].isdigit():
        month = int(period[-2:])
        next_month = 1 if month == 12 else month + 1
        return f"{month}月", f"{next_month}月"
    return "当月", "次月"


def previous_month(period: str) -> str:
    if len(period) >= 6 and period[-2:].isdigit():
        month = int(period[-2:])
        prev_month = 12 if month == 1 else month - 1
        return f"{prev_month}月"
    return "报告月"


def amount_to_wan(value: Optional[float], unit: str) -> Optional[float]:
    if value is None:
        return None
    normalized_unit = (unit or "").strip()
    if normalized_unit in {"万元", "万"}:
        return float(value)
    if normalized_unit == "元":
        return float(value) / 10000
    return None


def _extract_subject(raw_data: Any) -> Dict[str, Any]:
    if raw_data is None:
        raise ChapterDataError(f"第五章数据清洗失败: 原始数据为 null。{EMPTY_DATA_MESSAGE}")
    if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
        return raw_data["data"]
    if isinstance(raw_data, dict):
        return raw_data
    raise ChapterDataError(f"第五章数据清洗失败: 原始数据不是对象。{EMPTY_DATA_MESSAGE}")


def _extract_metadata(subject: Dict[str, Any], period: str = "") -> Dict[str, Any]:
    keys = [
        "月份",
        "部门编码",
        "区域经理工号",
        "部门名称",
        "区域经理姓名",
        "岗位名称",
        "客户编码",
        "客户名称",
        "章节名称",
    ]
    metadata = {key: subject.get(key, "") for key in keys}
    if period and not metadata.get("月份"):
        metadata["月份"] = period
    return metadata


def _parse_receivable_tree(subject: Dict[str, Any]) -> Optional[ReceivableTreeNode]:
    tree = subject.get("receivable_tree")
    if isinstance(tree, dict):
        return _tree_node_from_dict(tree)
    return None


def _tree_node_from_dict(data: Dict[str, Any]) -> ReceivableTreeNode:
    return ReceivableTreeNode(
        name=str(data.get("name") or data.get("名称") or ""),
        amount=Amount(_to_float(data.get("amount", data.get("金额"))), str(data.get("unit") or data.get("单位") or "万元")),
        children=[
            _tree_node_from_dict(child)
            for child in data.get("children", [])
            if isinstance(child, dict)
        ],
    )


def _parse_receivable_tree_from_metric_rows(
    rows: Iterable[Dict[str, Any]],
    warnings: List[str],
) -> Optional[ReceivableTreeNode]:
    row_list = [row for row in rows if isinstance(row, dict)]
    candidates = []
    indexed_rows: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in row_list:
        name = str(row.get("指标名称") or "")
        path = str(row.get("指标路径") or "")
        metric_data = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
        if any(keyword in name or keyword in path for keyword in ("应收款项", "应收款项总额", "个人应收")):
            candidates.append((name, metric_data))
        parts = _receivable_metric_path_parts(path)
        if parts:
            indexed_rows[parts] = row

    if not candidates:
        warnings.append("章节数据中暂未识别到应收款项总额字段。")
        return None

    name, metric_data = candidates[0]
    root = ReceivableTreeNode(
        name=name or "应收款项",
        amount=Amount(_to_float(metric_data.get("实际值")), str(metric_data.get("单位") or "万元")),
    )
    root.children = _build_receivable_tree_children(indexed_rows, prefix=())
    return root


def _receivable_metric_path_parts(path: str) -> Tuple[str, ...]:
    parts = [part.strip() for part in path.split("-") if part.strip()]
    if len(parts) < 2 or parts[0] != "五、应收分析":
        return ()

    metric_parts = tuple(parts[1:])
    if metric_parts == ("应收款项",):
        return ()
    if metric_parts[:1] in {("应收账款",), ("应收票据",), ("保证金",), ("供应链票证",)}:
        return metric_parts
    return ()


def _build_receivable_tree_children(
    indexed_rows: Dict[Tuple[str, ...], Dict[str, Any]],
    prefix: Tuple[str, ...],
) -> List[ReceivableTreeNode]:
    child_names = []
    for parts in indexed_rows:
        if len(parts) <= len(prefix):
            continue
        if parts[: len(prefix)] != prefix:
            continue
        child_name = parts[len(prefix)]
        if child_name not in child_names:
            child_names.append(child_name)

    children: List[ReceivableTreeNode] = []
    for child_name in child_names:
        child_path = prefix + (child_name,)
        row = indexed_rows.get(child_path)
        if row is None:
            row = _first_descendant_row(indexed_rows, child_path)
        amount = _row_amount(row) or Amount(None, "万元")
        children.append(
            ReceivableTreeNode(
                name=child_name,
                amount=amount,
                children=_build_receivable_tree_children(indexed_rows, child_path),
            )
        )
    return children


def _first_descendant_row(
    indexed_rows: Dict[Tuple[str, ...], Dict[str, Any]],
    prefix: Tuple[str, ...],
) -> Optional[Dict[str, Any]]:
    for parts, row in indexed_rows.items():
        if parts[: len(prefix)] == prefix:
            return row
    return None


def _normalize_from_metric_rows(rows: List[Dict[str, Any]], warnings: List[str]) -> Dict[str, Any]:
    """适配真实接口的扁平 章节数据 指标行。"""
    by_name: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("指标名称") or "")
        path = str(row.get("指标路径") or "")
        key = f"{path}|{name}"
        by_name[key] = row

    receivable_root = _parse_receivable_tree_from_metric_rows(rows, warnings)

    impairment_summary = _impairment_summary_from_rows(rows)
    financial_expense = _financial_expense_from_rows(rows)

    overdue = _parse_pair_customer_rows(
        rows,
        section="逾期金额前五客户",
        first_name="应收账款",
        second_name="逾期账款",
        amount_key="overdue_amount",
        extra_first_key="receivable_amount",
        limit=TOP_CUSTOMER_LIMIT,
    )
    next_due = _parse_single_customer_rows(
        rows,
        section="本月新增到期款前五客户",
        name="本月新增到期款",
        amount_key="due_amount",
        limit=TOP_CUSTOMER_LIMIT,
    )
    impairment_top = _parse_impairment_customer_rows(rows)
    aging_jump_top = _parse_aging_jump_customer_rows(rows)
    financial_top = _parse_single_customer_rows(
        rows,
        section="财务费用排名前三的客户",
        name="财务费用排名前三的客户",
        amount_key="financial_expense",
        limit=FINANCIAL_EXPENSE_CUSTOMER_LIMIT,
        convert_wan_to_yuan=True,
    )

    if any(record.customer_name.endswith("接口未提供名称）") for record in overdue + next_due + impairment_top + aging_jump_top + financial_top):
        warnings.append("第五章 TOP 客户明细接口未提供客户名称，已使用客户序号占位。")

    return {
        "receivable_tree": receivable_root,
        "impairment_summary": impairment_summary,
        "financial_expense": financial_expense,
        "overdue_top_customers": overdue,
        "next_month_due_top_customers": next_due,
        "impairment_top_customers": impairment_top,
        "aging_jump_top_customers": aging_jump_top,
        "financial_expense_top_customers": financial_top,
    }


def _find_row(rows: List[Dict[str, Any]], name: str = "", path_contains: str = "") -> Optional[Dict[str, Any]]:
    for row in rows:
        row_name = str(row.get("指标名称") or "")
        path = str(row.get("指标路径") or "")
        if name and row_name != name:
            continue
        if path_contains and path_contains not in path:
            continue
        return row
    return None


def _row_amount(row: Optional[Dict[str, Any]], convert_wan_to_yuan: bool = False) -> Optional[Amount]:
    if not row:
        return None
    metric = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
    value = _to_float(metric.get("实际值"))
    unit = str(metric.get("单位") or "万元")
    if value is None:
        return Amount(None, unit)
    if convert_wan_to_yuan and unit == "万元":
        return Amount(value * 10000, "元")
    return Amount(value, unit)


def _impairment_summary_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def val(name: str) -> Optional[float]:
        row = _find_row(rows, name=name, path_contains=f"五、应收分析-当年增加减值损失-{name}")
        if row is None and name == "当年增加减值损失":
            row = _find_row(rows, name=name, path_contains="五、应收分析-当年增加减值损失")
        amount = _row_amount(row)
        return amount.value if amount else None

    summary = {
        "current_year_increase": val("当年增加减值损失"),
        "receivable_impairment": val("应收减值（含坏账）"),
        "offset_house_impairment": val("工抵房减值"),
        "other_type_impairment": val("其他类型减值"),
        "aging_change": val("账龄变动增加减值"),
        "scale_change": val("规模变动增加减值"),
        "litigation_change": val("诉讼变动增加减值"),
        "unit": "万元",
    }
    return summary if any(v is not None for k, v in summary.items() if k != "unit") else {}


def _financial_expense_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    mapping = {
        "expense": ("本月财务费用", "五、应收分析-本月财务费用"),
        "interest_expense": ("利息支出", "五、应收分析-本月财务费用-利息支出"),
        "interest_income": ("利息收入", "五、应收分析-本月财务费用-利息收入"),
        "receivable_funding_fee": ("应收账款资金占用费", "应收账款资金占用费"),
        "note_funding_fee": ("应收票据资金占用费", "应收票据资金占用费"),
        "other_type_funding_fee": ("其他类型资金占用费", "其他类型资金占用费"),
    }
    result: Dict[str, Any] = {"unit": "元"}
    for key, (name, path_part) in mapping.items():
        row = _find_row(rows, name=name, path_contains=path_part)
        amount = _row_amount(row, convert_wan_to_yuan=True)
        result[key] = amount.value if amount else None
    return result if any(v is not None for k, v in result.items() if k != "unit") else {}


def _parse_pair_customer_rows(
    rows: List[Dict[str, Any]],
    section: str,
    first_name: str,
    second_name: str,
    amount_key: str,
    extra_first_key: str,
    limit: int,
) -> List[CustomerAmountRecord]:
    records: List[CustomerAmountRecord] = []
    pending: Optional[Amount] = None
    for row in rows:
        path = str(row.get("指标路径") or "")
        name = str(row.get("指标名称") or "")
        if section not in path:
            continue
        if name == first_name:
            pending = _row_amount(row)
            continue
        if name == second_name:
            amount = _row_amount(row)
            if amount and amount.value not in (None, 0):
                extra = {extra_first_key: pending.value if pending else None}
                records.append(_customer_record(len(records) + 1, amount, extra))
            pending = None
    return _sort_customer_records(records, limit)


def _parse_single_customer_rows(
    rows: List[Dict[str, Any]],
    section: str,
    name: str,
    amount_key: str,
    limit: int,
    convert_wan_to_yuan: bool = False,
) -> List[CustomerAmountRecord]:
    records: List[CustomerAmountRecord] = []
    for row in rows:
        path = str(row.get("指标路径") or "")
        row_name = str(row.get("指标名称") or "")
        if section not in path or row_name != name:
            continue
        amount = _row_amount(row, convert_wan_to_yuan=convert_wan_to_yuan)
        if amount and amount.value not in (None, 0):
            records.append(_customer_record(len(records) + 1, amount, {amount_key: amount.value}))
    return _sort_customer_records(records, limit)


def _parse_impairment_customer_rows(rows: List[Dict[str, Any]]) -> List[CustomerAmountRecord]:
    section = "减值损失影响金额TOP5客户"
    records: List[CustomerAmountRecord] = []
    current: Dict[str, Any] = {}

    def flush() -> None:
        if not current:
            return
        amount = current.get("amount")
        if isinstance(amount, Amount) and amount.value not in (None, 0):
            records.append(_customer_record(len(records) + 1, amount, current.get("extra", {})))

    for row in rows:
        path = str(row.get("指标路径") or "")
        name = str(row.get("指标名称") or "")
        if section not in path:
            continue
        amount = _row_amount(row)
        if name == "当年增加减值损失":
            flush()
            current = {"amount": amount, "extra": {}}
            continue
        if not current:
            current = {"amount": Amount(None, "万元"), "extra": {}}
        extra = current.setdefault("extra", {})
        if name == "应收金额":
            extra["receivable_amount"] = amount.value if amount else None
        elif name == "应收减值（含坏账）":
            extra["receivable_impairment"] = amount.value if amount else None
        elif name == "工抵房减值":
            extra["offset_house_impairment"] = amount.value if amount else None
        elif name == "其他类型减值":
            extra["other_type_impairment"] = amount.value if amount else None
    flush()
    return _sort_customer_records(records, TOP_CUSTOMER_LIMIT)


def _parse_aging_jump_customer_rows(rows: List[Dict[str, Any]]) -> List[CustomerAmountRecord]:
    section = "本月若未清收预计跳账龄的TOP5客户"
    records: List[CustomerAmountRecord] = []
    for row in rows:
        path = str(row.get("指标路径") or "")
        name = str(row.get("指标名称") or "")
        if section not in path or name != "净增加减值金额":
            continue
        amount = _row_amount(row)
        if amount and amount.value not in (None, 0):
            records.append(_customer_record(len(records) + 1, amount, {}))
    return _sort_customer_records(records, TOP_CUSTOMER_LIMIT)


def _customer_record(index: int, amount: Amount, extra: Dict[str, Any]) -> CustomerAmountRecord:
    return CustomerAmountRecord(
        customer_name=f"客户{index}（接口未提供名称）",
        amount=amount,
        extra=extra,
    )


def _customer_records_from_list(
    rows: Any,
    amount_key: str,
    fallback_amount_key: str = "amount",
) -> List[CustomerAmountRecord]:
    if not isinstance(rows, list):
        return []

    records: List[CustomerAmountRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        customer_name = str(row.get("customer_name") or row.get("客户名称") or "").strip()
        if not customer_name:
            continue
        value = _to_float(row.get(amount_key, row.get(fallback_amount_key)))
        if value is None:
            continue
        unit = str(row.get("unit") or row.get("单位") or "万元")
        extra = {key: value for key, value in row.items() if key not in {"customer_name", "客户名称", amount_key, fallback_amount_key, "unit", "单位"}}
        records.append(CustomerAmountRecord(customer_name=customer_name, amount=Amount(value, unit), extra=extra))
    return records


def _sort_customer_records(records: List[CustomerAmountRecord], limit: int) -> List[CustomerAmountRecord]:
    return sorted(
        records,
        key=lambda record: (record.amount.to_wan() is not None, record.amount.to_wan() or -1),
        reverse=True,
    )[:limit]


def _normalize_impairment_summary(summary: Any) -> Dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    unit = str(summary.get("unit") or summary.get("单位") or "万元")
    return {
        "current_year_increase": _to_float(summary.get("current_year_increase")),
        "receivable_impairment": _to_float(
            summary.get("receivable_impairment", summary.get("aging_change"))
        ),
        "offset_house_impairment": _to_float(
            summary.get("offset_house_impairment", summary.get("scale_change"))
        ),
        "other_type_impairment": _to_float(
            summary.get("other_type_impairment", summary.get("litigation_change"))
        ),
        "unit": unit,
    }


def _normalize_financial_expense(expense: Any) -> Dict[str, Any]:
    if not isinstance(expense, dict):
        return {}
    unit = str(expense.get("unit") or expense.get("单位") or "元")
    keys = [
        "expense",
        "interest_expense",
        "interest_income",
        "receivable_funding_fee",
        "note_funding_fee",
        "other_type_funding_fee",
    ]
    return {key: _to_float(expense.get(key)) for key in keys} | {"unit": unit}


def _build_impairment_summary_text(summary: Dict[str, Any]) -> str:
    if not summary:
        return "当年增加减值损失数据暂未提供。"

    unit = summary.get("unit", "万元")
    return (
        "当年增加减值损失="
        f"应收减值{_format_amount(Amount(summary.get('receivable_impairment'), unit))}"
        f"+工抵房减值{_format_amount(Amount(summary.get('offset_house_impairment'), unit))}"
        f"+其他类型减值{_format_amount(Amount(summary.get('other_type_impairment'), unit))}"
        "（保证金、商票、票证等）。"
    )


def _build_financial_expense_text(expense: Dict[str, Any], month_label: str) -> str:
    if not expense:
        return f"{month_label}财务费用数据暂未提供。"

    unit = expense.get("unit", "元")
    return (
        f"{month_label}财务费用{_format_amount(Amount(expense.get('expense'), unit))}"
        f"=利息支出{_format_amount(Amount(expense.get('interest_expense'), unit))}"
        f"-利息收入{_format_amount(Amount(expense.get('interest_income'), unit))}，"
        f"其中利息支出{_format_amount(Amount(expense.get('interest_expense'), unit))}"
        f"=应收账款资金占用费{_format_amount(Amount(expense.get('receivable_funding_fee'), unit))}"
        f"+应收票据资金占用费{_format_amount(Amount(expense.get('note_funding_fee'), unit))}"
        f"+其他类型资金占用费{_format_amount(Amount(expense.get('other_type_funding_fee'), unit))}。"
    )


def _build_receivable_tree_section(root: Optional[ReceivableTreeNode]) -> str:
    if not root:
        return "应收款项总额：—\n\n当前数据未提供应收款项结构。"

    lines = [f"应收款项总额：{_format_amount(root.amount)}", "", "应收款项结构："]
    lines.extend(_receivable_tree_lines(root))
    return "\n".join(lines)


def _receivable_tree_lines(node: ReceivableTreeNode, depth: int = 0) -> List[str]:
    indent = "  " * depth
    lines = [f"{indent}- {node.name} {_format_amount(node.amount)}"]
    for child in node.children:
        lines.extend(_receivable_tree_lines(child, depth + 1))
    return lines


def _build_overdue_table(records: List[CustomerAmountRecord]) -> str:
    if not records:
        return "当前数据未提供逾期客户明细。"

    rows = [["客户名称", "应收账款", "其中：逾期账款"]]
    for record in records:
        rows.append(
            [
                record.customer_name,
                _format_amount(_extra_amount(record, "receivable_amount")),
                _format_amount(record.amount),
            ]
        )
    return _markdown_table(rows)


def _build_next_month_due_table(records: List[CustomerAmountRecord], next_month_label: str) -> str:
    if not records:
        return "当前数据未提供次月新增到期款客户明细。"

    rows = [["客户名称", f"{next_month_label}新增到期款"]]
    for record in records:
        rows.append([record.customer_name, _format_amount(record.amount)])
    return _markdown_table(rows)


def _build_impairment_top_table(records: List[CustomerAmountRecord], previous_month_label: str) -> str:
    if not records:
        return "当前数据未提供减值损失客户明细。"

    header = [
        "客户名称",
        f"截止{previous_month_label}应收金额",
        "当年增加减值损失",
        "其中：应收减值（含坏账）",
        "工抵房减值",
        "其他类型减值（保证金、商票、票证等）",
    ]
    rows = [header]
    for record in records:
        rows.append(
            [
                record.customer_name,
                _format_amount(_extra_amount(record, "receivable_amount")),
                _format_amount(record.amount),
                _format_amount(_extra_amount(record, "receivable_impairment")),
                _format_amount(_extra_amount(record, "offset_house_impairment")),
                _format_amount(_extra_amount(record, "other_type_impairment")),
            ]
        )
    return _markdown_table(rows)


def _build_aging_jump_table(records: List[CustomerAmountRecord]) -> str:
    if not records:
        return "当前数据未提供预计跳账龄客户明细。"

    rows = [
        [
            "账龄跳到",
            "净增加减值金",
            "1 年≤账龄＜2 年",
            "",
            "2 年≤账龄＜3 年",
            "",
            "账龄 ≥3 年",
            "",
        ],
        ["客户名称", "额", "应收金额", "减值损失", "应收金额", "减值损失", "应收金额", "减值损失"],
    ]
    for record in records:
        row = [
            record.customer_name,
            _format_amount(record.amount),
        ]
        for bucket in AGING_JUMP_BUCKETS:
            row.extend(
                [
                    _format_amount(_aging_bucket_amount(record, bucket, "receivable_amount")),
                    _format_amount(_aging_bucket_amount(record, bucket, "impairment_loss")),
                ]
            )
        rows.append(row)
    return _markdown_table(rows, header_rows=2)


def _build_financial_expense_top_sentence(records: List[CustomerAmountRecord], month_label: str) -> str:
    if not records:
        return f"{month_label}财务费用排名前三客户数据暂未提供。"

    customer_text = "、".join(
        f"{record.customer_name}（{_format_amount(record.amount)}）"
        for record in records
    )
    return f"{month_label}财务费用排名前三的客户为{customer_text}。"


def _build_financial_expense_table(records: List[CustomerAmountRecord]) -> str:
    if not records:
        return "当前数据未提供财务费用客户明细。"

    rows = [["客户名称", "财务费用"]]
    for record in records:
        rows.append([record.customer_name, _format_amount(record.amount)])
    return _markdown_table(rows)


def _extra_amount(record: CustomerAmountRecord, key: str) -> Amount:
    return Amount(_to_float(record.extra.get(key)), record.amount.unit)


def _aging_bucket_amount(record: CustomerAmountRecord, bucket: str, key: str) -> Amount:
    buckets = record.extra.get("aging_buckets")
    if not isinstance(buckets, dict):
        return Amount(None, record.amount.unit)
    bucket_data = buckets.get(bucket)
    if not isinstance(bucket_data, dict):
        return Amount(None, record.amount.unit)
    return Amount(_to_float(bucket_data.get(key)), record.amount.unit)


def _markdown_table(rows: List[List[str]], header_rows: int = 1) -> str:
    if not rows:
        return ""
    divider = ["---"] * len(rows[0])
    table_lines = ["| " + " | ".join(row) + " |" for row in rows[:header_rows]]
    table_lines.append("| " + " | ".join(divider) + " |")
    table_lines.extend("| " + " | ".join(row) + " |" for row in rows[header_rows:])
    return "\n".join(table_lines)


def _format_amount(amount: Amount) -> str:
    if amount.value is None:
        return "—"
    if amount.unit == "元":
        return f"{_format_decimal(amount.value, 0)}元"
    return f"{_format_decimal(amount.value, 1)}{amount.unit or '万元'}"


def _format_decimal(value: float, precision: int) -> str:
    quant = Decimal("1") if precision == 0 else Decimal("1").scaleb(-precision)
    rounded = Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)
    return f"{rounded:.{precision}f}"


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None
