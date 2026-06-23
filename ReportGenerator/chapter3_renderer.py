"""第三章最终版渲染器。

将第三章销量分析 Markdown 输出为客户查看用的 HTML 和 PDF。
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
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PDF_MARGIN = 13 * mm


def save_final_html(markdown: str, output_path: Path) -> Path:
    """保存第三章 HTML 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    return output_path


def save_final_pdf(markdown: str, output_path: Path) -> Path:
    """保存第三章 PDF 文件。"""
    return html_to_pdf(_markdown_to_html(markdown), output_path)


def _inline_html(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"&lt;span style=&quot;color:#c00000;font-weight:700&quot;&gt;待补充&lt;/span&gt;", r'<span class="missing">待补充</span>', text)
    return re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)


def _inline_pdf(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"&lt;span style=&quot;color:#c00000;font-weight:700&quot;&gt;待补充&lt;/span&gt;", r'<font color="#c00000"><b>待补充</b></font>', text)
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


def _table_class(rows: List[List[str]]) -> str:
    if not rows:
        return "data-table"
    first_header = rows[0][0] if rows[0] else ""
    if first_header == "销量":
        return "data-table sales-table"
    if first_header == "过程指标":
        return "data-table process-table"
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
        elif line.startswith("### "):
            parts.append(f"<h3>{_inline_html(line[4:])}</h3>")
        elif line.startswith("  * "):
            parts.append(f'<p class="bullet bullet-sub">{_inline_html(line[4:])}</p>')
        elif line.startswith("* "):
            parts.append(f'<p class="bullet">{_inline_html(line[2:])}</p>')
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
  line-height: 1.7;
}
.page {
  box-sizing: border-box;
  max-width: 980px;
  min-height: 100vh;
  margin: 28px auto;
  padding: 44px 46px 52px;
  background: #fff;
  border: 1px solid #d9dde3;
}
h1 {
  margin: 0 0 26px;
  font-size: 28px;
  line-height: 1.25;
  font-weight: 800;
  color: #3a3d42;
}
h2 {
  margin: 32px 0 14px;
  font-size: 22px;
  line-height: 1.35;
  font-weight: 800;
  color: #111;
}
h3 {
  margin: 24px 0 10px;
  font-size: 18px;
  line-height: 1.4;
  font-weight: 800;
  color: #222;
}
p {
  margin: 9px 0;
  font-size: 16px;
}
.bullet {
  position: relative;
  padding-left: 24px;
  font-weight: 700;
  color: #3f4247;
}
.bullet::before {
  content: "\\25B6";
  position: absolute;
  left: 0;
  color: #111;
}
.bullet-sub {
  margin-left: 0;
  padding-left: 28px;
  font-weight: 600;
}
.bullet-sub::before {
  content: "\\2727";
  top: 0;
}
strong {
  font-weight: 800;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  margin: 14px 0 34px;
  font-size: 15px;
  border-top: 2px solid #111;
  border-bottom: 2px solid #111;
}
.data-table th,
.data-table td {
  padding: 8px 10px;
  text-align: center;
  vertical-align: middle;
  word-break: break-word;
  border: 1px dashed #bfc3c8;
}
.data-table th {
  padding: 12px 10px;
  font-weight: 800;
  color: #111;
  border-bottom: 2px solid #111;
}
.data-table tr:last-child td {
  border-bottom: 0;
}
.missing { color: #c00000; font-weight: 800; }
.sales-table th:first-child,
.sales-table td:first-child,
.process-table th:first-child,
.process-table td:first-child {
  font-weight: 700;
}
@media print {
  body { background: #fff; }
  .page { margin: 0; max-width: none; min-height: auto; padding: 0; border: 0; }
  h1 { margin-top: 0; }
}
"""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>第三章销量分析报告</title>
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
            name="CNTitle",
            parent=styles["Title"],
            fontName=font,
            fontSize=18,
            leading=24,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#3a3d42"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNSection",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=14.5,
            leading=20,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#111111"),
            spaceBefore=7,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBody",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=9.8,
            leading=15.5,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNSubSection",
            parent=styles["Heading3"],
            fontName=font,
            fontSize=11.5,
            leading=16,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#222222"),
            spaceBefore=6,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBullet",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=9.5,
            leading=15,
            leftIndent=10,
            firstLineIndent=0,
            bulletIndent=0,
            bulletFontName=font,
            bulletFontSize=9,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNSubBullet",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=9.8,
            leading=15.5,
            leftIndent=14,
            firstLineIndent=0,
            bulletIndent=2,
            bulletFontName=font,
            bulletFontSize=8.5,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBulletKeep",
            parent=styles["CNBullet"],
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNTable",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=8.2,
            leading=11,
            alignment=TA_CENTER,
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
            story.append(_build_pdf_table(rows, styles, font))
            story.append(Spacer(1, 5 * mm))
            continue

        if line.startswith("# "):
            story.append(Paragraph(_inline_pdf(line[2:]), styles["CNTitle"]))
        elif line.startswith("## "):
            story.append(Paragraph(_inline_pdf(line[3:]), styles["CNSection"]))
        elif line.startswith("### "):
            story.append(Paragraph(_inline_pdf(line[4:]), styles["CNSubSection"]))
        elif line.startswith("  * "):
            story.append(Paragraph(_inline_pdf(line[4:]), styles["CNSubBullet"], bulletText="✧"))
        elif line.startswith("* "):
            style = styles["CNBulletKeep"] if line[2:].startswith("风险指标") else styles["CNBullet"]
            story.append(Paragraph(_inline_pdf(line[2:]), style, bulletText="▶"))
        else:
            story.append(Paragraph(_inline_pdf(line), styles["CNBody"]))
        i += 1

    def page_no(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(A4[0] - 13 * mm, 10 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=PDF_MARGIN,
        leftMargin=PDF_MARGIN,
        topMargin=PDF_MARGIN,
        bottomMargin=PDF_MARGIN,
        title="第三章销量分析报告",
    )
    pdf.build(story, onFirstPage=page_no, onLaterPages=page_no)


def _register_pdf_font() -> str:
    candidates = [
        ("/System/Library/Fonts/Supplemental/NISC18030.ttf", "NISC18030"),
        ("/Library/Fonts/Arial Unicode.ttf", "ArialUnicode"),
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "ArialUnicode"),
    ]
    for font_path, font_name in candidates:
        path = Path(font_path)
        if not path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(font_name, str(path)))
            return font_name
        except Exception:
            continue

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def _build_pdf_table(rows: List[List[str]], styles, font: str) -> Table:
    table_rows = [
        [Paragraph(_inline_pdf(cell), styles["CNTable"]) for cell in row]
        for row in rows
    ]
    col_widths = _pdf_col_widths(rows[0] if rows else [])
    table = Table(table_rows, colWidths=col_widths, repeatRows=1, hAlign="CENTER")

    style_cmds = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111111")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c5c8cc")),
        ("LINEABOVE", (0, 0), (-1, 0), 1.1, colors.HexColor("#111111")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, colors.HexColor("#111111")),
        ("LINEBELOW", (0, -1), (-1, -1), 1.1, colors.HexColor("#111111")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    table.setStyle(TableStyle(style_cmds))
    return table


def _pdf_col_widths(header: List[str]) -> List[float]:
    page_width = A4[0] - 2 * PDF_MARGIN
    col_count = len(header)
    if col_count == 4:
        return [42 * mm, 45 * mm, 45 * mm, page_width - 132 * mm]
    if col_count == 6:
        return [32 * mm, 29 * mm, 29 * mm, 29 * mm, 29 * mm, page_width - 148 * mm]
    if col_count:
        return [page_width / col_count] * col_count
    return [page_width]
