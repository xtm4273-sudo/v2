"""最终交付归一化测试。"""
from __future__ import annotations


def test_normalize_display_numbers_preserves_money_precision():
    from run_full_report_strict import normalize_display_numbers

    text = "\n".join(
        [
            "70万，预计奖金0.12万",
            "奖金基数为0.6。若到年底分摊前利润在60万-80万（含）之间，奖金基数为1.2。",
            "| 营业收入（不含税） | 13.9万元 | 43.3万元 | 128.9万元 |",
            "地坪漆14.07元/KG，聚合物水泥防水涂料3.76元/KG，同比↑0.12元/KG",
        ]
    )

    normalized = normalize_display_numbers(text)

    assert "预计奖金0.12万" in normalized
    assert "奖金基数为0.6" in normalized
    assert "奖金基数为1.2" in normalized
    assert "13.9万元" in normalized
    assert "3.76元/KG" in normalized
    assert "0.12元/KG" in normalized


def test_normalize_display_numbers_still_normalizes_counts_and_percentages():
    from run_full_report_strict import normalize_display_numbers

    text = "拜访总频次104.000次，项目26.000个，客户3.000家，达成173.333%。"

    normalized = normalize_display_numbers(text)

    assert "拜访总频次104次" in normalized
    assert "项目26个" in normalized
    assert "客户3家" in normalized
    assert "达成173.3%" in normalized


def test_delivery_display_replaces_visible_missing_values_with_zero():
    from ReportGenerator.display_policy import normalize_delivery_display

    text = "\n".join(
        [
            "5月费用<span style=\"color:#c00000;font-weight:700\">待补充</span>，同比待补充。",
            "| 指标 | 值 |",
            "| --- | --- |",
            "| 当前达成率 | 待补充 |",
            "缺少可比同期数据。",
        ]
    )

    normalized = normalize_delivery_display(text)

    assert "待补充" not in normalized
    assert "数据暂未提供" not in normalized
    assert "5月费用0，同比0。" in normalized
    assert "| 当前达成率 | 0 |" in normalized
    assert "0。" in normalized


def test_delivery_display_hides_missing_topn_sentences():
    from ReportGenerator.display_policy import normalize_delivery_display

    text = "\n".join(
        [
            "## 6.2 样板样漆费用",
            "",
            "5月费用163元，同比增加163元。其中费用排名前三的产品为待补充。",
            "",
            "◇ 5月财务费用排名前三客户数据暂未提供。",
            "",
            "| 客户名称 | 财务费用 |",
            "| --- | --- |",
            "| 待补充 | 待补充 |",
            "",
            "正常句子保留。",
        ]
    )

    normalized = normalize_delivery_display(text)

    assert "待补充" not in normalized
    assert "5月费用163元，同比增加163元。" in normalized
    assert "费用排名前三" not in normalized
    assert "财务费用排名前三" not in normalized
    assert "客户名称 | 财务费用" not in normalized
    assert "正常句子保留。" in normalized


def test_delivery_display_audit_records_cleanup_actions():
    from ReportGenerator.display_policy import build_delivery_display_audit, normalize_delivery_display

    text = "\n".join(
        [
            "当前达成率待补充。",
            "5月费用163元，同比增加163元。其中费用排名前三的产品为待补充。",
        ]
    )

    normalized = normalize_delivery_display(text)
    audit = build_delivery_display_audit(text, normalized)

    assert audit["status"] == "ok"
    assert audit["visible_missing_before"] == 2
    assert audit["visible_missing_after"] == 0
    assert audit["zero_replacements"] == 1
    assert audit["hidden_topn_or_detail"] == 1
    assert audit["actions"][0]["failure_type_label"] == "接口数据问题"


def test_delivery_display_removes_textual_interface_placeholders_without_zeroing_names():
    from ReportGenerator.display_policy import normalize_delivery_display

    normalized = normalize_delivery_display(
        "\n".join(
            [
                "经营部（接口未提供）区域经理2026年1-5月经营分析报告",
                "| 省区内排名 | 20/待补充 |",
            ]
        )
    )

    assert "经营部区域经理2026年1-5月经营分析报告" in normalized
    assert "经营部（0）" not in normalized
    assert "| 省区内排名 | 20/0 |" in normalized
