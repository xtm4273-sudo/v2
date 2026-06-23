"""第一章最终版渲染器。

将第一章「绩效得分与预警」Markdown 输出为 HTML 和 PDF。
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import List, Tuple
import re

from .report_theme import apply_html_theme, colors
from .browser_pdf import html_to_pdf
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PDF_MARGIN = 12 * mm


def save_final_html(markdown: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    return output_path


def save_final_pdf(markdown: str, output_path: Path) -> Path:
    return html_to_pdf(_markdown_to_html(markdown), output_path)


def _inline_html(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace("待补充", '<span class="pending-value">待补充</span>')
    return text.replace("&lt;br&gt;", "<br>")


def _inline_pdf(text: str) -> str:
    parts = [escape(part.strip()) for part in text.strip().split("<br>")]
    text = "<br/>".join(parts)
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    return text.replace("待补充", '<font color="#d32f2f">待补充</font>')


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


def _table_class(rows: List[List[str]]) -> str:
    if not rows:
        return "data-table"
    first = rows[0][0] if rows[0] else ""
    second = rows[0][1] if len(rows[0]) > 1 else ""
    if first == "绩效排名" or second == "绩效排名":
        return "data-table rank-table"
    if first == "月度绩效":
        return "data-table performance-table"
    if first == "奖金影响因素":
        return "data-table bonus-table"
    return "data-table"


def _markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("|"):
            rows, i = _parse_markdown_table(lines, i)
            parts.append(f'<table class="{_table_class(rows)}">')
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
        else:
            parts.append(f"<p>{_inline_html(line)}</p>")
        i += 1

    css = """
:root { color-scheme: light; }
body {
  margin: 0;
  background: #f4f5f7;
  color: #222;
  font-family: "Microsoft YaHei", "Heiti SC", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  line-height: 1.68;
}
.page {
  box-sizing: border-box;
  max-width: 980px;
  min-height: 100vh;
  margin: 28px auto;
  padding: 42px 46px 52px;
  background: #fff;
  border: 1px solid #d9dde3;
}
h1 {
  margin: 14px 0 24px;
  text-align: left;
  font-size: 28px;
  line-height: 1.25;
  font-weight: 800;
  color: #222;
}
h2 {
  margin: 30px 0 14px;
  font-size: 22px;
  line-height: 1.35;
  font-weight: 800;
  color: #111;
}
p {
  margin: 8px 0;
  font-size: 15.5px;
}
strong {
  font-weight: 800;
}
.pending-value {
  color: #d32f2f;
  font-weight: 700;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  margin: 12px 0 26px;
  font-size: 14.5px;
  border-top: 2px solid #111;
  border-bottom: 2px solid #111;
}
.data-table th,
.data-table td {
  padding: 8px 9px;
  text-align: center;
  vertical-align: middle;
  word-break: break-word;
  border: 1px dashed #bfc3c8;
}
.data-table th {
  padding: 11px 9px;
  font-weight: 800;
  color: #111;
  border-bottom: 2px solid #111;
}
.bonus-table {
  font-size: 13px;
}
.bonus-table td:last-child {
  text-align: left;
}
@media print {
  body { background: #fff; }
  .page { margin: 0; max-width: none; min-height: auto; padding: 0; border: 0; }
}
"""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>第一章绩效得分与预警报告</title>
<style>{apply_html_theme(css)}</style>
</head>
<body><main class="page">{''.join(parts)}</main></body>
</html>
"""


def _markdown_to_pdf(markdown: str, output_path: Path) -> None:
    font = _register_pdf_font()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CNTitle1",
            parent=styles["Title"],
            fontName=font,
            fontSize=18,
            leading=24,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#222222"),
            spaceAfter=9,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNSection1",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=14,
            leading=20,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#111111"),
            spaceBefore=8,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBody1",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=9.8,
            leading=15,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNTable1",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=7.5,
            leading=10,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNTableSmall1",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=6.3,
            leading=8.2,
            alignment=TA_LEFT,
        )
    )

    story = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("|"):
            rows, i = _parse_markdown_table(lines, i)
            story.append(_pdf_table(rows, styles))
            story.append(Spacer(1, 5))
            continue
        if line.startswith("# "):
            story.append(Paragraph(_inline_pdf(line[2:]), styles["CNTitle1"]))
        elif line.startswith("## "):
            story.append(Paragraph(_inline_pdf(line[3:]), styles["CNSection1"]))
        else:
            story.append(Paragraph(_inline_pdf(line), styles["CNBody1"]))
        i += 1

    def page_no(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(A4[0] - PDF_MARGIN, 9 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=PDF_MARGIN,
        leftMargin=PDF_MARGIN,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
        title="第一章绩效得分与预警报告",
    )
    pdf.build(story, onFirstPage=page_no, onLaterPages=page_no)


def _pdf_table(rows: List[List[str]], styles) -> Table:
    if not rows:
        return Table([[""]])
    table_type = _table_class(rows)
    usable_width = A4[0] - PDF_MARGIN * 2
    if "rank-table" in table_type:
        col_widths = [usable_width * 0.18] + [usable_width * (0.82 / 3)] * 3
    elif table_type == "performance-table":
        col_widths = [usable_width * 0.28, usable_width * 0.24, usable_width * 0.48]
    elif table_type == "bonus-table":
        col_widths = [usable_width * 0.24, usable_width * 0.34, usable_width * 0.42]
    else:
        col_widths = [usable_width / len(rows[0])] * len(rows[0])

    small = table_type == "bonus-table"
    para_style = styles["CNTableSmall1"] if small else styles["CNTable1"]
    data = [[Paragraph(_inline_pdf(cell), para_style) for cell in row] for row in rows]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), para_style.fontName),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f2f4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111111")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#bfc3c8")),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.HexColor("#111111")),
                ("LINEBELOW", (0, 0), (-1, 0), 1.0, colors.HexColor("#111111")),
                ("LINEBELOW", (0, -1), (-1, -1), 1.2, colors.HexColor("#111111")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    if "rank-table" in table_type:
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F8E9")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                    ("BOX", (0, 0), (-1, -1), 0, colors.white),
                    ("INNERGRID", (0, 0), (-1, -1), 0, colors.white),
                    ("LINEABOVE", (0, 0), (-1, -1), 0, colors.white),
                    ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                    ("TOPPADDING", (0, 1), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
                ]
            )
        )
    if table_type == "bonus-table":
        table.setStyle(TableStyle([("ALIGN", (2, 1), (2, -1), "LEFT")]))
    return table


def _register_pdf_font() -> str:
    candidates = [
        ("/System/Library/Fonts/Supplemental/NISC18030.ttf", "NISC18030"),
        ("/System/Library/Fonts/Supplemental/Songti.ttc", "Songti"),
        ("/System/Library/Fonts/PingFang.ttc", "PingFang"),
        ("/Library/Fonts/Arial Unicode.ttf", "ArialUnicode"),
    ]
    for path, name in candidates:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                continue
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"
