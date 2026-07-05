"""第八章事实包派生测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURE_DIR = ROOT / "Reports" / "full_report_tests" / "202606" / "06427_刘晨" / "cleaned"


def _load_cleaned_chapters() -> dict[int, dict]:
    chapters: dict[int, dict] = {}
    for chapter in range(1, 7):
        path = FIXTURE_DIR / f"chapter{chapter}_cleaned.json"
        chapters[chapter] = json.loads(path.read_text(encoding="utf-8"))
    chapter7 = FIXTURE_DIR / "chapter7_cleaned.json"
    if not chapter7.exists():
        chapter7 = FIXTURE_DIR / "chapter7_derived.json"
    if chapter7.exists():
        chapters[7] = json.loads(chapter7.read_text(encoding="utf-8"))
    return chapters


def test_build_source_uses_project_customer_and_receivable_facts() -> None:
    from ReportGenerator.chapter8_source_builder import build_chapter8_source

    source = build_chapter8_source(
        _load_cleaned_chapters(),
        person_config={"job_id": "06427", "sale_name": "刘晨", "city_operation_department": "杭州工业厂房经营部"},
        calmonth="202606",
    )

    data = source["data"]
    dimensions = data["dimension_summary"]
    assert dimensions["项目"]["project_count"] == 26
    assert dimensions["项目"]["project_target"] == 100
    assert dimensions["渠道"]["channel_count"] == 1
    assert dimensions["渠道"]["channel_target"] == 2
    assert dimensions["客户"]["customer_count"] == 3
    assert dimensions["客户"]["customer_target"] == 20
    assert dimensions["应收"]["overdue_amount"] == 47.049
    assert dimensions["应收"]["impairment_amount"] == -27.885
    assert dimensions["应收"]["finance_cost"] == 3100.0
    assert dimensions["风控"]["overdue_amount"] == 47.049
    assert dimensions["风控"]["risk_level"] == "high"

    positive_names = {signal["metric_name"] for signal in data["positive_signals"]}
    negative_names = {signal["metric_name"] for signal in data["negative_signals"]}
    assert "月度有效项目落地" in positive_names
    assert "年度出货项目" in negative_names
    assert "存量生效客户" in negative_names
    assert "逾期应收" in negative_names
    assert any(fact["source_chapter"] == 2 and fact["metric_name"] == "营业收入（不含税）" for fact in data["facts"])
    assert any(fact["source_chapter"] == 7 and fact["metric_name"] == "拜访总频次" for fact in data["facts"])


def test_build_source_reads_chapter3_metric_name_from_path_when_name_is_empty() -> None:
    from ReportGenerator.chapter8_source_builder import build_chapter8_source

    def row(path: str, actual: str, target: float, rate: str, unit: str = "个") -> dict:
        return {
            "指标名称": "",
            "指标路径": path,
            "指标数据": {
                "实际值": actual,
                "目标值": target,
                "达成率": rate,
                "单位": unit,
                "日期类型": "年",
            },
        }

    source = build_chapter8_source(
        {
            3: {
                "rows": [
                    row("三、销量分析-100个出货项目-", "26.000", 100.0, "26.000"),
                    row("三、销量分析-招商生效客户-", "1.000", 2.0, "50.000", "家"),
                    row("三、销量分析-20个存量生效客户-", "3.000", 20.0, "15.000"),
                ]
            }
        },
        person_config={"job_id": "06427", "sale_name": "刘晨"},
        calmonth="202606",
    )

    dimensions = source["data"]["dimension_summary"]
    assert dimensions["项目"]["project_count"] == 26
    assert dimensions["项目"]["project_target"] == 100
    assert dimensions["渠道"]["channel_count"] == 1
    assert dimensions["渠道"]["channel_target"] == 2
    assert dimensions["客户"]["customer_count"] == 3
    assert dimensions["客户"]["customer_target"] == 20

    fact_names = {fact["metric_name"] for fact in source["data"]["facts"]}
    assert "年度出货项目" in fact_names
    assert "招商生效客户" in fact_names
    assert "存量生效客户" in fact_names


def test_build_source_keeps_units_and_traceable_sources() -> None:
    from ReportGenerator.chapter8_source_builder import build_chapter8_source

    data = build_chapter8_source(
        _load_cleaned_chapters(),
        person_config={"job_id": "06427"},
        calmonth="202606",
    )["data"]

    facts = data["facts"]
    overdue = next(fact for fact in facts if fact["metric_name"] == "逾期应收")
    assert overdue["unit"] == "万元"
    assert overdue["source_chapter"] == 5
    assert overdue["actual"] == 47.049

    sampling = data["dimension_summary"]["打样"]
    assert sampling["sample_expense"] == 119930.0
    assert sampling["yoy_direction"] == "new"


def test_sampling_strategy_uses_chapter6_same_period() -> None:
    from ReportGenerator.chapter8_generator import format_chapter8_data
    from ReportGenerator.chapter8_source_builder import build_chapter8_source

    source = build_chapter8_source(
        {
            6: {
                "sample_paint_expense": {
                    "total": {
                        "value": "4398.500",
                        "same_period": "4172.47",
                        "unit": "元",
                    }
                }
            }
        },
        person_config={"job_id": "06427"},
        calmonth="202606",
    )

    sampling = source["data"]["dimension_summary"]["打样"]
    markdown, _stats = format_chapter8_data(source, period="202606")

    assert sampling["yoy_direction"] == "up"
    assert "打样：费用4399元同比增加，需评估转化效率" in markdown
    assert "缺少可比同期数据" not in markdown


def test_sampling_strategy_treats_zero_same_period_as_available_data() -> None:
    from ReportGenerator.chapter8_generator import format_chapter8_data
    from ReportGenerator.chapter8_source_builder import build_chapter8_source

    source = build_chapter8_source(
        {
            6: {
                "sample_paint_expense": {
                    "total": {
                        "value": "81.000",
                        "same_period": "0.0",
                        "unit": "元",
                    }
                }
            }
        },
        person_config={"job_id": "107199"},
        calmonth="202606",
    )

    sampling = source["data"]["dimension_summary"]["打样"]
    markdown, _stats = format_chapter8_data(source, period="202606")

    assert sampling["yoy_direction"] == "new"
    assert "同期数据待补充" not in json.dumps(source, ensure_ascii=False)
    assert "缺少可比同期数据" not in markdown
    assert "打样：费用81元同比新增，需评估转化效率" in markdown


def test_derived_source_renders_complete_six_dimension_summary() -> None:
    from ReportGenerator.chapter8_generator import format_chapter8_data
    from ReportGenerator.chapter8_source_builder import build_chapter8_source

    source = build_chapter8_source(
        _load_cleaned_chapters(),
        person_config={"job_id": "06427", "sale_name": "刘晨"},
        calmonth="202606",
    )
    markdown, _stats = format_chapter8_data(source, period="202606")

    assert "分摊前利润45.0万元" in markdown
    assert "年度出货项目达成26%" in markdown
    assert "项目：年度出货项目26/100个" in markdown
    assert "渠道：招商生效客户1/2家" in markdown
    assert "客户：存量生效客户3/20个" in markdown
    assert "应收：逾期47.0万元" in markdown
    assert "资金费用3100元" in markdown
    assert "打样：费用119930元同比新增，需评估转化效率" in markdown
    assert "风控：逾期47.0万元客户按清收清单推进" in markdown
    assert "资金费用3100元压降赊销占用" in markdown
    assert "现款现货 + 超期客户法律催收" not in markdown
