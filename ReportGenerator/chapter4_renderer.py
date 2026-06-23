"""第四章最终版渲染器。

将第四章「毛利率与产品结构」Markdown 输出为客户查看用的 HTML 和 PDF。
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import List, Tuple
import re

from .report_theme import apply_html_theme, colors
from .browser_pdf import html_to_pdf
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PDF_MARGIN = 14 * mm


def save_final_html(markdown: str, output_path: Path) -> Path:
    """保存第四章 HTML 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    return output_path


def save_final_pdf(markdown: str, output_path: Path) -> Path:
    """保存第四章 PDF 文件。"""
    return html_to_pdf(_markdown_to_html(markdown), output_path)


def _inline_html(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace("&lt;br&gt;", "<br>")
    return text.replace(
        '&lt;span class=&quot;missing&quot;&gt;待补充&lt;/span&gt;',
        '<span class="missing">待补充</span>',
    )


def _inline_pdf(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = text.replace("&lt;br&gt;", "<br/>")
    return text.replace(
        '&lt;span class=&quot;missing&quot;&gt;待补充&lt;/span&gt;',
        '<font color="#c00000"><b>待补充</b></font>',
    )


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
            parts.append('<table class="chapter4-table">')
            for row_index, row in enumerate(rows):
                tag = "th" if row_index == 0 else "td"
                cells = "".join(f"<{tag}>{_inline_html(cell)}</{tag}>" for cell in row)
                parts.append(f"<tr>{cells}</tr>")
            parts.append("</table>")
            continue

        if line.startswith("# "):
            parts.append(f"<h1>{_inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            parts.append(f"<h1>{_inline_html(line[3:])}</h1>")
        elif line.startswith("### "):
            parts.append(f"<h2>{_inline_html(line[4:])}</h2>")
        else:
            class_name = ' class="guide"' if line.startswith("◇ ") else ""
            parts.append(f"<p{class_name}>{_inline_html(line)}</p>")
        i += 1

    css = """
:root { color-scheme: light; }
body {
  margin: 0;
  background: #f4f5f7;
  color: #303236;
  font-family: "Microsoft YaHei", "Heiti SC", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  line-height: 1.75;
}
.page {
  box-sizing: border-box;
  max-width: 960px;
  min-height: 100vh;
  margin: 28px auto;
  padding: 34px 36px 46px;
  background: #fff;
  border: 1px solid #d9dde3;
}
h1 {
  margin: 0 0 18px;
  font-size: 25px;
  line-height: 1.3;
  font-weight: 800;
  color: #3a3d42;
}
h2 {
  margin: 62px 0 18px;
  font-size: 21px;
  line-height: 1.35;
  font-weight: 800;
  color: #3a3d42;
}
p {
  margin: 10px 0;
  font-size: 18px;
}
strong {
  font-weight: 800;
}
.missing {
  color: #c00000;
  font-weight: 800;
}
.chapter4-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  margin: 14px 0 64px;
  font-size: 17px;
  border-top: 2px solid #111;
  border-bottom: 2px solid #111;
}
.chapter4-table th,
.chapter4-table td {
  padding: 12px 10px;
  text-align: left;
  vertical-align: middle;
  word-break: break-word;
  border: 1px dashed #bfc3c8;
}
.chapter4-table th {
  background: #d9d9d9;
  color: #111;
  font-weight: 800;
  border-bottom: 2px solid #111;
}
.chapter4-table th:first-child,
.chapter4-table td:first-child {
  width: 100px;
  font-weight: 800;
  color: #111;
}
.chapter4-table tr:last-child td {
  border-bottom: 0;
}
.guide {
  font-size: 19px;
  font-weight: 700;
  color: #3f4247;
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
<title>第四章毛利率与产品结构报告</title>
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
            name="CNTitle4",
            parent=styles["Title"],
            fontName=font,
            fontSize=17,
            leading=23,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#3a3d42"),
            spaceAfter=13,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNGuideTitle4",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=13.5,
            leading=19,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#3a3d42"),
            spaceBefore=24,
            spaceAfter=9,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBody4",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=11,
            leading=17,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNGuide4",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=11.5,
            leading=18,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNTable4",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=9.2,
            leading=14.5,
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
            story.append(_build_pdf_table(rows, styles, font))
            story.append(Spacer(1, 18 * mm))
            continue

        if line.startswith("# "):
            story.append(Paragraph(_inline_pdf(line[2:]), styles["CNTitle4"]))
        elif line.startswith("## "):
            story.append(Paragraph(_inline_pdf(line[3:]), styles["CNTitle4"]))
        elif line.startswith("### "):
            story.append(Paragraph(_inline_pdf(line[4:]), styles["CNGuideTitle4"]))
        elif line.startswith("◇ "):
            story.append(Paragraph(_inline_pdf(line), styles["CNGuide4"]))
        else:
            story.append(Paragraph(_inline_pdf(line), styles["CNBody4"]))
        i += 1

    def page_no(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(A4[0] - PDF_MARGIN, 10 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=PDF_MARGIN,
        leftMargin=PDF_MARGIN,
        topMargin=PDF_MARGIN,
        bottomMargin=PDF_MARGIN,
        title="第四章毛利率与产品结构报告",
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
        [Paragraph(_inline_pdf(cell), styles["CNTable4"]) for cell in row]
        for row in rows
    ]
    page_width = A4[0] - 2 * PDF_MARGIN
    col_widths = [22 * mm, page_width - 22 * mm]
    table = Table(table_rows, colWidths=col_widths, repeatRows=1, hAlign="CENTER")

    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111111")),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#bfc3c8")),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.HexColor("#111111")),
                ("LINEBELOW", (0, 0), (-1, 0), 1.0, colors.HexColor("#111111")),
                ("LINEBELOW", (0, -1), (-1, -1), 1.2, colors.HexColor("#111111")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table
