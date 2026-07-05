"""统一报告月份标签。

`calmonth` 用于接口请求，`report_period` 用于正文展示。正文当前月、
累计区间、上月和次月都从 `report_period` 派生，避免各章节自行减月。
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, List, Optional, Tuple


@dataclass(frozen=True)
class ReportPeriodContext:
    period: str
    month: Optional[int]
    current_label: str
    ytd_label: str
    display_label: str
    previous_label: str
    next_label: str


def build_report_period_context(period: Any) -> ReportPeriodContext:
    text = str(period or "")
    month = _month_number(text)
    if month is None:
        return ReportPeriodContext(
            period=text,
            month=None,
            current_label="当月",
            ytd_label="累计",
            display_label=text,
            previous_label="报告月",
            next_label="次月",
        )

    previous_month = 12 if month == 1 else month - 1
    next_month = 1 if month == 12 else month + 1
    year = _year_number(text)
    return ReportPeriodContext(
        period=text,
        month=month,
        current_label=f"{month}月",
        ytd_label=f"1-{month}月累计",
        display_label=f"{year}年1-{month}月" if year is not None else f"1-{month}月",
        previous_label=f"{previous_month}月",
        next_label=f"{next_month}月",
    )


def current_and_ytd_labels(period: Any) -> Tuple[str, str]:
    context = build_report_period_context(period)
    return context.current_label, context.ytd_label


def current_and_next_labels(period: Any) -> Tuple[str, str]:
    context = build_report_period_context(period)
    return context.current_label, context.next_label


def previous_label(period: Any) -> str:
    return build_report_period_context(period).previous_label


def month_number(period: Any) -> Optional[int]:
    return build_report_period_context(period).month


def display_period_label(period: Any) -> str:
    return build_report_period_context(period).display_label


def default_report_period(calmonth: Any) -> str:
    """接口取数月默认展示上一个经营月。

    业务口径：例如接口参数 CALMONTH=202606 取到的是 6 月推送包，
    正文应分析截至 5 月的数据，展示为 2026年1-5月。
    """
    text = str(calmonth or "")
    match = re.fullmatch(r"(\d{4})(0[1-9]|1[0-2])", text)
    if not match:
        return text

    year = int(match.group(1))
    month = int(match.group(2))
    if month == 1:
        return f"{year - 1}12"
    return f"{year}{month - 1:02d}"


def audit_report_month_labels(markdown: str, period: Any) -> List[str]:
    """检查正文主口径是否使用了指定展示截止月。

    允许业务字段出现上月/次月，例如“截止4月应收金额”和“6月新增到期款”。
    这里只检查标题、利润、销量、过程指标、奖金预警等主报告期间标签。
    """
    context = build_report_period_context(period)
    if context.month is None:
        return []

    expected_period = str(period)
    expected_display_period = context.display_label
    expected_current = context.current_label
    expected_ytd = context.ytd_label
    previous_ytd = f"1-{context.previous_label.removesuffix('月')}月累计"
    issues: List[str] = []

    if re.search(r"^# .+经营分析报告\s*$", markdown, flags=re.MULTILINE):
        if (
            f"{expected_period}经营分析报告" not in markdown
            and f"{expected_display_period}经营分析报告" not in markdown
        ):
            issues.append(f"报告标题未使用展示截止月份 {expected_period}")

    main_period_checks = [
        ("| 科目 |", f"| 科目 | {expected_current} |", f"第二章利润表表头未使用展示月份 {expected_current}"),
        ("| 销量 |", f"| 销量 | {expected_current} |", f"第三章销量表头未使用展示月份 {expected_current}"),
        (
            "| 过程指标 | 目标与实际 |",
            f"| 过程指标 | 目标与实际 | {expected_current} |",
            f"第三章过程指标表头未使用展示月份 {expected_current}",
        ),
    ]
    for section_needle, expected_needle, message in main_period_checks:
        if section_needle in markdown and expected_needle not in markdown:
            issues.append(message)

    if _has_main_ytd_surface(markdown) and expected_ytd not in markdown:
        issues.append(f"正文主累计区间未使用展示累计 {expected_ytd}")

    expected_overdue = f"截止{expected_current}底逾期金额"
    if "月底逾期金额" in markdown and expected_overdue not in markdown:
        issues.append(f"第一章逾期金额未使用展示月份 {expected_current}")

    expected_profit = f"截止{expected_current}本年累计分摊前利润"
    if "本年累计分摊前利润" in markdown and expected_profit not in markdown:
        issues.append(f"第一章年终利润预警未使用展示月份 {expected_current}")

    checks = [
        (f"| 科目 | {context.previous_label} |", "第二章利润表表头误用上月"),
        (f"| 销量 | {context.previous_label} |", "第三章销量表头误用上月"),
        (f"| 过程指标 | 目标与实际 | {context.previous_label} |", "第三章过程指标表头误用上月"),
        (previous_ytd, "正文主累计区间误用上月累计"),
        (f"正向指标（1-{context.previous_label}", "第三章正向指标误用上月累计"),
        (f"风险指标（1-{context.previous_label}", "第三章风险指标误用上月累计"),
        (f"未达百（1-{context.previous_label}", "第三章未达百说明误用上月累计"),
        (f"负增长（1-{context.previous_label}", "第三章负增长说明误用上月累计"),
    ]
    issues.extend(message for needle, message in checks if needle in markdown)
    return _dedupe(issues)


def _has_main_ytd_surface(markdown: str) -> bool:
    return any(
        needle in markdown
        for needle in (
            "| 科目 |",
            "| 销量 |",
            "| 过程指标 | 目标与实际 |",
            "正向指标（1-",
            "风险指标（1-",
            "未达百（1-",
            "负增长（1-",
        )
    )


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _month_number(period: str) -> Optional[int]:
    if len(period) >= 6 and period[-2:].isdigit():
        month = int(period[-2:])
        if 1 <= month <= 12:
            return month
    return None


def _year_number(period: str) -> Optional[int]:
    if len(period) >= 4 and period[:4].isdigit():
        return int(period[:4])
    return None
