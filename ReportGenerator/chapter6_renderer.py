"""第六章最终版渲染器。

第六章以段落文本为主，无复杂表格。沿用二期 2/3/4 章的渲染路线：
1. 生成器输出 Markdown。
2. Markdown 渲染为 HTML。
3. Markdown 渲染为 PDF（reportlab）。
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import List, Tuple
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def save_final_html(markdown: str, output_path: Path) -> Path:
    """保存第六章 HTML 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    return output_path


def save_final_pdf(markdown: str, output_path: Path) -> Path:
    """保存第六章 PDF 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _markdown_to_pdf(markdown, output_path)
    return output_path


def _inline_html(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace(
        '&lt;span style=&quot;color:#c00000;font-weight:700&quot;&gt;待补充&lt;/span&gt;',
        '<span class="pending">待补充</span>',
    )
    return text


def _inline_pdf(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = text.replace(
        '&lt;span style=&quot;color:#c00000;font-weight:700&quot;&gt;待补充&lt;/span&gt;',
        '<font color="#c00000"><b>待补充</b></font>',
    )
    return text


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

        if stripped.startswith("<!--"):
            i += 1
            continue

        if line.startswith("# "):
            parts.append(f"<h1>{_inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            parts.append(f"<h2>{_inline_html(line[3:])}</h2>")
        elif line.startswith("### "):
            parts.append(f"<h3>{_inline_html(line[4:])}</h3>")
        elif line.startswith("◇ "):
            parts.append(f'<p class="guide">{_inline_html(line)}</p>')
        else:
            parts.append(f"<p>{_inline_html(line)}</p>")
        i += 1

    css = """
:root { color-scheme: light; }
body {
  margin: 0;
  background: #f3f5f7;
  color: #172033;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
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
h3 { margin: 22px 0 10px; font-size: 18px; color: #244b73; }
p { margin: 7px 0; font-size: 15px; }
p.guide { margin-top: 18px; font-size: 16px; font-weight: 700; color: #111; }
strong { color: #0b5cad; font-weight: 700; }
.pending { color: #c00000; font-weight: 700; }
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
<title>第六章费用分析报告</title>
<style>{css}</style>
</head>
<body><main class="page">{''.join(parts)}</main></body>
</html>
"""


def _markdown_to_pdf(markdown: str, output_path: Path) -> None:
    font = _register_pdf_font()

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CNTitle6",
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
            name="CNSection6",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=14,
            leading=19,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#244b73"),
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBody6",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=10.5,
            leading=17,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNGuide6",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=10.5,
            leading=17,
            spaceBefore=6,
            spaceAfter=6,
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

        if stripped.startswith("<!--"):
            i += 1
            continue

        if line.startswith("# "):
            story.append(Paragraph(_inline_pdf(line[2:]), styles["CNTitle6"]))
        elif line.startswith("## "):
            story.append(Paragraph(_inline_pdf(line[3:]), styles["CNSection6"]))
        elif line.startswith("### "):
            story.append(Paragraph(_inline_pdf(line[4:]), styles["CNSection6"]))
        elif line.startswith("◇ "):
            story.append(Paragraph(_inline_pdf(line), styles["CNGuide6"]))
        else:
            story.append(Paragraph(_inline_pdf(line), styles["CNBody6"]))
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
        title="第六章费用分析报告",
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
