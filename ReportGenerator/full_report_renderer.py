"""完整报告 Markdown/HTML/PDF 渲染器。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path
from typing import List, Tuple
import re

from .report_theme import apply_html_theme, colors
from .browser_pdf import html_to_pdf
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass(frozen=True)
class ReportHeader:
    title: str
    breadcrumb: str
    generated_date: str
    report_range: str


def _extract_report_header(lines: List[str]) -> Tuple[ReportHeader | None, int]:
    """从完整报告开头的 Markdown 元数据中组装一期式页眉。"""
    first = _next_non_empty_index(lines, 0)
    if first >= len(lines) or not lines[first].startswith("# "):
        return None, 0

    next_heading = first + 1
    while next_heading < len(lines) and not lines[next_heading].startswith("# "):
        next_heading += 1
    if next_heading >= len(lines):
        return None, 0

    metadata = [line.strip() for line in lines[first + 1 : next_heading] if line.strip()]
    employee_name = ""
    organization = ""
    period_text = ""
    for line in metadata:
        if line.startswith("姓名："):
            employee_name = line.split("：", 1)[1].strip()
        elif line.startswith("组织："):
            organization = line.split("：", 1)[1].strip()
        match = re.search(r"(\d{4}年1-\d{1,2}月)", line)
        if match:
            period_text = match.group(1)

    if not period_text:
        compact_period = re.search(r"(\d{4})(\d{2})", lines[first])
        if compact_period:
            year, month = compact_period.groups()
            period_text = f"{year}年1-{int(month)}月"

    if not organization or not period_text:
        return None, 0

    breadcrumb = " > ".join(part.strip() for part in organization.split("/") if part.strip())
    if employee_name:
        breadcrumb = f"{breadcrumb} {employee_name}"

    header = ReportHeader(
        title=f"{period_text}经营分析报告",
        breadcrumb=breadcrumb,
        generated_date=date.today().strftime("%Y/%m/%d"),
        report_range=period_text,
    )
    return header, next_heading


def _report_header_html(header: ReportHeader) -> str:
    return (
        '<header class="report-header">'
        '<div class="report-header-main">'
        '<div class="report-header-left">'
        f'<div class="report-header-title">{escape(header.title)}</div>'
        f'<div class="report-header-breadcrumb">{escape(header.breadcrumb)}</div>'
        "</div>"
        '<div class="report-header-meta">'
        f'<div>日期：{escape(header.generated_date)}</div>'
        f'<div>范围：{escape(header.report_range)}</div>'
        "</div></div></header>"
    )


def save_full_html(markdown: str, output_path: Path, title: str = "经营分析报告") -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown_to_html(markdown, title=title), encoding="utf-8")
    return output_path


def save_full_pdf(markdown: str, output_path: Path, title: str = "经营分析报告") -> Path:
    return html_to_pdf(markdown_to_html(markdown, title=title), output_path)


def _inline_html(text: str) -> str:
    nested_bullet = bool(re.match(r"^\s{2,}\* ", text))
    text = text.strip()
    if nested_bullet:
        text = text[2:]
    elif text.startswith("* "):
        text = "- " + text[2:]
    text = re.sub(r"<span\b[^>]*>(.*?)</span>", r"\1", text)
    text = escape(text)
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace("待补充", '<span class="missing">待补充</span>')
    return text.replace("&lt;br&gt;", "<br>")


def _inline_pdf(text: str) -> str:
    nested_bullet = bool(re.match(r"^\s{2,}\* ", text))
    text = text.strip()
    if nested_bullet:
        text = text[2:]
    elif text.startswith("* "):
        text = "- " + text[2:]
    text = re.sub(r"<span\b[^>]*>(.*?)</span>", r"\1", text)
    text = escape(text).replace("&lt;br&gt;", "<br/>")
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    return text.replace("待补充", '<font color="#c00000"><b>待补充</b></font>')


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
    """识别客户范本中的绩效/销量/利润排名摘要表。"""
    if not rows:
        return "report-table"
    header = rows[0]
    if "绩效排名" in header and any("分摊前利润" in cell for cell in header):
        return "report-table rank-table"
    return "report-table"


def _is_action_guide_heading(line: str) -> bool:
    label = line.lstrip("#").strip().rstrip("：:").strip()
    return label == "行动指南"


def _clean_action_line(line: str) -> str:
    text = line.strip()
    if text.startswith("◇"):
        text = text[1:].strip()
    return text


def _collect_action_guide(lines: List[str], start: int) -> Tuple[List[str], int]:
    """收集一个行动指南标题之后、下一个标题之前的内容。"""
    items: List[str] = []
    i = start + 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            break
        if stripped.startswith("<!--"):
            i += 1
            continue
        if stripped:
            items.append(_clean_action_line(stripped))
        i += 1
    return items, i


def _inline_action_text(line: str) -> str | None:
    stripped = line.strip()
    match = re.match(r"^\*\s*行动指南[：:]\s*(.+)$", stripped)
    return match.group(1).strip() if match else None


def _action_guide_html(items: List[str]) -> str:
    content = "".join(f"<p>{_inline_html(item)}</p>" for item in items)
    return f'<section class="action-guide"><div class="action-guide-title">行动指南：</div>{content}</section>'


def _parse_summary(lines: List[str], start: int) -> Tuple[str, str, List[str]]:
    advantage = ""
    shortcoming = ""
    strategies: List[str] = []
    mode = ""
    for raw in lines[start:]:
        text = raw.strip()
        if not text:
            continue
        if text.startswith("优势："):
            advantage = text.split("：", 1)[1].strip()
            mode = "advantage"
        elif text.startswith("短板："):
            shortcoming = text.split("：", 1)[1].strip()
            mode = "shortcoming"
        elif text.rstrip("：:") == "核心策略":
            mode = "strategy"
        elif mode == "strategy":
            strategies.append(text)
    return advantage, shortcoming, strategies


def _summary_html(advantage: str, shortcoming: str, strategies: List[str]) -> str:
    strategy_html = "".join(f"<p>{_inline_html(item)}</p>" for item in strategies)
    return (
        '<section class="summary-group"><h1>八、总结</h1>'
        '<section class="summary-item summary-advantage"><h3>核心优势</h3>'
        f'<p>{_inline_html(advantage)}</p></section>'
        '<section class="summary-item summary-shortcoming"><h3>关键短板</h3>'
        f'<p>{_inline_html(shortcoming)}</p></section>'
        '<section class="summary-item summary-strategy"><h3>核心策略</h3>'
        f'{strategy_html}</section></section>'
    )


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


def _next_non_empty_index(lines: List[str], start: int) -> int:
    i = start
    while i < len(lines) and not lines[i].strip():
        i += 1
    return i


def _append_receivable_chart(
    story: List,
    lines: List[str],
    start: int,
    font: str,
    available_width: float,
) -> int:
    try:
        from ReportGenerator.chapter5_renderer import (
            _build_pdf_receivable_chart,
            _build_tree,
            _parse_tree,
        )
    except Exception:
        return start

    tree_lines, next_index = _parse_tree(lines, start)
    root = _build_tree(tree_lines)
    if not root:
        return start

    story.append(_build_pdf_receivable_chart(root, font, available_width=available_width))
    story.append(Spacer(1, 6))
    return next_index


def markdown_to_html(markdown: str, title: str = "经营分析报告") -> str:
    lines = markdown.splitlines()
    parts: List[str] = []
    report_header, content_start = _extract_report_header(lines)
    if report_header:
        parts.append(_report_header_html(report_header))
    i = content_start
    skip_receivable_note = False

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped == "应收款项结构：":
            parts.append(f"<p>{_inline_html(stripped)}</p>")
            tree_start = _next_non_empty_index(lines, i + 1)
            if tree_start < len(lines) and lines[tree_start].strip().startswith("- "):
                try:
                    from ReportGenerator.chapter5_renderer import _parse_tree, _tree_to_html

                    tree_lines, i = _parse_tree(lines, tree_start)
                    parts.append(_tree_to_html(tree_lines))
                    skip_receivable_note = True
                    continue
                except Exception:
                    pass

        if skip_receivable_note and stripped.startswith("备注：") and "逾期金额含诉讼" in stripped:
            skip_receivable_note = False
            i += 1
            continue

        inline_action = _inline_action_text(stripped)
        if inline_action:
            parts.append(_action_guide_html([inline_action]))
            i += 1
            continue

        if _is_action_guide_heading(stripped):
            action_items, i = _collect_action_guide(lines, i)
            parts.append(_action_guide_html(action_items))
            continue

        if stripped == "## 八、总结":
            advantage, shortcoming, strategies = _parse_summary(lines, i + 1)
            parts.append(_summary_html(advantage, shortcoming, strategies))
            break

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
        elif line.startswith("◇ "):
            parts.append(f'<p class="guide">{_inline_html(line)}</p>')
        elif line.startswith("<!--"):
            pass
        else:
            parts.append(f"<p>{_inline_html(line)}</p>")
        i += 1

    css = """
body {
  margin: 0;
  background: #f4f6f8;
  color: #18202a;
  font-family: "Microsoft YaHei", "Heiti SC", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  line-height: 1.72;
}
.page {
  box-sizing: border-box;
  max-width: 980px;
  margin: 28px auto;
  padding: 42px 50px 56px;
  background: #fff;
  border: 1px solid #d8dee6;
}
.report-header {
  margin: 0 0 28px;
  padding: 0 0 15px;
  border-bottom: 3px solid #2E7D32;
}
.report-header-main {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
}
.report-header-left { min-width: 0; }
.report-header-title {
  margin: 0 0 7px;
  color: #2E7D32;
  font-size: 25px;
  line-height: 1.3;
  font-weight: 500;
}
.report-header-breadcrumb {
  color: #2E7D32;
  font-size: 13px;
  line-height: 1.5;
}
.report-header-meta {
  flex: 0 0 auto;
  color: #666666;
  font-size: 13px;
  line-height: 1.7;
  text-align: right;
}
h1 { margin: 8px 0 24px; font-size: 28px; line-height: 1.3; color: #15293f; }
h2 { margin: 32px 0 14px; padding-bottom: 7px; border-bottom: 2px solid #d8e1ea; font-size: 22px; color: #15293f; }
h3 { margin: 24px 0 10px; font-size: 18px; color: #1f3348; }
p { margin: 7px 0; font-size: 15px; }
p.guide { padding-left: 4px; }
p.comment { color: #6b7280; font-size: 13px; }
strong { font-weight: 800; color: #0b5cad; }
.missing { color: #c00000; font-weight: 800; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; margin: 12px 0 24px; font-size: 13.5px; }
th, td { border: 1px solid #ccd6e0; padding: 8px 9px; vertical-align: middle; word-break: break-word; }
th { background: #eef3f7; color: #132940; font-weight: 800; }
tr:nth-child(even) td { background: #fbfcfd; }
.receivable-chart { position: relative; width: 100%; height: 455px; margin: 18px 0 8px; }
.chart-lines { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.chart-line { stroke: #b8c1ca; stroke-width: 2; fill: none; }
.chart-node {
  position: absolute;
  min-width: 118px;
  min-height: 52px;
  padding: 9px 14px;
  border-radius: 4px;
  background: #c8f1b8;
  color: #1c2f1a;
  font-size: 14px;
  line-height: 1.25;
  font-weight: 800;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: pre-line;
}
.chart-node.root { min-width: 145px; min-height: 82px; background: #75dc4f; font-size: 16px; }
.chart-node.overdue { color: #d64242; }
.chart-note { position: absolute; right: 128px; bottom: 10px; font-size: 13px; color: #111; }
.tree-fallback { display: flex; align-items: center; gap: 12px; margin: 10px 0; }
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
<style>{apply_html_theme(css)}</style>
</head>
<body><main class="page">{''.join(parts)}</main></body>
</html>
"""


def markdown_to_pdf(markdown: str, output_path: Path, title: str = "经营分析报告") -> None:
    font = _register_pdf_font()

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CNTitle", parent=styles["Title"], fontName=font, fontSize=18, leading=25, alignment=TA_LEFT, textColor=colors.HexColor("#15293f"), spaceAfter=10))
    styles.add(ParagraphStyle(name="CNHeading2", parent=styles["Heading2"], fontName=font, fontSize=14, leading=20, textColor=colors.HexColor("#15293f"), spaceBefore=8, spaceAfter=6))
    styles.add(ParagraphStyle(name="CNHeading3", parent=styles["Heading3"], fontName=font, fontSize=12, leading=18, textColor=colors.HexColor("#1f3348"), spaceBefore=6, spaceAfter=4))
    styles.add(ParagraphStyle(name="CNBody", parent=styles["BodyText"], fontName=font, fontSize=9.8, leading=16, spaceAfter=4))
    styles.add(ParagraphStyle(name="CNTable", parent=styles["BodyText"], fontName=font, fontSize=7.6, leading=10))
    styles.add(ParagraphStyle(name="CNHeaderTitle", parent=styles["BodyText"], fontName=font, fontSize=17, leading=22, textColor=colors.HexColor("#2E7D32"), spaceAfter=4))
    styles.add(ParagraphStyle(name="CNHeaderPath", parent=styles["BodyText"], fontName=font, fontSize=8.4, leading=12, textColor=colors.HexColor("#2E7D32")))
    styles.add(ParagraphStyle(name="CNHeaderMeta", parent=styles["BodyText"], fontName=font, fontSize=8.4, leading=12, alignment=TA_RIGHT, textColor=colors.HexColor("#666666")))
    styles.add(ParagraphStyle(name="CNCalloutTitle", parent=styles["BodyText"], fontName=font, fontSize=9.2, leading=13, textColor=colors.black, spaceAfter=3))
    styles.add(ParagraphStyle(name="CNCalloutBody", parent=styles["BodyText"], fontName=font, fontSize=8.2, leading=12, textColor=colors.HexColor("#333333"), spaceAfter=2))

    doc = SimpleDocTemplate(str(output_path), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title=title)
    story = []
    lines = markdown.splitlines()
    report_header, content_start = _extract_report_header(lines)
    i = content_start
    max_width = A4[0] - 24 * mm
    skip_receivable_note = False

    if report_header:
        header_table = Table(
            [[
                [
                    Paragraph(_inline_pdf(report_header.title), styles["CNHeaderTitle"]),
                    Paragraph(_inline_pdf(report_header.breadcrumb), styles["CNHeaderPath"]),
                ],
                [
                    Paragraph(f"日期：{_inline_pdf(report_header.generated_date)}", styles["CNHeaderMeta"]),
                    Paragraph(f"范围：{_inline_pdf(report_header.report_range)}", styles["CNHeaderMeta"]),
                ],
            ]],
            colWidths=[max_width * 0.76, max_width * 0.24],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(header_table)
        story.append(Spacer(1, 5))
        story.append(HRFlowable(width="100%", thickness=1.6, color=colors.HexColor("#2E7D32"), spaceBefore=0, spaceAfter=12))

    def append_callout(items: List[str], background: str, accent: str, label: str) -> None:
        content = [Paragraph(f"<b>{_inline_pdf(label)}</b>", styles["CNCalloutTitle"])]
        content.extend(Paragraph(_inline_pdf(item), styles["CNCalloutBody"]) for item in items)
        callout = Table([[content]], colWidths=[max_width])
        callout.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(accent)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(callout)
        story.append(Spacer(1, 7))

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if skip_receivable_note and stripped.startswith("备注：") and "逾期金额含诉讼" in stripped:
            skip_receivable_note = False
            i += 1
            continue

        inline_action = _inline_action_text(stripped)
        if inline_action:
            append_callout([inline_action], "#FFF8E1", "#FFA000", "行动指南：")
            i += 1
            continue

        if _is_action_guide_heading(stripped):
            action_items, i = _collect_action_guide(lines, i)
            append_callout(action_items, "#FFF8E1", "#FFA000", "行动指南：")
            continue

        if stripped == "## 八、总结":
            story.append(Paragraph("八、总结", styles["CNTitle"]))
            advantage, shortcoming, strategies = _parse_summary(lines, i + 1)
            append_callout([advantage], "#E3F2FD", "#0D47A1", "核心优势")
            append_callout([shortcoming], "#FFEBEE", "#B71C1C", "关键短板")
            append_callout(strategies, "#FFF3E0", "#E65100", "核心策略")
            break

        if stripped == "应收款项结构：":
            story.append(Paragraph(_inline_pdf(stripped), styles["CNBody"]))
            tree_start = _next_non_empty_index(lines, i + 1)
            if tree_start < len(lines) and lines[tree_start].strip().startswith("- "):
                i = _append_receivable_chart(story, lines, tree_start, font, max_width)
                skip_receivable_note = True
                continue

        if line.startswith("|"):
            rows, i = _parse_markdown_table(lines, i)
            if rows:
                col_count = max(len(row) for row in rows)
                col_width = max_width / max(col_count, 1)
                table_rows = [
                    [Paragraph(_inline_pdf(cell), styles["CNTable"]) for cell in row + [""] * (col_count - len(row))]
                    for row in rows
                ]
                table_type = _table_class(rows)
                if "rank-table" in table_type and col_count == 4:
                    col_widths = [max_width * 0.18] + [max_width * (0.82 / 3)] * 3
                else:
                    col_widths = [col_width] * col_count
                table = Table(table_rows, colWidths=col_widths, repeatRows=1)
                if "rank-table" in table_type:
                    table_style = [
                        ("FONTNAME", (0, 0), (-1, -1), font),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F8E9")),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (0, -1), "LEFT"),
                        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, 0), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                        ("TOPPADDING", (0, 1), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
                    ]
                else:
                    table_style = [
                        ("FONTNAME", (0, 0), (-1, -1), font),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#ccd6e0")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D32")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                table.setStyle(TableStyle(table_style))
                story.append(table)
                story.append(Spacer(1, 6))
            continue

        if line.startswith("# "):
            heading = Table([[Paragraph(_inline_pdf(line[2:]), styles["CNTitle"])]], colWidths=[max_width])
            heading.setStyle(TableStyle([
                ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#66BB6A")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(heading)
        elif line.startswith("## "):
            story.append(Paragraph(_inline_pdf(line[3:]), styles["CNHeading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(_inline_pdf(line[4:]), styles["CNHeading3"]))
        else:
            story.append(Paragraph(_inline_pdf(line), styles["CNBody"]))
        i += 1

    doc.build(story)
