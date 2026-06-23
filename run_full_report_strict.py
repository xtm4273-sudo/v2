"""真实接口全部成功后，生成单人 1-8 章完整报告。"""
from __future__ import annotations

import argparse
import asyncio
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from Data.check_data import check_chapter_response
from Data.fetch_data import fetch_chapter_data_batch
from ReportGenerator.full_report_generator import CHAPTER_KEYWORDS, FullReportGenerator


def normalize_missing_labels(markdown: str) -> str:
    """严格交付口径：所有可见缺失数据统一标记为“待补充”。"""
    markdown = re.sub(r"<span\b[^>]*>(.*?)</span>", r"\1", markdown, flags=re.DOTALL)
    markdown = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
    markdown = re.sub(
        r"客户(\d+)（接口未提供名称）",
        r"客户名称待补充（客户\1）",
        markdown,
    )
    markdown = markdown.replace("当前数据未提供预计跳账龄客户明细。", "预计跳账龄客户明细：待补充。")
    markdown = markdown.replace("数据暂未提供", "数据待补充")
    markdown = markdown.replace("缺少可比同期数据", "可比同期数据待补充")
    markdown = markdown.replace("| — |", "| 待补充 |")
    return markdown


def normalize_display_numbers(markdown: str) -> str:
    """交付展示口径：金额取整数，百分比保留一位小数。"""
    def integer_money(match: re.Match[str]) -> str:
        value = Decimal(match.group(1).replace(",", ""))
        rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return f"{rounded}{match.group(2)}"

    def one_decimal_percent(match: re.Match[str]) -> str:
        value = Decimal(match.group(1).replace(",", ""))
        rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{rounded}%"

    markdown = re.sub(
        r"(?<![\d.])(-?\d+(?:,\d{3})*(?:\.\d+)?)(万元|万|元)",
        integer_money,
        markdown,
    )
    markdown = re.sub(
        r"(?<![\d.])(-?\d+(?:,\d{3})*(?:\.\d+)?)%",
        one_decimal_percent,
        markdown,
    )
    return markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="严格模式生成 1-8 章完整报告")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--calmonth", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--department", default="")
    parser.add_argument("--province", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--business-department", default="城市焕新事业部")
    parser.add_argument("--output-root", default="Reports/full_report_live_strict")
    parser.add_argument("--timeout", type=int, default=45)
    return parser


async def run(args: argparse.Namespace) -> None:
    requests = [
        {"job_id": args.job_id, "time": args.calmonth, "module": module}
        for module in range(1, 7)
    ]
    responses = await fetch_chapter_data_batch(
        requests,
        concurrent_limit=6,
        api_key=args.api_key,
        timeout=args.timeout,
    )

    failures = []
    for module in range(1, 7):
        response = responses.get(module, {})
        has_error, message = check_chapter_response(
            response,
            module=module,
            expected_chapter_keywords=CHAPTER_KEYWORDS[module],
            required_metric_data_keys=(),
        )
        if has_error or response.get("code") != 1:
            failures.append(f"module {module}: {message}; code={response.get('code')}")

    if failures:
        raise SystemExit("接口门禁失败，未生成报告：" + " | ".join(failures))

    person = {
        "calmonth": args.calmonth,
        "job_id": args.job_id,
        "sale_name": args.name,
        "sale_class": "",
        "city_operation_department": args.department,
        "province": args.province,
        "region": args.region,
        "business_department": args.business_department,
    }
    generator = FullReportGenerator(
        person_config=person,
        calmonth=args.calmonth,
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
    from ReportGenerator.full_report_renderer import save_full_html, save_full_pdf

    title = f"{args.name or args.job_id}{args.calmonth}经营分析报告"
    save_full_html(full_markdown, result.html_path, title=title)
    save_full_pdf(full_markdown, result.pdf_path, title=title)

    print(result.report_dir.resolve())
    print(result.pdf_path.resolve())
    print(result.diagnostics_path.resolve())


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
