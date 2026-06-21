"""Run chapter 3 with real API data.

Example:
    python run_chapter3_api.py --job-id 86002542 --calmonth 202606 --api-key xxx
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from Data import ChapterDataError, check_chapter_response, fetch_chapter_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="拉取二期第三章接口数据并输出 Markdown/HTML/PDF")
    parser.add_argument("--job-id", required=True, help="区域经理工号，例如 86002542")
    parser.add_argument("--calmonth", required=True, help="月份，例如 202606")
    parser.add_argument("--api-key", default=None, help="接口 apikey；也可通过 SKSHU_BI_API_KEY 环境变量提供")
    parser.add_argument(
        "--api-url",
        default=None,
        help="接口 URL；默认使用 SKSHU_EMPLOYEE_INDEX_CCQ_API_URL 或开发环境 getEmployeeIndexAiCcq",
    )
    parser.add_argument("--output", default=None, help="输出目录；默认 Reports/chapter3_api_{job_id}_{calmonth}")
    parser.add_argument("--timeout", type=int, default=30, help="接口超时秒数，默认 30")
    parser.add_argument("--verify-ssl", action="store_true", help="开启 SSL 证书校验；生产环境建议开启")
    parser.add_argument("--raw-input", default=None, help="已保存的真实 MOUDLE=3 响应 JSON；提供时不再请求接口")
    parser.add_argument(
        "--use-ai-action-guide",
        action="store_true",
        help="预留开关：行动指南走 AI Writer 接口；未配置模型时自动回退规则文案",
    )
    return parser


def save_json(path: Path, data: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def run(args: argparse.Namespace) -> None:
    output_dir = (
        Path(args.output)
        if args.output
        else BASE_DIR / "Reports" / f"chapter3_api_{args.job_id}_{args.calmonth}"
    )
    raw_path = output_dir / "raw" / f"employee_{args.job_id}_month_{args.calmonth}_module_3.json"

    if args.raw_input:
        response = json.loads(Path(args.raw_input).read_text(encoding="utf-8"))
    else:
        response = await fetch_chapter_data(
            job_id=args.job_id,
            time=args.calmonth,
            module=3,
            api_key=args.api_key,
            api_url=args.api_url,
            timeout=args.timeout,
            verify_ssl=args.verify_ssl,
        )
    save_json(raw_path, response)

    has_error, message = check_chapter_response(
        response,
        module=3,
        expected_chapter_keywords=("销量分析",),
        required_metric_data_keys=("实际值", "日期类型"),
    )
    subject = response.get("data") if isinstance(response, dict) else None
    chapter_data = subject.get("章节数据") if isinstance(subject, dict) else []

    print(f"raw JSON: {raw_path.resolve()}")
    print(f"校验结果: {'失败' if has_error else '通过'} - {message}")
    if isinstance(subject, dict):
        print(f"章节名称: {subject.get('章节名称', '')}")
        print(f"月份: {subject.get('月份', '')}")
        print(f"区域经理: {subject.get('区域经理工号', '')} {subject.get('区域经理姓名', '')}")
    if isinstance(chapter_data, list):
        print(f"章节数据条数: {len(chapter_data)}")

    if has_error:
        raise SystemExit(message)

    from ReportGenerator.chapter3_generator import (
        build_chapter3_apipost_checklist,
        format_chapter3_data,
        format_chapter3_data_async,
        normalize_chapter3_records,
    )
    from ReportGenerator.chapter3_renderer import save_final_html, save_final_pdf

    try:
        if args.use_ai_action_guide:
            from ReportGenerator.chapter3_ai_writer import Chapter3ActionGuideWriter

            final_markdown, stats = await format_chapter3_data_async(
                chapter_data,
                period=args.calmonth,
                action_guide_writer=Chapter3ActionGuideWriter(model=None),
            )
        else:
            final_markdown, stats = format_chapter3_data(chapter_data, period=args.calmonth)
    except ChapterDataError as e:
        raise SystemExit(str(e)) from e

    final_md_path = output_dir / "chapter3_final_report.md"
    final_html_path = output_dir / "chapter3_final_report.html"
    final_pdf_path = output_dir / "chapter3_final_report.pdf"
    final_data_path = output_dir / "chapter3_final_data.json"
    checklist_path = output_dir / "chapter3_apipost_checklist.md"

    final_md_path.parent.mkdir(parents=True, exist_ok=True)
    final_md_path.write_text(final_markdown, encoding="utf-8")
    save_final_html(final_markdown, final_html_path)
    save_final_pdf(final_markdown, final_pdf_path)
    save_json(final_data_path, stats)
    checklist_path.write_text(
        build_chapter3_apipost_checklist(normalize_chapter3_records(chapter_data), period=args.calmonth),
        encoding="utf-8",
    )

    print(
        "数据统计: "
        f"有效指标 {stats['有效指标数']} 项，"
        f"过程指标 {stats['过程指标数']} 项，"
        f"产品销量金额指标 {stats['产品销量金额指标数']} 项，"
        f"产品销售量指标 {stats['产品销售量指标数']} 项，"
        f"行动指南来源 {stats.get('行动指南来源', 'rule')}"
    )
    print(f"客户版 Markdown: {final_md_path.resolve()}")
    print(f"客户版 HTML: {final_html_path.resolve()}")
    print(f"客户版 PDF: {final_pdf_path.resolve()}")
    print(f"字段核对数据: {final_data_path.resolve()}")
    print(f"ApiPost 核对清单: {checklist_path.resolve()}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
