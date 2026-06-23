"""Run chapter 8 with API data or a local fixture.

Example:
    python run_chapter8_api.py --job-id 86002542 --calmonth 202606 --api-key xxx
    python run_chapter8_api.py --job-id 86002542 --calmonth 202606 --skip-api --fixture Data/fixtures/chapter8_mock.json
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
    parser = argparse.ArgumentParser(description="拉取二期第八章接口数据并输出 Markdown/HTML/PDF")
    parser.add_argument("--job-id", required=True, help="区域经理工号，例如 86002542")
    parser.add_argument("--calmonth", required=True, help="月份，例如 202606")
    parser.add_argument("--api-key", default=None, help="接口 apikey；也可通过 SKSHU_BI_API_KEY 环境变量提供")
    parser.add_argument("--api-url", default=None, help="接口 URL")
    parser.add_argument("--output", default=None, help="输出目录")
    parser.add_argument("--timeout", type=int, default=30, help="接口超时秒数")
    parser.add_argument("--verify-ssl", action="store_true", help="开启 SSL 证书校验")
    parser.add_argument("--fixture", default=None, help="接口未就绪时用于生成报告的本地 JSON fixture")
    parser.add_argument("--skip-api", action="store_true", help="跳过接口请求，仅使用 --fixture 生成报告")
    parser.add_argument("--use-ai-summary", action="store_true", help="总结（优势/短板/核心策略）走 AI Writer")
    return parser


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ChapterDataError(f"JSON 文件必须是对象: {path}")
    return data


def save_json(path: Path, data: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def skipped_api_response(job_id: str, calmonth: str) -> Dict[str, Any]:
    return {"code": 1, "message": "skip_api", "data": {"月份": calmonth, "区域经理工号": job_id, "章节名称": "八、总结", "章节数据": []}}


def print_response_summary(response: Dict[str, Any], raw_path: Path) -> None:
    has_error, message = check_chapter_response(response, module=8, expected_chapter_keywords=("总结",), required_metric_data_keys=())
    subject = response.get("data") if isinstance(response, dict) else None
    print(f"raw JSON: {raw_path.resolve()}")
    print(f"校验结果: {'提示' if has_error else '通过'} - {message}")
    if isinstance(subject, dict):
        print(f"章节名称: {subject.get('章节名称', '')}")
        print(f"月份: {subject.get('月份', '')}")
        print(f"区域经理: {subject.get('区域经理工号', '')} {subject.get('区域经理姓名', '')}")


def print_stats(stats: Dict[str, Any]) -> None:
    print(f"数据统计: 绩效得分 {stats.get('绩效得分') or '—'}，正向信号 {stats.get('正向信号数') or 0} 条，负向信号 {stats.get('负向信号数') or 0} 条")


async def run(args: argparse.Namespace) -> None:
    if args.skip_api and not args.fixture:
        raise SystemExit("--skip-api 需要同时提供 --fixture")

    output_dir = Path(args.output) if args.output else BASE_DIR / "Reports" / f"chapter8_api_{args.job_id}_{args.calmonth}"
    raw_path = output_dir / "raw" / f"employee_{args.job_id}_month_{args.calmonth}_module_8.json"

    if args.skip_api:
        response = skipped_api_response(args.job_id, args.calmonth)
    else:
        response = await fetch_chapter_data(job_id=args.job_id, time=args.calmonth, module=8, api_key=args.api_key, api_url=args.api_url, timeout=args.timeout, verify_ssl=args.verify_ssl)
    save_json(raw_path, response)
    print_response_summary(response, raw_path)

    if "error" in response and not args.fixture:
        raise SystemExit(f"第八章接口请求失败，且未提供 fixture: {response.get('message', '')}")

    generation_source = response
    if args.fixture:
        fixture_path = Path(args.fixture)
        generation_source = load_json(fixture_path)
        print(f"使用 fixture 生成报告: {fixture_path.resolve()}")

    from ReportGenerator.chapter8_generator import format_chapter8_data, format_chapter8_data_with_ai
    from ReportGenerator.chapter8_renderer import save_final_html, save_final_pdf

    try:
        if args.use_ai_summary:
            from AnaModel import DeepSeek_model
            from ReportGenerator.chapter8_ai_writer import Chapter8SummaryWriter
            final_markdown, stats = await format_chapter8_data_with_ai(generation_source, period=args.calmonth, action_writer=Chapter8SummaryWriter(model=DeepSeek_model))
        else:
            final_markdown, stats = format_chapter8_data(generation_source, period=args.calmonth)
    except ChapterDataError as e:
        raise SystemExit(str(e)) from e

    final_md_path = output_dir / "chapter8_final_report.md"
    final_html_path = output_dir / "chapter8_final_report.html"
    final_pdf_path = output_dir / "chapter8_final_report.pdf"
    final_data_path = output_dir / "chapter8_final_data.json"

    final_md_path.parent.mkdir(parents=True, exist_ok=True)
    final_md_path.write_text(final_markdown, encoding="utf-8")
    save_json(final_data_path, stats["cleaned_data"])
    print_stats(stats)

    save_final_html(final_markdown, final_html_path)
    save_final_pdf(final_markdown, final_pdf_path)

    print(f"清洗后 JSON: {final_data_path.resolve()}")
    print(f"客户版 Markdown: {final_md_path.resolve()}")
    print(f"客户版 HTML: {final_html_path.resolve()}")
    print(f"客户版 PDF: {final_pdf_path.resolve()}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
