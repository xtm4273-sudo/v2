"""批量生成多名区域经理 1-8 章完整报告。

这个入口同时服务本地验收和服务器部署：
- 本地用较低 --concurrent 检查大批量报告完整性；
- 服务器可按资源调高并发；
- 支持跳过已完成报告、失败重试和批量汇总。
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from Data.check_data import check_chapter_response
from Data.fetch_data import (
    add_ranking_population_totals,
    extract_employee_configs,
    fetch_chapter_data_batch,
    fetch_employee_org_data,
)
from ReportAI.settings import load_env_file
from ReportGenerator.full_report_generator import (
    CHAPTER_KEYWORDS,
    SOURCE_CHAPTERS,
    FullReportGenerator,
    _failure_from_exception,
    _failure_from_response,
    _failure_summary_fields,
    _failure_type_label,
    cleanup_extra_pdfs,
)
from ReportGenerator.report_period import default_report_period
from run_full_report_strict import normalize_display_numbers, normalize_missing_labels


@dataclass
class BatchPerson:
    job_id: str
    sale_name: str = ""
    city_operation_department: str = ""
    province: str = ""
    region: str = ""
    business_department: str = "城市焕新事业部"


class ReportPeriodArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if not parsed.report_period:
            parsed.report_period = default_report_period(parsed.calmonth)
        return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = ReportPeriodArgumentParser(description="批量生成 1-8 章完整报告")
    parser.add_argument("--people", default="", help="可选 CSV，字段 job_id,name/sale_name")
    parser.add_argument("--offset", type=int, default=0, help="跳过前 N 个人，用于分批生成不重复样本")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--calmonth", required=True)
    parser.add_argument(
        "--report-period",
        default="",
        help="报告展示截止月份 YYYYMM；默认按接口取数月的上一个月推导，例如 CALMONTH=202606 时展示 202605",
    )
    parser.add_argument("--api-key", default=None, help="接口 apikey；也可通过 SKSHU_BI_API_KEY 环境变量提供")
    parser.add_argument("--employee-org-api-url", default=None, help="人员名单接口 URL")
    parser.add_argument("--chapter-api-url", default=None, help="章节数据接口 URL")
    parser.add_argument("--output-root", default="Reports/full_report_live_strict")
    parser.add_argument("--summary-root", default="Reports/batch_report_runs")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--concurrent", type=int, default=1, help="同时生成多少份完整报告，本地建议 2-3")
    parser.add_argument("--chapter-concurrent", type=int, default=6, help="单份报告内章节接口并发数")
    parser.add_argument("--retries", type=int, default=1, help="失败后的重试次数")
    parser.add_argument("--retry-delay", type=float, default=2.0, help="失败重试前等待秒数")
    parser.add_argument("--resume", action="store_true", help="跳过已经完整生成的报告，继续未完成部分")
    parser.add_argument("--skip-completed", action="store_true", help="跳过输出目录中已完整的报告")
    parser.add_argument("--force", action="store_true", help="即使报告已完整也重新生成")
    parser.add_argument("--audit-only", action="store_true", help="只检查已有报告完整性，不请求接口、不生成报告")
    parser.add_argument("--verify-ssl", action="store_true", help="开启 SSL 证书校验")
    parser.add_argument("--sync-cache", action="store_true", help="同步成功报告到 output/period_adjusted_reports")
    return parser


async def run(args: argparse.Namespace) -> None:
    load_env_file(Path(__file__).resolve().parent / ".env")
    _validate_args(args)
    summary_dir = Path(args.summary_root)
    summary_dir.mkdir(parents=True, exist_ok=True)

    if args.audit_only and args.people:
        employee_configs: List[Dict[str, Any]] = []
    else:
        employee_response = await fetch_employee_org_data(
            api_key=args.api_key,
            api_url=args.employee_org_api_url,
            timeout=args.timeout,
            verify_ssl=args.verify_ssl,
        )
        if isinstance(employee_response, dict) and employee_response.get("error"):
            raise SystemExit(f"人员名单接口请求失败: {employee_response.get('error')} - {employee_response.get('message', '')}")
        employee_configs = extract_employee_configs(employee_response, calmonth=args.calmonth)

    people = _load_people(args, employee_configs)
    if not people:
        raise SystemExit("没有可生成的人员。请检查 --people、--limit 或人员名单接口。")

    results_by_job: Dict[str, Dict[str, Any]] = {}
    summary_lock = asyncio.Lock()

    async def record_result(person: BatchPerson, result: Dict[str, Any]) -> None:
        results_by_job[person.job_id] = result
        async with summary_lock:
            _write_summary_files(summary_dir, _ordered_results(people, results_by_job), args)

    if args.audit_only:
        for index, person in enumerate(people, 1):
            result = _completed_result_from_disk(person, args, status_if_complete="completed")
            print(f"[{index}/{len(people)}] {person.job_id} {person.sale_name or ''} -> {result['status']}", flush=True)
            await record_result(person, result)
        _write_summary_files(summary_dir, _ordered_results(people, results_by_job), args)
        _print_summary_paths(summary_dir)
        return

    semaphore = asyncio.Semaphore(args.concurrent)

    async def worker(index: int, person: BatchPerson) -> None:
        skipped = _skip_result_if_complete(person, args)
        if skipped:
            print(f"[{index}/{len(people)}] {person.job_id} {person.sale_name or ''} -> skipped", flush=True)
            await record_result(person, skipped)
            return

        async with semaphore:
            print(f"[{index}/{len(people)}] {person.job_id} {person.sale_name or ''}".strip(), flush=True)
            result = await _run_one_with_retries(person, args, employee_configs)
            print(f"  -> {result['status']}: {result.get('message', '')}", flush=True)
            await record_result(person, result)

    tasks = [asyncio.create_task(worker(index, person)) for index, person in enumerate(people, 1)]
    await asyncio.gather(*tasks)

    _write_summary_files(summary_dir, _ordered_results(people, results_by_job), args)
    _print_summary_paths(summary_dir)


def _validate_args(args: argparse.Namespace) -> None:
    if args.concurrent < 1:
        raise SystemExit("--concurrent 必须 >= 1")
    if args.chapter_concurrent < 1:
        raise SystemExit("--chapter-concurrent 必须 >= 1")
    if args.retries < 0:
        raise SystemExit("--retries 必须 >= 0")
    if args.offset < 0:
        raise SystemExit("--offset 必须 >= 0")
    if args.force and (args.resume or args.skip_completed or args.audit_only):
        raise SystemExit("--force 不能和 --resume/--skip-completed/--audit-only 同时使用")


async def _run_one_with_retries(
    person: BatchPerson,
    args: argparse.Namespace,
    employee_configs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    attempts = args.retries + 1
    last_result: Dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        last_result = await _run_one(person, args, employee_configs)
        last_result["attempts"] = attempt
        if last_result.get("status") == "completed":
            return last_result
        if attempt < attempts and args.retry_delay > 0:
            await asyncio.sleep(args.retry_delay)
    return last_result


async def _run_one(
    person: BatchPerson,
    args: argparse.Namespace,
    employee_configs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    requests = [
        {"job_id": person.job_id, "time": args.calmonth, "module": module}
        for module in SOURCE_CHAPTERS
    ]
    raw_responses = await fetch_chapter_data_batch(
        requests,
        concurrent_limit=args.chapter_concurrent,
        api_key=args.api_key,
        api_url=args.chapter_api_url,
        timeout=args.timeout,
        verify_ssl=args.verify_ssl,
    )

    failure_details = _validate_raw_response_details(raw_responses)
    if failure_details:
        failures = [
            f"module {detail.get('module')}: {detail.get('failure_reason')}; code={detail.get('api_code')}"
            for detail in failure_details
        ]
        diagnostics_path = _write_raw_failure_diagnostics(person, args, raw_responses, failure_details)
        failure = _aggregate_failure_details("validate_raw_responses", failure_details)
        return {
            "job_id": person.job_id,
            "name": person.sale_name,
            "status": "raw_failed",
            "message": "；".join(failures),
            "failures": failures,
            "failure_details": failure_details,
            "diagnostics": str(diagnostics_path.resolve()),
            **_failure_summary_fields(failure),
        }

    person_config = add_ranking_population_totals(person.__dict__, employee_configs)
    generator = FullReportGenerator(
        person_config=person_config,
        calmonth=args.calmonth,
        report_period=args.report_period,
        output_root=Path(args.output_root),
        timeout=args.timeout,
        verify_ssl=args.verify_ssl,
        chapter_concurrent_limit=args.chapter_concurrent,
        ai_required=True,
    )

    async def use_validated_responses() -> Dict[int, Dict[str, Any]]:
        return raw_responses

    generator._fetch_raw_chapters = use_validated_responses
    try:
        generated = await generator.run()
        _normalize_generated_outputs(generated, person, args.report_period)
        audit = audit_report_dir(
            generated.report_dir,
            require_ai=True,
            expected_calmonth=args.calmonth,
            expected_report_period=args.report_period,
        )
        if not audit["complete"]:
            return {
                "job_id": person.job_id,
                "name": person.sale_name,
                "status": "incomplete",
                "message": "；".join(audit["issues"]),
                "report_dir": str(generated.report_dir.resolve()),
                "pdf": str(generated.pdf_path.resolve()),
                "diagnostics": str(generated.diagnostics_path.resolve()),
                "period_audit": audit.get("period_audit"),
                "ai_status": audit.get("ai_status"),
                "complete": False,
                "missing": audit["issues"],
            }
        if args.sync_cache:
            _sync_cache(generated.report_dir, args.calmonth, person)
        diagnostics = generated.diagnostics
        ai = diagnostics.get("ai", {}) if isinstance(diagnostics, dict) else {}
        return {
            "job_id": person.job_id,
            "name": person.sale_name,
            "status": "completed",
            "message": "ok",
            "report_dir": str(generated.report_dir.resolve()),
            "pdf": str(generated.pdf_path.resolve()),
            "diagnostics": str(generated.diagnostics_path.resolve()),
            "period_audit": diagnostics.get("period_audit", {}).get("status"),
            "ai_status": ai.get("status"),
            "ai_validated": ai.get("validated"),
            "repair_calls": ai.get("repair_calls"),
            "complete": True,
        }
    except Exception as exc:
        diagnostics_path = generator._report_dir() / "diagnostics.json"
        failure = _load_failure_from_diagnostics(diagnostics_path) or _failure_from_exception(
            exc,
            "generate_report",
        )
        return {
            "job_id": person.job_id,
            "name": person.sale_name,
            "status": "generate_failed",
            "message": str(exc),
            "diagnostics": str(diagnostics_path.resolve()),
            **_failure_summary_fields(failure),
        }


def _validate_raw_responses(raw_responses: Dict[int, Dict[str, Any]]) -> List[str]:
    return [
        f"module {detail.get('module')}: {detail.get('failure_reason')}; code={detail.get('api_code')}"
        for detail in _validate_raw_response_details(raw_responses)
    ]


def _validate_raw_response_details(raw_responses: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for module in SOURCE_CHAPTERS:
        response = raw_responses.get(module, {})
        has_error, message = check_chapter_response(
            response,
            module=module,
            expected_chapter_keywords=CHAPTER_KEYWORDS[module],
            required_metric_data_keys=(),
        )
        if has_error or response.get("code") != 1:
            failure = _failure_from_response(
                response,
                module=module,
                stage="validate_raw_responses",
                raw_message=message,
            )
            detail = {
                "module": module,
                "api_code": response.get("code") if isinstance(response, dict) else None,
                **_failure_summary_fields(failure),
                "failure": failure,
            }
            details.append(detail)
    return details


def _write_raw_failure_diagnostics(
    person: BatchPerson,
    args: argparse.Namespace,
    raw_responses: Dict[int, Dict[str, Any]],
    failure_details: List[Dict[str, Any]],
) -> Path:
    report_dir = _person_report_dir(Path(args.output_root), args.calmonth, person)
    raw_dir = report_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "all_raw_chapters.json").write_text(
        json.dumps(raw_responses, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for module, response in raw_responses.items():
        (raw_dir / f"module_{module}.json").write_text(
            json.dumps(response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    failure = _aggregate_failure_details("validate_raw_responses", failure_details)
    diagnostics = {
        "person": person.__dict__,
        "calmonth": args.calmonth,
        "report_period": args.report_period,
        "status": "raw_failed",
        "chapters": {},
        "derived": {},
        "failure_details": failure_details,
        **_failure_summary_fields(failure),
        "failure": failure,
    }
    for detail in failure_details:
        module = str(detail.get("module", ""))
        diagnostics["chapters"][module] = {
            "status": "raw_error",
            **{key: value for key, value in detail.items() if key != "failure"},
            "failure": detail.get("failure"),
        }

    diagnostics_path = report_dir / "diagnostics.json"
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    return diagnostics_path


def _aggregate_failure_details(stage: str, failure_details: List[Dict[str, Any]]) -> Dict[str, Any]:
    failure_type = _dominant_failure_type(
        str(detail.get("failure_type") or "")
        for detail in failure_details
    )
    reasons = [
        f"module {detail.get('module')}: {detail.get('failure_reason')}"
        for detail in failure_details
    ]
    return {
        "failure_type": failure_type,
        "failure_type_label": _failure_type_label(failure_type),
        "failure_stage": stage,
        "failure_reason": "；".join(reasons),
        "message": "；".join(reasons),
        "failure_count": len(failure_details),
        "modules": [detail.get("module") for detail in failure_details],
    }


def _dominant_failure_type(failure_types: Any) -> str:
    values = [value for value in failure_types if value]
    for candidate in ("configuration_error", "interface_error", "data_error", "ai_error", "render_error", "period_error", "program_error"):
        if candidate in values:
            return candidate
    return values[0] if values else "unknown_error"


def _load_failure_from_diagnostics(diagnostics_path: Path) -> Dict[str, Any]:
    if not diagnostics_path.exists() or diagnostics_path.stat().st_size == 0:
        return {}
    try:
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    failure = diagnostics.get("failure") if isinstance(diagnostics, dict) else None
    return failure if isinstance(failure, dict) else {}


def _skip_result_if_complete(person: BatchPerson, args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    if args.force or not (args.resume or args.skip_completed):
        return None
    result = _completed_result_from_disk(person, args, status_if_complete="skipped_completed")
    if result.get("complete"):
        return result
    return None


def _completed_result_from_disk(
    person: BatchPerson,
    args: argparse.Namespace,
    status_if_complete: str,
) -> Dict[str, Any]:
    report_dir = _person_report_dir(Path(args.output_root), args.calmonth, person)
    audit = audit_report_dir(
        report_dir,
        require_ai=True,
        expected_calmonth=args.calmonth,
        expected_report_period=args.report_period,
    )
    result = {
        "job_id": person.job_id,
        "name": person.sale_name,
        "status": status_if_complete if audit["complete"] else "incomplete",
        "message": "ok" if audit["complete"] else "；".join(audit["issues"]),
        "report_dir": str(report_dir.resolve()),
        "pdf": audit.get("pdf") or "",
        "diagnostics": str((report_dir / "diagnostics.json").resolve()),
        "period_audit": audit.get("period_audit"),
        "ai_status": audit.get("ai_status"),
        "complete": audit["complete"],
    }
    if not audit["complete"]:
        result["missing"] = audit["issues"]
    return result


def audit_report_dir(
    report_dir: Path,
    require_ai: bool = True,
    expected_calmonth: Optional[str] = None,
    expected_report_period: Optional[str] = None,
) -> Dict[str, Any]:
    report_dir = Path(report_dir)
    issues: List[str] = []
    required_files = [
        report_dir / "raw" / "all_raw_chapters.json",
        report_dir / "markdown" / "full_report.md",
        report_dir / "html" / "full_report.html",
        report_dir / "diagnostics.json",
    ]
    required_files.extend(report_dir / "raw" / f"module_{module}.json" for module in SOURCE_CHAPTERS)
    required_files.extend(report_dir / "markdown" / f"chapter{module}.md" for module in range(1, 9))
    required_files.extend(report_dir / "cleaned" / f"chapter{module}_cleaned.json" for module in SOURCE_CHAPTERS)
    required_files.extend([
        report_dir / "cleaned" / "chapter8_source.json",
        report_dir / "cleaned" / "chapter8_derived.json",
    ])

    for path in required_files:
        if not path.exists():
            issues.append(f"missing {path.relative_to(report_dir)}")
        elif path.is_file() and path.stat().st_size == 0:
            issues.append(f"empty {path.relative_to(report_dir)}")

    diagnostics: Dict[str, Any] = {}
    diagnostics_path = report_dir / "diagnostics.json"
    if diagnostics_path.exists() and diagnostics_path.stat().st_size > 0:
        try:
            diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"invalid diagnostics.json: {exc}")

    status = diagnostics.get("status") if isinstance(diagnostics, dict) else None
    period_audit = diagnostics.get("period_audit", {}) if isinstance(diagnostics, dict) else {}
    ai = diagnostics.get("ai", {}) if isinstance(diagnostics, dict) else {}
    if status != "completed":
        issues.append(f"diagnostics.status={status or 'missing'}")
    if expected_calmonth is not None and diagnostics.get("calmonth") != expected_calmonth:
        issues.append(
            f"diagnostics.calmonth={diagnostics.get('calmonth') or 'missing'} expected {expected_calmonth}"
        )
    if expected_report_period is not None and diagnostics.get("report_period") != expected_report_period:
        issues.append(
            f"diagnostics.report_period={diagnostics.get('report_period') or 'missing'} expected {expected_report_period}"
        )
    if period_audit.get("status") != "ok":
        issues.append(f"period_audit={period_audit.get('status') or 'missing'}")
    if expected_report_period is not None and period_audit.get("report_period") != expected_report_period:
        issues.append(
            f"period_audit.report_period={period_audit.get('report_period') or 'missing'} expected {expected_report_period}"
        )
    if require_ai and ai.get("status") != "ok":
        issues.append(f"ai.status={ai.get('status') or 'missing'}")

    outputs = diagnostics.get("outputs", {}) if isinstance(diagnostics, dict) else {}
    output_pdf_path: Optional[Path] = None
    for key in ("markdown", "html", "pdf"):
        output_path = outputs.get(key)
        if output_path and not Path(output_path).exists():
            issues.append(f"diagnostics.outputs.{key} missing on disk")
        if key == "pdf" and output_path:
            output_pdf_path = Path(output_path)

    if output_pdf_path is None:
        issues.append("diagnostics.outputs.pdf missing")
    else:
        if output_pdf_path.exists() and not _is_delivery_pdf_name(output_pdf_path):
            issues.append(f"pdf filename must be 姓名_YYYYMMDD.pdf: {output_pdf_path.name}")
        pdf_files = sorted((report_dir / "pdf").glob("*.pdf"))
        extra_pdfs = [
            path for path in pdf_files
            if not output_pdf_path.exists() or path.resolve() != output_pdf_path.resolve()
        ]
        if extra_pdfs:
            names = ", ".join(path.name for path in extra_pdfs)
            issues.append(f"extra pdf files: {names}")

    return {
        "complete": not issues,
        "issues": issues,
        "status": status,
        "period_audit": period_audit.get("status"),
        "ai_status": ai.get("status"),
        "pdf": str(output_pdf_path.resolve()) if output_pdf_path else "",
    }


def _is_delivery_pdf_name(path: Path) -> bool:
    stem = Path(path).stem
    name, separator, date_text = stem.rpartition("_")
    return (
        Path(path).suffix.lower() == ".pdf"
        and bool(name)
        and separator == "_"
        and len(date_text) == 8
        and date_text.isdigit()
    )


def _normalize_generated_outputs(generated: Any, person: BatchPerson, report_period: str) -> None:
    changed = False
    markdown_dir = generated.report_dir / "markdown"
    for markdown_path in markdown_dir.glob("*.md"):
        original = markdown_path.read_text(encoding="utf-8")
        normalized = normalize_display_numbers(normalize_missing_labels(original))
        if normalized != original:
            markdown_path.write_text(normalized, encoding="utf-8")
            changed = True

    full_markdown = generated.markdown_path.read_text(encoding="utf-8")
    normalized_full = normalize_display_numbers(normalize_missing_labels(full_markdown))
    if normalized_full != full_markdown:
        generated.markdown_path.write_text(normalized_full, encoding="utf-8")
        full_markdown = normalized_full
        changed = True

    if not changed:
        return

    from ReportGenerator.full_report_renderer import save_full_html, save_full_pdf
    from ReportGenerator.report_period import display_period_label

    title = f"{person.sale_name or person.job_id}{display_period_label(report_period)}经营分析报告"
    save_full_html(full_markdown, generated.html_path, title=title)
    save_full_pdf(full_markdown, generated.pdf_path, title=title)
    cleanup_extra_pdfs(generated.pdf_path.parent, keep_pdf=generated.pdf_path)


def _sync_cache(report_dir: Path, calmonth: str, person: BatchPerson) -> None:
    dst = Path("output/period_adjusted_reports") / calmonth / f"{person.job_id}_{person.sale_name or 'unknown'}"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(report_dir, dst)


def _person_report_dir(output_root: Path, calmonth: str, person: BatchPerson) -> Path:
    safe_name = person.sale_name or "unknown"
    return output_root / calmonth / f"{person.job_id}_{safe_name}"


def _load_people(args: argparse.Namespace, employee_configs: List[Dict[str, Any]]) -> List[BatchPerson]:
    if args.people:
        return _enrich_people_from_employee_configs(
            _load_people_csv(Path(args.people), args.offset, args.limit),
            employee_configs,
        )
    selected = employee_configs[args.offset : args.offset + args.limit]
    return [
        BatchPerson(
            job_id=str(item.get("job_id") or ""),
            sale_name=str(item.get("sale_name") or ""),
            city_operation_department=str(item.get("city_operation_department") or ""),
            province=str(item.get("province") or ""),
            region=str(item.get("region") or ""),
            business_department=str(item.get("business_department") or "城市焕新事业部"),
        )
        for item in selected
        if item.get("job_id")
    ]


def _enrich_people_from_employee_configs(
    people: List[BatchPerson],
    employee_configs: List[Dict[str, Any]],
) -> List[BatchPerson]:
    by_job_id = {
        str(config.get("job_id") or ""): config
        for config in employee_configs
        if config.get("job_id")
    }
    enriched: List[BatchPerson] = []
    for person in people:
        config = by_job_id.get(str(person.job_id))
        if not config:
            enriched.append(person)
            continue
        enriched.append(
            BatchPerson(
                job_id=person.job_id,
                sale_name=person.sale_name or str(config.get("sale_name") or ""),
                city_operation_department=person.city_operation_department or str(config.get("city_operation_department") or ""),
                province=person.province or str(config.get("province") or ""),
                region=person.region or str(config.get("region") or ""),
                business_department=person.business_department or str(config.get("business_department") or "城市焕新事业部"),
            )
        )
    return enriched


def _load_people_csv(path: Path, offset: int, limit: int) -> List[BatchPerson]:
    rows: List[BatchPerson] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row_index, row in enumerate(csv.DictReader(handle)):
            if row_index < offset:
                continue
            job_id = str(row.get("job_id") or row.get("工号") or "").strip()
            if not job_id:
                continue
            rows.append(
                BatchPerson(
                    job_id=job_id,
                    sale_name=str(row.get("name") or row.get("sale_name") or row.get("姓名") or "").strip(),
                    city_operation_department=str(row.get("city_operation_department") or row.get("经营部") or "").strip(),
                    province=str(row.get("province") or row.get("省区") or "").strip(),
                    region=str(row.get("region") or row.get("区域") or "").strip(),
                    business_department=str(row.get("business_department") or row.get("事业部") or "城市焕新事业部").strip(),
                )
            )
            if len(rows) >= limit:
                break
    return rows


def _write_summary_files(
    summary_dir: Path,
    results: List[Dict[str, Any]],
    args: Optional[argparse.Namespace] = None,
) -> None:
    enriched_results = []
    for item in results:
        enriched = dict(item)
        enriched["problem_type"] = _problem_type(enriched)
        enriched_results.append(enriched)

    (summary_dir / "batch_summary.json").write_text(
        json.dumps(enriched_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts: Dict[str, int] = {}
    problem_counts: Dict[str, int] = {}
    for item in enriched_results:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
        problem_type = str(item.get("problem_type", ""))
        if problem_type and problem_type != "无":
            problem_counts[problem_type] = problem_counts.get(problem_type, 0) + 1

    manifest = {
        "total": len(enriched_results),
        "counts": counts,
        "problem_counts": problem_counts,
    }
    (summary_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# 批量报告生成汇总",
        "",
        f"- 总数：{len(enriched_results)}",
        f"- 完成：{counts.get('completed', 0)}",
        f"- 跳过已完成：{counts.get('skipped_completed', 0)}",
        f"- 不完整：{counts.get('incomplete', 0)}",
        f"- 原始数据失败：{counts.get('raw_failed', 0)}",
        f"- 生成失败：{counts.get('generate_failed', 0)}",
        f"- 数据接口/原始数据问题：{problem_counts.get('数据接口/原始数据问题', 0)}",
        f"- 配置问题：{problem_counts.get('配置问题', 0)}",
        f"- AI接口/生成问题：{problem_counts.get('AI接口/生成问题', 0)}",
        f"- HTML/PDF渲染问题：{problem_counts.get('HTML/PDF渲染问题', 0)}",
        f"- 报告月份/规则审计问题：{problem_counts.get('报告月份/规则审计问题', 0)}",
        f"- 程序异常：{problem_counts.get('程序异常', 0)}",
        f"- 报告产物不完整：{problem_counts.get('报告产物不完整', 0)}",
        "",
        "| 工号 | 姓名 | 状态 | 问题类型 | 失败阶段 | 完整 | AI | 月份审计 | 尝试 | PDF | 问题 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in enriched_results:
        pdf = item.get("pdf") or ""
        pdf_text = f"[PDF]({pdf})" if pdf else "未生成"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("job_id", "")),
                    str(item.get("name", "")),
                    str(item.get("status", "")),
                    str(item.get("problem_type", "")),
                    str(item.get("failure_stage", "")),
                    "是" if item.get("complete") else "否",
                    str(item.get("ai_status", "")),
                    str(item.get("period_audit", "")),
                    str(item.get("attempts", "")),
                    pdf_text,
                    _escape_markdown_cell(str(item.get("message", ""))),
                ]
            )
            + " |"
        )
    (summary_dir / "batch_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ordered_results(people: List[BatchPerson], results_by_job: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [results_by_job[person.job_id] for person in people if person.job_id in results_by_job]


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _problem_type(item: Dict[str, Any]) -> str:
    failure_type = str(item.get("failure_type") or "")
    if failure_type == "configuration_error":
        return "配置问题"
    if failure_type in {"interface_error", "data_error"}:
        return "数据接口/原始数据问题"
    if failure_type == "ai_error":
        return "AI接口/生成问题"
    if failure_type == "render_error":
        return "HTML/PDF渲染问题"
    if failure_type == "period_error":
        return "报告月份/规则审计问题"
    if failure_type == "program_error":
        return "程序异常"
    status = str(item.get("status") or "")
    if status == "raw_failed":
        return "数据接口/原始数据问题"
    if status == "generate_failed":
        return "程序异常"
    if status == "incomplete":
        return "报告产物不完整"
    return "无"


def _print_summary_paths(summary_dir: Path) -> None:
    print(str((summary_dir / "batch_summary.md").resolve()))
    print(str((summary_dir / "batch_summary.json").resolve()))
    print(str((summary_dir / "batch_manifest.json").resolve()))


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
