"""Compile phase-2 chapter reports into one editable report package.

This script keeps each chapter editable as Markdown while producing a combined
Markdown, HTML, and PDF report.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Iterable, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from ReportGenerator.browser_pdf import html_to_pdf


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_REPORTS_DIR = BASE_DIR / "Reports"
CHAPTER_RANGE = range(1, 9)


@dataclass(frozen=True)
class ChapterSource:
    number: int
    source_dir: Path
    markdown_path: Path
    pdf_path: Optional[Path]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="整合二期 1-8 章为一份可编辑报告")
    parser.add_argument("--job-id", required=True, help="区域经理工号，例如 86002542")
    parser.add_argument("--calmonth", required=True, help="月份，例如 202606")
    parser.add_argument(
        "--reports-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="章节报告目录，默认 SimpleIntellReportV2/Reports",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="整合报告输出目录；默认 Reports/integrated_report_{job_id}_{calmonth}",
    )
    parser.add_argument(
        "--from-chapters",
        action="store_true",
        help="使用输出目录 chapters/ 内已修改的 Markdown 重新编译",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="不覆盖输出目录 chapters/ 内已有 Markdown",
    )
    parser.add_argument(
        "--pdf-mode",
        choices=("markdown", "merge"),
        default="markdown",
        help="PDF 生成方式：markdown=从可编辑 Markdown 编译；merge=拼接原章节 PDF 保留原版式",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="要求 1-8 章全部存在，否则失败",
    )
    return parser.parse_args()


def discover_chapters(reports_dir: Path, job_id: str, calmonth: str) -> List[ChapterSource]:
    chapters: List[ChapterSource] = []
    for chapter_no in CHAPTER_RANGE:
        candidates = sorted(
            reports_dir.glob(f"chapter{chapter_no}_api_{job_id}_{calmonth}")
        )
        if not candidates and chapter_no == 2:
            candidates = sorted(reports_dir.glob("chapter2_final"))

        for source_dir in candidates:
            md_path = source_dir / f"chapter{chapter_no}_final_report.md"
            pdf_path = source_dir / f"chapter{chapter_no}_final_report.pdf"
            if md_path.exists():
                chapters.append(
                    ChapterSource(
                        number=chapter_no,
                        source_dir=source_dir,
                        markdown_path=md_path,
                        pdf_path=pdf_path if pdf_path.exists() else None,
                    )
                )
                break
    return chapters


def load_edited_chapters(chapters_dir: Path) -> List[ChapterSource]:
    chapters: List[ChapterSource] = []
    for chapter_no in CHAPTER_RANGE:
        md_path = chapters_dir / f"chapter{chapter_no}_final_report.md"
        pdf_path = chapters_dir / f"chapter{chapter_no}_final_report.pdf"
        if md_path.exists():
            chapters.append(
                ChapterSource(
                    number=chapter_no,
                    source_dir=chapters_dir,
                    markdown_path=md_path,
                    pdf_path=pdf_path if pdf_path.exists() else None,
                )
            )
    return chapters


def ensure_complete(chapters: Iterable[ChapterSource], strict: bool) -> None:
    existing = {chapter.number for chapter in chapters}
    missing = [str(number) for number in CHAPTER_RANGE if number not in existing]
    if missing and strict:
        raise SystemExit(f"缺少章节: {', '.join(missing)}")
    if missing:
        print(f"提示：当前未发现章节 {', '.join(missing)}，将先整合已有章节。")


def prepare_output_chapters(
    sources: List[ChapterSource], chapters_dir: Path, no_copy: bool
) -> List[ChapterSource]:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    prepared: List[ChapterSource] = []
    for source in sources:
        target_md = chapters_dir / f"chapter{source.number}_final_report.md"
        target_pdf = chapters_dir / f"chapter{source.number}_final_report.pdf"

        if not no_copy or not target_md.exists():
            shutil.copy2(source.markdown_path, target_md)
        if source.pdf_path and (not no_copy or not target_pdf.exists()):
            shutil.copy2(source.pdf_path, target_pdf)

        prepared.append(
            ChapterSource(
                number=source.number,
                source_dir=chapters_dir,
                markdown_path=target_md,
                pdf_path=target_pdf if target_pdf.exists() else None,
            )
        )
    return prepared


def normalize_chapter_markdown(text: str) -> str:
    text = text.strip()
    return text + "\n" if text else ""


def build_combined_markdown(chapters: List[ChapterSource], title: str) -> str:
    parts = [f"# {title}", ""]
    for index, chapter in enumerate(chapters):
        content = normalize_chapter_markdown(chapter.markdown_path.read_text(encoding="utf-8"))
        if not content:
            continue
        if index:
            parts.append("")
        parts.append(content.rstrip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def inline_html(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    return text.replace("&lt;br&gt;", "<br>")


def inline_pdf(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    return text.replace("&lt;br&gt;", "<br/>")


def parse_markdown_table(lines: List[str], start: int) -> tuple[List[List[str]], int]:
    table_lines = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        table_lines.append(lines[i].strip())
        i += 1

    rows: List[List[str]] = []
    for line in table_lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        rows.append(cells)
    return rows, i


def markdown_to_html(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    parts: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped == "\\pagebreak":
            parts.append('<div class="page-break"></div>')
            i += 1
            continue
        if stripped.startswith("|"):
            rows, i = parse_markdown_table(lines, i)
            parts.append("<table>")
            for row_index, row in enumerate(rows):
                tag = "th" if row_index == 0 else "td"
                parts.append(
                    "<tr>"
                    + "".join(f"<{tag}>{inline_html(cell)}</{tag}>" for cell in row)
                    + "</tr>"
                )
            parts.append("</table>")
            continue
        if stripped.startswith("# "):
            parts.append(f"<h1>{inline_html(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            parts.append(f"<h2>{inline_html(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            parts.append(f"<h3>{inline_html(stripped[4:])}</h3>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            parts.append(f'<p class="bullet">{inline_html(stripped[2:])}</p>')
        else:
            class_name = ' class="guide"' if stripped.startswith("◇ ") else ""
            parts.append(f"<p{class_name}>{inline_html(stripped)}</p>")
        i += 1

    css = """
:root { color-scheme: light; }
body {
  margin: 0;
  background: #eef2f6;
  color: #222936;
  font-family: "Microsoft YaHei", "Heiti SC", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  line-height: 1.72;
}
.page {
  box-sizing: border-box;
  max-width: 980px;
  margin: 28px auto;
  padding: 42px 52px 56px;
  background: #fff;
  border: 1px solid #d9e0e8;
}
h1 { margin: 0 0 24px; text-align: center; font-size: 28px; line-height: 1.35; color: #16324f; }
h2 { margin: 34px 0 14px; font-size: 22px; line-height: 1.35; color: #16324f; border-bottom: 2px solid #d8e2ed; padding-bottom: 7px; }
h3 { margin: 24px 0 10px; font-size: 18px; line-height: 1.4; color: #303946; }
p { margin: 8px 0; font-size: 15px; }
p.bullet { position: relative; padding-left: 18px; }
p.bullet::before { content: "•"; position: absolute; left: 0; color: #244b73; font-weight: 700; }
p.guide { font-weight: 700; color: #3f4247; }
strong { font-weight: 800; color: #0b5cad; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; margin: 14px 0 24px; font-size: 13px; }
th, td { border: 1px solid #cfd8e3; padding: 8px 9px; text-align: left; vertical-align: middle; word-break: break-word; }
th { background: #edf3f8; color: #16324f; font-weight: 800; }
tr:nth-child(even) td { background: #fafbfd; }
.page-break { break-after: page; height: 28px; }
@media print {
  body { background: #fff; }
  .page { margin: 0; max-width: none; border: 0; padding: 0; }
}
"""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{css}</style>
</head>
<body><main class="page">{''.join(parts)}</main></body>
</html>
"""


def register_font() -> str:
    candidates = [
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/NISC18030.ttf",
    ]
    for font_path in candidates:
        path = Path(font_path)
        if path.exists():
            pdfmetrics.registerFont(TTFont("ReportCJK", str(path)))
            return "ReportCJK"

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def markdown_to_pdf(markdown: str, output_path: Path, title: str) -> None:
    html_to_pdf(markdown_to_html(markdown, title), output_path)


def _markdown_to_pdf_reportlab(markdown: str, output_path: Path, title: str) -> None:
    """Legacy renderer kept only for reference; customer PDFs use Chromium."""
    font = register_font()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CNTitle",
            parent=styles["Title"],
            fontName=font,
            fontSize=20,
            leading=28,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#16324f"),
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNHeading",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=14,
            leading=20,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#16324f"),
            spaceBefore=12,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBody",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=9.8,
            leading=15,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNTable",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=7.2,
            leading=9.5,
        )
    )

    story = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped == "\\pagebreak":
            story.append(PageBreak())
            i += 1
            continue
        if stripped.startswith("|"):
            rows, i = parse_markdown_table(lines, i)
            if rows:
                max_cols = max(len(row) for row in rows)
                normalized = [row + [""] * (max_cols - len(row)) for row in rows]
                table = Table(
                    [
                        [Paragraph(inline_pdf(cell), styles["CNTable"]) for cell in row]
                        for row in normalized
                    ],
                    repeatRows=1,
                )
                table.setStyle(
                    TableStyle(
                        [
                            ("FONTNAME", (0, 0), (-1, -1), font),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f8")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#16324f")),
                            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cfd8e3")),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.extend([table, Spacer(1, 5 * mm)])
            continue
        if stripped.startswith("# "):
            story.append(Paragraph(inline_pdf(stripped[2:]), styles["CNTitle"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(inline_pdf(stripped[3:]), styles["CNHeading"]))
        elif stripped.startswith("### "):
            story.append(Paragraph(inline_pdf(stripped[4:]), styles["CNHeading"]))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            story.append(Paragraph("• " + inline_pdf(stripped[2:]), styles["CNBody"]))
        else:
            story.append(Paragraph(inline_pdf(stripped), styles["CNBody"]))
        i += 1

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=title,
    )
    doc.build(story)


def merge_chapter_pdfs(chapters: List[ChapterSource], output_path: Path) -> None:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise SystemExit("缺少 pypdf，无法使用 --pdf-mode merge。请先安装 pypdf。") from exc

    writer = PdfWriter()
    for chapter in chapters:
        if not chapter.pdf_path or not chapter.pdf_path.exists():
            raise SystemExit(f"第 {chapter.number} 章缺少可拼接 PDF: {chapter.pdf_path}")
        reader = PdfReader(str(chapter.pdf_path))
        start_page = len(writer.pages)
        for page in reader.pages:
            writer.add_page(page)
        writer.add_outline_item(f"第 {chapter.number} 章", start_page)

    with output_path.open("wb") as f:
        writer.write(f)


def write_manifest(
    output_dir: Path,
    chapters: List[ChapterSource],
    missing: List[int],
    pdf_mode: str,
) -> None:
    manifest = {
        "chapters": [
            {
                "chapter": chapter.number,
                "markdown": str(chapter.markdown_path.relative_to(output_dir)),
                "pdf": str(chapter.pdf_path.relative_to(output_dir)) if chapter.pdf_path else None,
            }
            for chapter in chapters
        ],
        "missing_chapters": missing,
        "pdf_mode": pdf_mode,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    reports_dir = Path(args.reports_dir).resolve()
    output_dir = (
        Path(args.output).resolve()
        if args.output
        else reports_dir / f"integrated_report_{args.job_id}_{args.calmonth}"
    )
    chapters_dir = output_dir / "chapters"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.from_chapters:
        chapters = load_edited_chapters(chapters_dir)
    else:
        sources = discover_chapters(reports_dir, args.job_id, args.calmonth)
        ensure_complete(sources, args.strict)
        chapters = prepare_output_chapters(sources, chapters_dir, args.no_copy)

    chapters = sorted(chapters, key=lambda chapter: chapter.number)
    ensure_complete(chapters, args.strict)
    if not chapters:
        raise SystemExit("未找到可整合的章节 Markdown。")

    title = f"二期经营分析报告_{args.job_id}_{args.calmonth}"
    combined_markdown = build_combined_markdown(chapters, title)
    md_path = output_dir / "integrated_report.md"
    html_path = output_dir / "integrated_report.html"
    pdf_path = output_dir / "integrated_report.pdf"

    md_path.write_text(combined_markdown, encoding="utf-8")
    html_path.write_text(markdown_to_html(combined_markdown, title), encoding="utf-8")

    if args.pdf_mode == "merge":
        merge_chapter_pdfs(chapters, pdf_path)
    else:
        markdown_to_pdf(combined_markdown, pdf_path, title)

    missing = [number for number in CHAPTER_RANGE if number not in {c.number for c in chapters}]
    write_manifest(output_dir, chapters, missing, args.pdf_mode)

    print(f"整合目录: {output_dir}")
    print(f"章节 Markdown: {chapters_dir}")
    print(f"整本 Markdown: {md_path}")
    print(f"整本 HTML: {html_path}")
    print(f"整本 PDF: {pdf_path}")


if __name__ == "__main__":
    main()
