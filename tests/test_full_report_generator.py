"""完整报告生成器数据源测试。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


@pytest.mark.asyncio
async def test_full_report_fetches_source_chapters_1_to_7(monkeypatch, tmp_path):
    import ReportGenerator.full_report_generator as module
    from ReportGenerator.full_report_generator import FullReportGenerator

    captured_modules = []

    async def fake_fetch_chapter_data_batch(requests, **_kwargs):
        captured_modules.extend(request["module"] for request in requests)
        return {
            request["module"]: {"code": 1, "data": {"章节名称": "", "章节数据": []}}
            for request in requests
        }

    monkeypatch.setattr(module, "fetch_chapter_data_batch", fake_fetch_chapter_data_batch)

    generator = FullReportGenerator(
        person_config={"job_id": "06427", "sale_name": "刘晨"},
        calmonth="202606",
        output_root=tmp_path,
    )

    await generator._fetch_raw_chapters()

    assert captured_modules == [1, 2, 3, 4, 5, 6, 7]


def test_full_report_opening_title_uses_display_period_label(tmp_path):
    from ReportGenerator.full_report_generator import FullReportGenerator

    generator = FullReportGenerator(
        person_config={
            "job_id": "06427",
            "sale_name": "刘晨",
            "city_operation_department": "杭州工业厂房经营部",
        },
        calmonth="202606",
        report_period="202605",
        output_root=tmp_path,
    )

    markdown = generator._merge_markdown({1: "# 一、绩效得分与预警\n\n正文"})

    assert markdown.splitlines()[0] == "# 杭州工业厂房经营部刘晨2026年1-5月经营分析报告"
    assert "202605经营分析报告" not in markdown.splitlines()[0]


def test_full_report_defaults_display_period_to_previous_month(tmp_path):
    from ReportGenerator.full_report_generator import FullReportGenerator

    generator = FullReportGenerator(
        person_config={
            "job_id": "06427",
            "sale_name": "刘晨",
            "city_operation_department": "杭州工业厂房经营部",
        },
        calmonth="202606",
        output_root=tmp_path,
    )

    markdown = generator._merge_markdown({1: "# 一、绩效得分与预警\n\n正文"})

    assert generator.report_period == "202605"
    assert markdown.splitlines()[0] == "# 杭州工业厂房经营部刘晨2026年1-5月经营分析报告"


def test_delivery_pdf_filename_uses_person_name_and_generation_date():
    from ReportGenerator.full_report_generator import delivery_pdf_filename

    assert delivery_pdf_filename("宁健民", datetime(2026, 6, 9, 8, 26)) == "宁健民_20260609.pdf"


def test_delivery_pdf_path_uses_customer_named_pdf(tmp_path):
    from ReportGenerator.full_report_generator import delivery_pdf_path

    pdf_path = delivery_pdf_path(tmp_path / "pdf", "宁健民", datetime(2026, 6, 9))

    assert pdf_path == tmp_path / "pdf" / "宁健民_20260609.pdf"


def test_cleanup_extra_pdfs_leaves_only_customer_named_pdf(tmp_path):
    from ReportGenerator.full_report_generator import cleanup_extra_pdfs, delivery_pdf_path

    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    keep_pdf = delivery_pdf_path(pdf_dir, "宁健民", datetime(2026, 6, 9))
    keep_pdf.write_bytes(b"%PDF-1.4\nfinal\n")
    (pdf_dir / "full_report.pdf").write_bytes(b"old")
    (pdf_dir / "chapter8.pdf").write_bytes(b"old")

    cleanup_extra_pdfs(pdf_dir, keep_pdf=keep_pdf)

    assert sorted(path.name for path in pdf_dir.glob("*.pdf")) == ["宁健民_20260609.pdf"]


def test_full_report_delivery_policy_sanitizes_chapter_files(tmp_path):
    from ReportGenerator.full_report_generator import FullReportGenerator

    generator = FullReportGenerator(
        person_config={"job_id": "06427", "sale_name": "刘晨"},
        calmonth="202606",
        output_root=tmp_path,
    )
    report_dir = tmp_path / "202606" / "06427_刘晨"
    (report_dir / "markdown").mkdir(parents=True)
    diagnostics = {}
    chapter_markdowns = {
        6: "\n".join(
            [
                "## 6.2 样板样漆费用",
                "",
                "5月费用163元，同比增加163元。其中费用排名前三的产品为待补充。",
                "",
            ]
        )
    }

    generator._apply_delivery_display_policy(chapter_markdowns, report_dir, diagnostics)

    chapter_text = (report_dir / "markdown" / "chapter6.md").read_text(encoding="utf-8")
    assert "待补充" not in chapter_text
    assert "5月费用163元，同比增加163元。" in chapter_text
    assert "费用排名前三" not in chapter_text
    assert diagnostics["delivery_display_policy"]["changed_modules"] == [6]
    assert diagnostics["delivery_display_policy"]["hidden_topn_or_detail"] == 1


def test_chapter8_product_strategy_uses_chapter3_risk_products():
    from ReportGenerator.full_report_generator import _chapter8_strategy_lines_with_chapter3_product_rule

    def row(name: str, path: str, actual: str, yoy: str) -> dict:
        return {
            "指标名称": name,
            "指标路径": path,
            "指标数据": {
                "实际值": actual,
                "同期数": yoy,
                "单位": "万",
                "日期类型": "年",
            },
        }

    chapter3_raw = {"data": {"章节数据": [
        row("真石漆", "三、销量分析-各产品销量-真石漆", "10", "30"),
        row("真石漆", "三、销量分析-各产品销售量-真石漆", "20", "60"),
    ]}}

    lines = _chapter8_strategy_lines_with_chapter3_product_rule(
        ["产品：AI生成的产品结构优化文案", "项目：推进项目落地"],
        chapter3_raw,
    )

    assert lines[0] == "产品：真石漆产品销量下滑，制定针对性推广或调整策略"
    assert "产品：AI生成的产品结构优化文案" not in lines
    assert "项目：推进项目落地" in lines


def test_chapter8_product_strategy_is_hidden_without_chapter3_risk_products():
    from ReportGenerator.full_report_generator import _chapter8_strategy_lines_with_chapter3_product_rule

    chapter3_raw = {"data": {"章节数据": [
        {
            "指标名称": "内墙乳胶漆面漆",
            "指标路径": "三、销量分析-各产品销量-内墙乳胶漆面漆",
            "指标数据": {"实际值": "28", "同期数": "14", "单位": "万", "日期类型": "年"},
        },
        {
            "指标名称": "内墙乳胶漆面漆",
            "指标路径": "三、销量分析-各产品销售量-内墙乳胶漆面漆",
            "指标数据": {"实际值": "30", "同期数": "15", "单位": "万", "日期类型": "年"},
        },
    ]}}

    lines = _chapter8_strategy_lines_with_chapter3_product_rule(
        ["产品：AI生成的产品结构优化文案", "项目：推进项目落地"],
        chapter3_raw,
    )

    assert lines == ["项目：推进项目落地"]


def test_failure_from_response_marks_api_errors_as_interface_problem():
    from ReportGenerator.full_report_generator import _failure_from_response

    failure = _failure_from_response(
        {
            "error": "timeout",
            "message": "Request timed out after 30s",
            "failure_type": "interface_error",
            "failure_stage": "fetch_chapter_api",
            "module": 3,
        },
        module=3,
        stage="validate_raw_chapter",
        raw_message="第3章接口请求失败: timeout - Request timed out after 30s",
    )

    assert failure["failure_type"] == "interface_error"
    assert failure["failure_type_label"] == "接口问题"
    assert failure["failure_stage"] == "validate_raw_chapter"
    assert failure["context"]["failure_stage_from_api"] == "fetch_chapter_api"


@pytest.mark.asyncio
async def test_full_report_writes_failure_diagnostics_when_fetch_raises(tmp_path):
    from ReportGenerator.full_report_generator import FullReportGenerator

    generator = FullReportGenerator(
        person_config={"job_id": "06427", "sale_name": "刘晨"},
        calmonth="202606",
        output_root=tmp_path,
    )

    async def boom():
        raise RuntimeError("fetch exploded")

    generator._fetch_raw_chapters = boom

    with pytest.raises(RuntimeError):
        await generator.run()

    diagnostics_path = tmp_path / "202606" / "06427_刘晨" / "diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))

    assert diagnostics["status"] == "raw_fetch_failed"
    assert diagnostics["failure_type"] == "program_error"
    assert diagnostics["failure_stage"] == "fetch_raw_chapters"
    assert diagnostics["failure_reason"] == "fetch exploded"
    assert "traceback" in diagnostics["failure"]
