"""真实接口全部成功后，生成单人 1-8 章完整报告。"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List

from Data.check_data import check_chapter_response
from Data.fetch_data import (
    add_ranking_population_totals,
    extract_employee_configs,
    fetch_chapter_data_batch,
    fetch_employee_org_data,
)
from ReportGenerator.full_report_generator import (
    CHAPTER_KEYWORDS,
    SOURCE_CHAPTERS,
    FullReportGenerator,
    _failure_from_response,
    _failure_summary_fields,
    _failure_type_label,
    cleanup_extra_pdfs,
)
from ReportGenerator.report_period import default_report_period
from ReportGenerator.display_policy import normalize_delivery_display
from ReportAI.settings import load_env_file


EMPTY_FALLBACK_MODULES = {2, 4}


class ReportPeriodArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if not parsed.report_period:
            parsed.report_period = default_report_period(parsed.calmonth)
        return parsed


def normalize_missing_labels(markdown: str) -> str:
    """交付口径：客户报告不展示“待补充”，缺失数值展示为 0，空明细隐藏。"""
    return normalize_delivery_display(markdown)


def allows_empty_fallback(module: int, response: dict, message: str) -> bool:
    """第二、第四章空数组由章节生成器按0兜底，不作为严格门禁失败。"""
    return (
        module in EMPTY_FALLBACK_MODULES
        and response.get("code") == 1
        and "章节数据为空数组" in message
    )


def _preliminary_person(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "calmonth": args.calmonth,
        "job_id": args.job_id,
        "sale_name": args.name,
        "sale_class": "",
        "city_operation_department": args.department,
        "province": args.province,
        "region": args.region,
        "business_department": args.business_department,
    }


def _raw_failure_details(raw_responses: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for module in SOURCE_CHAPTERS:
        response = raw_responses.get(module, {})
        has_error, message = check_chapter_response(
            response,
            module=module,
            expected_chapter_keywords=CHAPTER_KEYWORDS[module],
            required_metric_data_keys=(),
        )
        if (has_error and not allows_empty_fallback(module, response, message)) or response.get("code") != 1:
            failure = _failure_from_response(
                response,
                module=module,
                stage="strict_raw_gate",
                raw_message=message,
            )
            details.append({
                "module": module,
                "api_code": response.get("code") if isinstance(response, dict) else None,
                **_failure_summary_fields(failure),
                "failure": failure,
            })
    return details


def _dominant_failure_type(details: List[Dict[str, Any]]) -> str:
    values = [str(detail.get("failure_type") or "") for detail in details]
    for candidate in ("configuration_error", "interface_error", "data_error", "program_error"):
        if candidate in values:
            return candidate
    return values[0] if values else "unknown_error"


def _write_raw_gate_failure_diagnostics(
    args: argparse.Namespace,
    raw_responses: Dict[int, Dict[str, Any]],
    failure_details: List[Dict[str, Any]],
) -> Path:
    person = _preliminary_person(args)
    safe_name = person.get("sale_name") or "unknown"
    report_dir = Path(args.output_root) / args.calmonth / f"{args.job_id}_{safe_name}"
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

    failure_type = _dominant_failure_type(failure_details)
    reason = "；".join(
        f"module {detail.get('module')}: {detail.get('failure_reason')}"
        for detail in failure_details
    )
    failure = {
        "failure_type": failure_type,
        "failure_type_label": _failure_type_label(failure_type),
        "failure_stage": "strict_raw_gate",
        "failure_reason": reason,
        "message": reason,
        "failure_count": len(failure_details),
        "modules": [detail.get("module") for detail in failure_details],
    }
    diagnostics = {
        "person": person,
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
        diagnostics["chapters"][str(detail.get("module"))] = {
            "status": "raw_error",
            **{key: value for key, value in detail.items() if key != "failure"},
            "failure": detail.get("failure"),
        }
    diagnostics_path = report_dir / "diagnostics.json"
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    return diagnostics_path


def normalize_display_numbers(markdown: str) -> str:
    """交付展示口径：只统一计数和百分比，不改写金额/单价精度。

    金额字段在各章节内有不同业务精度：奖金可能是 0.12 万，利润表保留
    1 位小数，产品单价保留 2 位小数。全局正则不能把这些统一取整。
    """
    def integer_count(match: re.Match[str]) -> str:
        value = Decimal(match.group(1).replace(",", ""))
        rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return f"{rounded}{match.group(2)}"

    def one_decimal_percent(match: re.Match[str]) -> str:
        value = Decimal(match.group(1).replace(",", ""))
        rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if rounded == rounded.quantize(Decimal("1")):
            return f"{rounded.quantize(Decimal('1'))}%"
        return f"{rounded}%"

    markdown = re.sub(
        r"(?<![\d.])(-?\d+(?:,\d{3})*(?:\.\d+)?)(个|家|人|项|次)",
        integer_count,
        markdown,
    )
    markdown = re.sub(
        r"(?<![\d.])(-?\d+(?:,\d{3})*(?:\.\d+)?)%",
        one_decimal_percent,
        markdown,
    )
    return markdown


def build_parser() -> argparse.ArgumentParser:
    parser = ReportPeriodArgumentParser(description="严格模式生成 1-8 章完整报告")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--calmonth", required=True)
    parser.add_argument(
        "--report-period",
        default="",
        help="报告展示截止月份 YYYYMM；默认按接口取数月的上一个月推导，例如 CALMONTH=202606 时展示 202605",
    )
    parser.add_argument("--api-key", default=None, help="接口 apikey；也可通过 SKSHU_BI_API_KEY 环境变量或 .env 提供")
    parser.add_argument("--name", default="")
    parser.add_argument("--department", default="")
    parser.add_argument("--province", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--business-department", default="城市焕新事业部")
    parser.add_argument("--output-root", default="Reports/full_report_live_strict")
    parser.add_argument("--timeout", type=int, default=45)
    return parser


async def run(args: argparse.Namespace) -> None:
    load_env_file(Path(__file__).resolve().parent / ".env")
    requests = [
        {"job_id": args.job_id, "time": args.calmonth, "module": module}
        for module in SOURCE_CHAPTERS
    ]
    responses = await fetch_chapter_data_batch(
        requests,
        concurrent_limit=6,
        api_key=args.api_key,
        timeout=args.timeout,
    )

    failure_details = _raw_failure_details(responses)
    if failure_details:
        diagnostics_path = _write_raw_gate_failure_diagnostics(args, responses, failure_details)
        failures = [
            f"module {detail.get('module')}: {detail.get('failure_reason')}; code={detail.get('api_code')}"
            for detail in failure_details
        ]
        raise SystemExit(
            "接口门禁失败，未生成报告："
            + " | ".join(failures)
            + f" | 诊断日志：{diagnostics_path.resolve()}"
        )

    person = _preliminary_person(args)
    employee_org_response = await fetch_employee_org_data(
        api_key=args.api_key,
        timeout=args.timeout,
    )
    employee_configs = extract_employee_configs(employee_org_response, calmonth=args.calmonth)
    matching_person = next(
        (config for config in employee_configs if config.get("job_id") == args.job_id),
        None,
    )
    if matching_person:
        for key in (
            "sale_name", "city_operation_department", "province", "region", "business_department"
        ):
            if not person.get(key):
                person[key] = matching_person.get(key, "")
    person = add_ranking_population_totals(person, employee_configs)
    generator = FullReportGenerator(
        person_config=person,
        calmonth=args.calmonth,
        report_period=args.report_period,
        output_root=Path(args.output_root),
        timeout=args.timeout,
    )

    async def use_validated_responses():
        return responses

    generator._fetch_raw_chapters = use_validated_responses
    result = await generator.run()

    markdown_dir = result.report_dir / "markdown"
    for markdown_path in markdown_dir.glob("*.md"):
        original = markdown_path.read_text(encoding="utf-8")
        normalized = normalize_display_numbers(normalize_missing_labels(original))
        if normalized != original:
            markdown_path.write_text(normalized, encoding="utf-8")

    full_markdown = result.markdown_path.read_text(encoding="utf-8")
    normalized_full = normalize_display_numbers(normalize_missing_labels(full_markdown))
    if normalized_full != full_markdown:
        result.markdown_path.write_text(normalized_full, encoding="utf-8")
        full_markdown = normalized_full
    from ReportGenerator.full_report_renderer import save_full_html, save_full_pdf
    from ReportGenerator.report_period import display_period_label

    title_name = person.get("sale_name") or args.name or args.job_id
    title = f"{title_name}{display_period_label(args.report_period)}经营分析报告"
    save_full_html(full_markdown, result.html_path, title=title)
    save_full_pdf(full_markdown, result.pdf_path, title=title)
    cleanup_extra_pdfs(result.pdf_path.parent, keep_pdf=result.pdf_path)

    print(result.report_dir.resolve())
    print(result.pdf_path.resolve())
    print(result.diagnostics_path.resolve())


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
