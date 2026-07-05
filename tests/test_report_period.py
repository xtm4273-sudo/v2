"""报告月份统一口径测试。"""
from __future__ import annotations


def test_report_period_context_uses_report_month_directly():
    from ReportGenerator.report_period import build_report_period_context

    context = build_report_period_context("202605")

    assert context.current_label == "5月"
    assert context.ytd_label == "1-5月累计"
    assert context.display_label == "2026年1-5月"
    assert context.previous_label == "4月"
    assert context.next_label == "6月"


def test_default_report_period_is_previous_month_of_interface_calmonth():
    from ReportGenerator.report_period import default_report_period

    assert default_report_period("202606") == "202605"
    assert default_report_period("202601") == "202512"
    assert default_report_period("") == ""


def test_chapter2_and_chapter3_do_not_subtract_report_period_month():
    from ReportGenerator.chapter2_generator import _dimension_report_label
    from ReportGenerator.chapter3_generator import month_labels

    assert _dimension_report_label("月", "202605") == "5月"
    assert _dimension_report_label("年", "202605") == "1-5月累计"
    assert month_labels("202605") == ("5月", "1-5月累计")


def test_chapter5_keeps_next_month_business_label():
    from ReportGenerator.chapter5_generator import month_labels, previous_month

    assert month_labels("202605") == ("5月", "6月")
    assert previous_month("202605") == "4月"


def test_period_audit_allows_business_previous_and_next_month_but_blocks_main_labels():
    from ReportGenerator.report_period import audit_report_month_labels

    allowed = """
| 科目 | 5月 | 本季度累计 | 1-5月累计 |
| 销量 | 5月 | 本季度累计 | 1-5月累计 |
| 客户名称 | 截止4月应收金额 | 当年增加减值损失 |
◇ **6月新增到期款金额排名前五客户：**
"""
    assert audit_report_month_labels(allowed, "202605") == []

    bad = """
| 科目 | 4月 | 本季度累计 | 1-4月累计 |
| 销量 | 4月 | 本季度累计 | 1-4月累计 |
"""
    issues = audit_report_month_labels(bad, "202605")
    assert "第二章利润表表头误用上月" in issues
    assert "第三章销量表头误用上月" in issues


def test_period_audit_blocks_main_labels_after_expected_period():
    from ReportGenerator.report_period import audit_report_month_labels

    bad = """
# 杭州工业厂房经营部刘晨202606经营分析报告
| 科目 | 6月 | 本季度累计 | 1-6月累计 |
| 销量 | 6月 | 本季度累计 | 1-6月累计 |
| 发放规则（与逾期金额同比挂钩） | 截止6月底逾期金额 | 47万 |
◇ **6月新增到期款金额排名前五客户：**
"""

    issues = audit_report_month_labels(bad, "202605")

    assert "报告标题未使用展示截止月份 202605" in issues
    assert "第二章利润表表头未使用展示月份 5月" in issues
    assert "第三章销量表头未使用展示月份 5月" in issues
    assert "正文主累计区间未使用展示累计 1-5月累计" in issues
    assert "第一章逾期金额未使用展示月份 5月" in issues
    assert all("6月新增到期款" not in issue for issue in issues)


def test_strict_single_report_defaults_report_period_to_previous_month():
    from run_full_report_strict import build_parser

    parser = build_parser()
    args = parser.parse_args(["--job-id", "06427", "--calmonth", "202606", "--api-key", "test"])

    assert args.report_period == "202605"
