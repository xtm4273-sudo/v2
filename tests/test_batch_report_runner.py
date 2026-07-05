"""二期批量报告入口的控制逻辑测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def _write_complete_report(
    root: Path,
    calmonth: str = "202606",
    report_period: str = "202606",
    job_id: str = "06427",
    name: str = "刘晨",
) -> Path:
    report_dir = root / calmonth / f"{job_id}_{name}"
    for path in (
        report_dir / "raw",
        report_dir / "cleaned",
        report_dir / "markdown",
        report_dir / "html",
        report_dir / "pdf",
    ):
        path.mkdir(parents=True, exist_ok=True)

    (report_dir / "raw" / "all_raw_chapters.json").write_text("{}", encoding="utf-8")
    for module in range(1, 8):
        (report_dir / "raw" / f"module_{module}.json").write_text("{}", encoding="utf-8")
        (report_dir / "cleaned" / f"chapter{module}_cleaned.json").write_text("{}", encoding="utf-8")
    for module in range(1, 9):
        (report_dir / "markdown" / f"chapter{module}.md").write_text(f"chapter {module}", encoding="utf-8")
    (report_dir / "cleaned" / "chapter8_source.json").write_text("{}", encoding="utf-8")
    (report_dir / "cleaned" / "chapter8_derived.json").write_text("{}", encoding="utf-8")
    full_md = report_dir / "markdown" / "full_report.md"
    full_html = report_dir / "html" / "full_report.html"
    full_pdf = report_dir / "pdf" / f"{name}_20260630.pdf"
    full_md.write_text("full", encoding="utf-8")
    full_html.write_text("<html></html>", encoding="utf-8")
    full_pdf.write_bytes(b"%PDF-1.4\n")
    diagnostics = {
        "status": "completed",
        "calmonth": calmonth,
        "report_period": report_period,
        "period_audit": {"status": "ok", "report_period": report_period},
        "ai": {"status": "ok"},
        "outputs": {
            "markdown": str(full_md),
            "html": str(full_html),
            "pdf": str(full_pdf),
        },
    }
    (report_dir / "diagnostics.json").write_text(json.dumps(diagnostics), encoding="utf-8")
    return report_dir


def test_audit_report_dir_accepts_complete_report(tmp_path):
    import run_batch_report_test as module

    report_dir = _write_complete_report(tmp_path)

    audit = module.audit_report_dir(report_dir)

    assert audit["complete"] is True
    assert audit["issues"] == []
    assert audit["period_audit"] == "ok"
    assert audit["ai_status"] == "ok"


def test_audit_report_dir_reports_missing_pdf(tmp_path):
    import run_batch_report_test as module

    report_dir = _write_complete_report(tmp_path)
    (report_dir / "pdf" / "刘晨_20260630.pdf").unlink()

    audit = module.audit_report_dir(report_dir)

    assert audit["complete"] is False
    assert any("diagnostics.outputs.pdf missing on disk" in issue for issue in audit["issues"])


def test_audit_report_dir_rejects_extra_pdf_files(tmp_path):
    import run_batch_report_test as module

    report_dir = _write_complete_report(tmp_path)
    (report_dir / "pdf" / "full_report.pdf").write_bytes(b"old")

    audit = module.audit_report_dir(report_dir)

    assert audit["complete"] is False
    assert any("extra pdf files: full_report.pdf" in issue for issue in audit["issues"])


@pytest.mark.asyncio
async def test_audit_only_with_people_csv_does_not_call_employee_api(monkeypatch, tmp_path):
    import run_batch_report_test as module

    output_root = tmp_path / "reports"
    _write_complete_report(output_root)
    people_csv = tmp_path / "people.csv"
    people_csv.write_text("job_id,name\n06427,刘晨\n", encoding="utf-8")

    async def fail_employee_api(**_kwargs):
        raise AssertionError("audit-only with --people should not request employee API")

    monkeypatch.setattr(module, "fetch_employee_org_data", fail_employee_api)
    args = module.build_parser().parse_args([
        "--people", str(people_csv),
        "--calmonth", "202606",
        "--report-period", "202606",
        "--output-root", str(output_root),
        "--summary-root", str(tmp_path / "summary"),
        "--audit-only",
    ])

    await module.run(args)

    summary = json.loads((tmp_path / "summary" / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary[0]["status"] == "completed"
    assert summary[0]["complete"] is True
    manifest = json.loads((tmp_path / "summary" / "batch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"] == {"completed": 1}


def test_parser_defaults_are_local_safe():
    import run_batch_report_test as module

    args = module.build_parser().parse_args([
        "--calmonth", "202606",
    ])

    assert args.concurrent == 1
    assert args.chapter_concurrent == 6
    assert args.retries == 1
    assert args.offset == 0
    assert args.report_period == "202605"


def test_load_people_supports_offset_for_employee_configs():
    import run_batch_report_test as module

    args = module.build_parser().parse_args([
        "--calmonth", "202606",
        "--report-period", "202606",
        "--offset", "1",
        "--limit", "2",
    ])
    people = module._load_people(args, [
        {"job_id": "001", "sale_name": "一"},
        {"job_id": "002", "sale_name": "二"},
        {"job_id": "003", "sale_name": "三"},
        {"job_id": "004", "sale_name": "四"},
    ])

    assert [person.job_id for person in people] == ["002", "003"]


def test_load_people_csv_enriches_missing_org_fields_from_employee_configs(tmp_path):
    import run_batch_report_test as module

    people_csv = tmp_path / "people.csv"
    people_csv.write_text("job_id,name\n06427,刘晨\n", encoding="utf-8")
    args = module.build_parser().parse_args([
        "--people", str(people_csv),
        "--calmonth", "202606",
        "--report-period", "202605",
    ])

    people = module._load_people(args, [
        {
            "job_id": "06427",
            "sale_name": "接口姓名",
            "city_operation_department": "杭州工业厂房经营部",
            "province": "浙江省区",
            "region": "华东区域",
            "business_department": "城市焕新事业部",
        }
    ])

    assert people[0].sale_name == "刘晨"
    assert people[0].city_operation_department == "杭州工业厂房经营部"
    assert people[0].province == "浙江省区"
    assert people[0].region == "华东区域"


def test_resume_only_skips_complete_reports(tmp_path):
    import run_batch_report_test as module

    person = module.BatchPerson(job_id="06427", sale_name="刘晨")
    args = module.build_parser().parse_args([
        "--calmonth", "202606",
        "--report-period", "202606",
        "--output-root", str(tmp_path),
        "--resume",
    ])

    assert module._skip_result_if_complete(person, args) is None

    _write_complete_report(tmp_path)

    skipped = module._skip_result_if_complete(person, args)
    assert skipped is not None
    assert skipped["status"] == "skipped_completed"


def test_resume_does_not_skip_stale_report_period(tmp_path):
    import run_batch_report_test as module

    person = module.BatchPerson(job_id="06427", sale_name="刘晨")
    args = module.build_parser().parse_args([
        "--calmonth", "202606",
        "--report-period", "202605",
        "--output-root", str(tmp_path),
        "--resume",
    ])
    _write_complete_report(tmp_path, calmonth="202606", report_period="202606")

    skipped = module._skip_result_if_complete(person, args)

    assert skipped is None
    audit = module.audit_report_dir(
        tmp_path / "202606" / "06427_刘晨",
        expected_calmonth="202606",
        expected_report_period="202605",
    )
    assert audit["complete"] is False
    assert any("diagnostics.report_period=202606 expected 202605" in issue for issue in audit["issues"])


def test_summary_labels_raw_failed_as_data_interface_problem(tmp_path):
    import run_batch_report_test as module

    module._write_summary_files(
        tmp_path,
        [
            {
                "job_id": "80001195",
                "name": "马雨情",
                "status": "raw_failed",
                "message": "module 4: 第4章数据异常: 章节数据为空数组",
            }
        ],
    )

    summary = json.loads((tmp_path / "batch_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "batch_manifest.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "batch_summary.md").read_text(encoding="utf-8")

    assert summary[0]["problem_type"] == "数据接口/原始数据问题"
    assert manifest["problem_counts"] == {"数据接口/原始数据问题": 1}
    assert "数据接口/原始数据问题" in markdown


def test_problem_type_uses_detailed_failure_type():
    import run_batch_report_test as module

    assert module._problem_type({"status": "generate_failed", "failure_type": "program_error"}) == "程序异常"
    assert module._problem_type({"status": "generate_failed", "failure_type": "ai_error"}) == "AI接口/生成问题"
    assert module._problem_type({"status": "generate_failed", "failure_type": "render_error"}) == "HTML/PDF渲染问题"
    assert module._problem_type({"status": "raw_failed", "failure_type": "configuration_error"}) == "配置问题"
