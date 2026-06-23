"""生成仅包含第一章和第二章的测试报告，并输出数据流日志。"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from Data import check_chapter_response, fetch_chapter_data_batch
from ReportGenerator.full_report_renderer import save_full_html, save_full_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成只包含第一章和第二章的报告，并输出数据流日志")
    parser.add_argument("--job-id", default="06427", help="区域经理工号")
    parser.add_argument("--calmonth", default="202606", help="月份，例如 202606")
    parser.add_argument("--api-key", default=None, help="接口 apikey；也可通过 SKSHU_BI_API_KEY 环境变量提供")
    parser.add_argument("--api-url", default=None, help="章节数据接口 URL")
    parser.add_argument("--output-root", default=str(BASE_DIR / "Reports" / "chapter1_2_flow_tests"), help="输出根目录")
    parser.add_argument("--timeout", type=int, default=30, help="接口超时秒数")
    parser.add_argument("--verify-ssl", action="store_true", help="开启 SSL 证书校验")
    parser.add_argument("--name", default="", help="报告标题中的姓名")
    parser.add_argument("--raw-dir", default=None, help="复用已有 raw/module_1.json 和 raw/module_2.json，不重新请求接口")
    return parser


def save_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


async def run(args: argparse.Namespace) -> None:
    report_dir = Path(args.output_root) / args.calmonth / f"{args.job_id}_{args.name or 'unknown'}"
    raw_dir = report_dir / "raw"
    cleaned_dir = report_dir / "cleaned"
    markdown_dir = report_dir / "markdown"
    html_dir = report_dir / "html"
    pdf_dir = report_dir / "pdf"
    for path in (raw_dir, cleaned_dir, markdown_dir, html_dir, pdf_dir):
        path.mkdir(parents=True, exist_ok=True)

    flow: List[Dict[str, Any]] = []
    requests = [
        {"job_id": args.job_id, "time": args.calmonth, "module": 1},
        {"job_id": args.job_id, "time": args.calmonth, "module": 2},
    ]
    flow.append({"step": "build_requests", "detail": requests})

    if args.raw_dir:
        source_raw_dir = Path(args.raw_dir)
        raw_responses = {
            1: json.loads((source_raw_dir / "module_1.json").read_text(encoding="utf-8")),
            2: json.loads((source_raw_dir / "module_2.json").read_text(encoding="utf-8")),
        }
        flow.append({"step": "load_existing_raw", "detail": f"复用已有接口 raw 数据: {source_raw_dir.resolve()}"})
    else:
        raw_responses = await fetch_chapter_data_batch(
            requests=requests,
            concurrent_limit=2,
            api_key=args.api_key,
            api_url=args.api_url,
            timeout=args.timeout,
            verify_ssl=args.verify_ssl,
        )
        flow.append({"step": "fetch_api", "detail": "并发请求 MOUDLE=1 和 MOUDLE=2 完成"})
    save_json(raw_dir / "all_raw_chapters.json", raw_responses)

    for module, response in raw_responses.items():
        save_json(raw_dir / f"module_{module}.json", response)
        subject = response.get("data") if isinstance(response, dict) else {}
        rows = subject.get("章节数据") if isinstance(subject, dict) else []
        has_error, message = check_chapter_response(
            response,
            module=module,
            expected_chapter_keywords=("绩效得分与预警", "薪资绩效分析") if module == 1 else ("利润概况",),
            required_metric_data_keys=(),
        )
        flow.append(
            {
                "step": f"validate_module_{module}",
                "status": "error" if has_error else "ok",
                "message": message,
                "chapter_name": subject.get("章节名称", "") if isinstance(subject, dict) else "",
                "row_count": len(rows) if isinstance(rows, list) else 0,
                "raw_path": str((raw_dir / f"module_{module}.json").resolve()),
            }
        )

    if any(item.get("step", "").startswith("validate_module_") and item.get("status") == "error" for item in flow):
        flow_path = save_json(report_dir / "data_flow_log.json", flow)
        flow_md_path = write_text(report_dir / "data_flow_log.md", build_flow_markdown(flow, {}))
        raise SystemExit(f"接口数据校验失败，已写入日志: {flow_md_path.resolve()} / {flow_path.resolve()}")

    from ReportGenerator.chapter1_generator import format_chapter1_data
    from ReportGenerator.chapter2_renderer import build_final_markdown

    chapter1_markdown, chapter1_stats = format_chapter1_data(raw_responses.get(1, {}), period=args.calmonth)
    chapter1_cleaned = chapter1_stats.get("cleaned_data", {})
    save_json(cleaned_dir / "chapter1_cleaned.json", chapter1_cleaned)
    write_text(markdown_dir / "chapter1.md", chapter1_markdown)
    flow.append(
        {
            "step": "normalize_chapter_1",
            "detail": "第一章接口数据 -> 轻量字段映射 -> Chapter1Data -> Markdown",
            "field_sources": chapter1_cleaned.get("field_sources", {}),
            "cleaned_path": str((cleaned_dir / "chapter1_cleaned.json").resolve()),
            "markdown_path": str((markdown_dir / "chapter1.md").resolve()),
        }
    )

    chapter2_response = raw_responses.get(2, {})
    chapter2_subject = chapter2_response.get("data") if isinstance(chapter2_response, dict) else {}
    chapter2_rows = chapter2_subject.get("章节数据") if isinstance(chapter2_subject, dict) else []
    chapter2_markdown = build_final_markdown(chapter2_rows, period=args.calmonth)
    save_json(cleaned_dir / "chapter2_cleaned.json", {"rows": chapter2_rows})
    write_text(markdown_dir / "chapter2.md", chapter2_markdown)
    flow.append(
        {
            "step": "normalize_chapter_2",
            "detail": "第二章接口 data.章节数据 -> 按 指标名称 + 日期类型 组织利润概况表 -> Markdown",
            "row_count": len(chapter2_rows) if isinstance(chapter2_rows, list) else 0,
            "cleaned_path": str((cleaned_dir / "chapter2_cleaned.json").resolve()),
            "markdown_path": str((markdown_dir / "chapter2.md").resolve()),
        }
    )

    title_name = args.name or args.job_id
    full_markdown = "\n".join(
        [
            f"# {title_name}{args.calmonth}经营分析报告（第一、二章）",
            "",
            f"工号：{args.job_id}",
            f"姓名：{args.name or '—'}",
            "",
            chapter1_markdown.strip(),
            "",
            chapter2_markdown.strip(),
            "",
        ]
    )
    markdown_path = write_text(markdown_dir / "chapter1_2_report.md", full_markdown)
    html_path = save_full_html(full_markdown, html_dir / "chapter1_2_report.html", title=f"{title_name}{args.calmonth}经营分析报告")
    pdf_path = save_full_pdf(full_markdown, pdf_dir / "chapter1_2_report.pdf", title=f"{title_name}{args.calmonth}经营分析报告")
    flow.append(
        {
            "step": "render_report",
            "detail": "第一章 Markdown + 第二章 Markdown -> 连续版 HTML/PDF",
            "markdown_path": str(markdown_path.resolve()),
            "html_path": str(html_path.resolve()),
            "pdf_path": str(pdf_path.resolve()),
        }
    )

    flow_path = save_json(report_dir / "data_flow_log.json", flow)
    flow_md_path = write_text(report_dir / "data_flow_log.md", build_flow_markdown(flow, chapter1_cleaned))

    print(f"报告目录: {report_dir.resolve()}")
    print(f"Markdown: {markdown_path.resolve()}")
    print(f"HTML: {html_path.resolve()}")
    print(f"PDF: {pdf_path.resolve()}")
    print(f"数据流日志 JSON: {flow_path.resolve()}")
    print(f"数据流日志 Markdown: {flow_md_path.resolve()}")


def build_flow_markdown(flow: List[Dict[str, Any]], chapter1_cleaned: Dict[str, Any]) -> str:
    lines = [
        "# 第一、二章报告数据流日志",
        "",
        "## 运行步骤",
        "",
    ]
    for item in flow:
        lines.append(f"### {item.get('step')}")
        for key, value in item.items():
            if key == "step":
                continue
            if key == "field_sources":
                lines.append("")
                lines.append("字段来源见下方“第一章字段来源”。")
                continue
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    lines.extend(
        [
            "## 第一章字段来源",
            "",
            "| 报告字段 | 状态 | 来源 | 原始值 | 是否 fallback |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for field_id, source in (chapter1_cleaned.get("field_sources") or {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    field_id,
                    str(source.get("status", "")),
                    str(source.get("source", source.get("message", ""))),
                    str(source.get("raw_value", "")),
                    str(source.get("fallback_used", "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 数据如何进入报告",
            "",
            "1. 脚本构造两个请求：`MOUDLE=1` 和 `MOUDLE=2`。",
            "2. 接口返回后，原始响应保存到 `raw/module_1.json` 和 `raw/module_2.json`。",
            "3. 第一章先经过字段映射，生成 `cleaned/chapter1_cleaned.json`，其中 `field_sources` 记录每个排名表字段来自哪条接口记录。",
            "4. 第一章 Markdown 表格只读取清洗后的 `Chapter1Data`，不再临时猜字段。",
            "5. 第二章读取 `data.章节数据`，按 `指标名称 + 日期类型` 组装利润概况表。",
            "6. 两章 Markdown 合并后，由总报告渲染器生成连续 HTML/PDF。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
