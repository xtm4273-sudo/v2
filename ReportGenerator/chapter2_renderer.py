"""
第二章最终版渲染器
将利润概况数据输出为客户查看用的 HTML 和 PDF。
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Dict, List, Tuple
import re

from .report_theme import apply_html_theme, colors
from .browser_pdf import html_to_pdf
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .chapter2_generator import build_chapter2_markdown, normalize_chapter2_data


def month_labels(period: str) -> Tuple[str, str]:
    """将接口月份 202605 转为表头 5月 / 1-5 月累计。"""
    if len(period) < 6 or not period[-2:].isdigit():
        return "当月", "累计"

    month = int(period[-2:])
    return f"{month}月", f"1-{month} 月累计"


def build_final_markdown(
    raw_chapter_data: List[Dict[str, Any]],
    period: str,
    note: str = "",
) -> str:
    """生成客户版第二章 Markdown，不改写接口精度。"""
    markdown = build_chapter2_markdown(normalize_chapter2_data(raw_chapter_data, period=period))
    lines = [markdown.rstrip()]
    if note:
        lines.extend(["", note])
    return "\n".join(lines) + "\n"


def save_final_html(markdown: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    return output_path


def save_final_pdf(markdown: str, output_path: Path) -> Path:
    return html_to_pdf(_markdown_to_html(markdown), output_path)


def _inline_html(text: str) -> str:
    pending = "__CHAPTER2_PENDING__"
    text = text.strip().replace('<span class="pending-value">待补充</span>', pending)
    text = escape(text)
    text = text.replace(pending, '<span class="pending-value">待补充</span>')
    return re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)


def _inline_pdf(text: str) -> str:
    pending = "__CHAPTER2_PENDING__"
    text = text.strip().replace('<span class="pending-value">待补充</span>', pending)
    text = escape(text)
    text = text.replace(pending, '<font color="#c00000"><b>待补充</b></font>')
    return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)


def _parse_markdown_table(lines: List[str], start: int) -> Tuple[List[List[str]], int]:
    table_lines = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        table_lines.append(lines[i].strip())
        i += 1

    rows = []
    for line in table_lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(set(cell) <= {"-", " "} for cell in cells):
            continue
        rows.append(cells)

    return rows, i


def _markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue

        if line.startswith("|"):
            rows, i = _parse_markdown_table(lines, i)
            parts.append("<table>")
            for row_index, row in enumerate(rows):
                tag = "th" if row_index == 0 else "td"
                cells = "".join(f"<{tag}>{_inline_html(cell)}</{tag}>" for cell in row)
                parts.append(f"<tr>{cells}</tr>")
            parts.append("</table>")
            continue

        if line.startswith("# "):
            parts.append(f"<h1>{_inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            parts.append(f"<h2>{_inline_html(line[3:])}</h2>")
        elif line.startswith("* "):
            parts.append(f'<p class="bullet">{_inline_html(line[2:])}</p>')
        else:
            parts.append(f"<p>{_inline_html(line)}</p>")
        i += 1

    css = """
:root { color-scheme: light; }
body {
  margin: 0;
  background: #f3f5f7;
  color: #172033;
  font-family: "Microsoft YaHei", "Heiti SC", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  line-height: 1.72;
}
.page {
  max-width: 920px;
  margin: 32px auto;
  padding: 44px 56px 56px;
  background: #fff;
  border: 1px solid #dbe2ea;
  box-shadow: 0 10px 26px rgba(23,32,51,.08);
}
h1 { margin: 0 0 24px; text-align: center; font-size: 28px; line-height: 1.35; color: #16324f; }
h2 { margin: 28px 0 12px; font-size: 22px; color: #16324f; border-bottom: 2px solid #d8e2ed; padding-bottom: 7px; }
p { margin: 7px 0; font-size: 15px; }
p.bullet { position: relative; padding-left: 18px; }
p.bullet::before { content: "•"; position: absolute; left: 0; color: #244b73; font-weight: 700; }
strong { color: #0b5cad; font-weight: 700; }
.pending-value { color: #c00000; font-weight: 700; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; table-layout: fixed; }
th, td { border: 1px solid #cfd8e3; padding: 9px 10px; text-align: left; vertical-align: middle; word-break: break-word; }
th { background: #edf3f8; color: #16324f; font-weight: 700; }
tr:nth-child(even) td { background: #fafbfd; }
@media print {
  body { background: #fff; }
  .page { box-shadow: none; border: 0; margin: 0; max-width: none; padding: 0; }
}
"""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>第二章利润概况报告</title>
<style>{apply_html_theme(css)}</style>
</head>
<body><main class="page">{''.join(parts)}</main></body>
</html>
"""


def _markdown_to_pdf(markdown: str, output_path: Path) -> None:
    font_path = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    if not font_path.exists():
        raise RuntimeError(f"生成第二章 PDF 失败：缺少可嵌入中文字体 {font_path}")
    font = "Chapter2CJK"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font, str(font_path)))

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
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBody",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=10.5,
            leading=17,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNTable",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=8.2,
            leading=11,
        )
    )

    story = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue

        if line.startswith("|"):
            rows, i = _parse_markdown_table(lines, i)
            table_rows = [
                [Paragraph(_inline_pdf(cell), styles["CNTable"]) for cell in row]
                for row in rows
            ]
            table = Table(
                table_rows,
                colWidths=[45 * mm, 27 * mm, 35 * mm, 35 * mm],
                repeatRows=1,
            )
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), font),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f8")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#16324f")),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd8e3")),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 5 * mm))
            continue

        if line.startswith("# "):
            story.append(Paragraph(_inline_pdf(line[2:]), styles["CNTitle"]))
        else:
            story.append(Paragraph(_inline_pdf(line), styles["CNBody"]))
        i += 1

    def page_no(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="第二章利润概况报告",
    )
    pdf.build(story, onFirstPage=page_no, onLaterPages=page_no)
