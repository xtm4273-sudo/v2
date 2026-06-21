"""Run chapter 4 with real API data.

Example:
    python run_chapter4_api.py --job-id 86002542 --calmonth 202606 --api-key xxx
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
    parser = argparse.ArgumentParser(description="拉取二期第四章接口数据并输出 Markdown/HTML/PDF")
    parser.add_argument("--job-id", required=True, help="区域经理工号，例如 86002542")
    parser.add_argument("--calmonth", required=True, help="月份，例如 202606")
    parser.add_argument("--api-key", default=None, help="接口 apikey；也可通过 SKSHU_BI_API_KEY 环境变量提供")
    parser.add_argument(
        "--api-url",
        default=None,
        help="接口 URL；默认使用 SKSHU_EMPLOYEE_INDEX_CCQ_API_URL 或开发环境 getEmployeeIndexAiCcq",
    )
    parser.add_argument("--output", default=None, help="输出目录；默认 Reports/chapter4_api_{job_id}_{calmonth}")
    parser.add_argument("--timeout", type=int, default=30, help="接口超时秒数，默认 30")
    parser.add_argument("--verify-ssl", action="store_true", help="开启 SSL 证书校验；生产环境建议开启")
    parser.add_argument(
        "--use-ai-action-guide",
        action="store_true",
        help="行动指南走 AI Writer；模型不可用或失败时自动回退规则文案",
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
        else BASE_DIR / "Reports" / f"chapter4_api_{args.job_id}_{args.calmonth}"
    )
    raw_path = output_dir / "raw" / f"employee_{args.job_id}_month_{args.calmonth}_module_4.json"

    response = await fetch_chapter_data(
        job_id=args.job_id,
        time=args.calmonth,
        module=4,
        api_key=args.api_key,
        api_url=args.api_url,
        timeout=args.timeout,
        verify_ssl=args.verify_ssl,
    )
    save_json(raw_path, response)

    has_error, message = check_chapter_response(
        response,
        module=4,
        expected_chapter_keywords=("毛利率与产品结构",),
        required_metric_data_keys=("实际值", "单位"),
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

    from ReportGenerator.chapter4_generator import (
        build_chapter4_apipost_checklist,
        format_chapter4_data,
        format_chapter4_data_async,
    )
    from ReportGenerator.chapter4_renderer import save_final_html, save_final_pdf

    try:
        if args.use_ai_action_guide:
            from AnaModel import DeepSeek_model
            from ReportGenerator.chapter4_ai_writer import Chapter4ActionGuideWriter

            final_markdown, stats = await format_chapter4_data_async(
                response,
                period=args.calmonth,
                action_guide_writer=Chapter4ActionGuideWriter(model=DeepSeek_model),
            )
        else:
            final_markdown, stats = format_chapter4_data(response, period=args.calmonth)
    except ChapterDataError as e:
        raise SystemExit(str(e)) from e

    final_md_path = output_dir / "chapter4_final_report.md"
    final_html_path = output_dir / "chapter4_final_report.html"
    final_pdf_path = output_dir / "chapter4_final_report.pdf"
    final_data_path = output_dir / "chapter4_final_data.json"
    checklist_path = output_dir / "chapter4_apipost_checklist.md"

    final_md_path.parent.mkdir(parents=True, exist_ok=True)
    final_md_path.write_text(final_markdown, encoding="utf-8")
    save_json(final_data_path, stats["cleaned_data"])
    checklist_path.write_text(build_chapter4_apipost_checklist(stats), encoding="utf-8")
    save_final_html(final_markdown, final_html_path)
    save_final_pdf(final_markdown, final_pdf_path)

    print(
        "数据统计: "
        f"均价差异证据 {stats['均价差异正常证据数']} 条，"
        f"收入占比差异证据 {stats['收入占比差异正常证据数']} 条，"
        f"冲突 {stats['冲突数']} 条，"
        f"行动指南来源 {stats.get('行动指南来源', 'rule')}"
    )
    if stats["warnings"]:
        print(f"清洗提示: {len(stats['warnings'])} 条，详见 {final_data_path.resolve()}")
    print(f"缺失字段: {'、'.join(stats['缺失字段'])}")
    print(f"清洗后 JSON: {final_data_path.resolve()}")
    print(f"客户版 Markdown: {final_md_path.resolve()}")
    print(f"客户版 HTML: {final_html_path.resolve()}")
    print(f"客户版 PDF: {final_pdf_path.resolve()}")
    print(f"ApiPost 核对清单: {checklist_path.resolve()}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
