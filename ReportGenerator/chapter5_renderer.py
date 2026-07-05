"""第五章最终版渲染器。

第五章沿用二期 2/3/4 章的依赖路线：

1. 生成器输出 Markdown。
2. Markdown 渲染为 HTML，用 HTML/CSS 承载横向应收树和表格样式。
3. Markdown 渲染为 PDF，用 reportlab 生成同内容 PDF，不额外引入 Chrome。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from .report_theme import apply_html_theme, colors
from .browser_pdf import html_to_pdf
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_SIZE = landscape(A4)
PDF_MARGIN = 11 * mm


@dataclass
class TreeNode:
    text: str
    children: List["TreeNode"] = field(default_factory=list)


def save_final_html(markdown: str, output_path: Path) -> Path:
    """保存第五章 HTML 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    return output_path


def save_final_pdf(markdown: str, output_path: Path) -> Path:
    """保存第五章 PDF 文件。"""
    return html_to_pdf(_markdown_to_html(markdown), output_path)


def _inline_html(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace(
        '&lt;span style=&quot;color:#c00000&quot;&gt;待补充&lt;/span&gt;',
        '<span class="pending">待补充</span>',
    )
    return text.replace("&lt;br&gt;", "<br>")


def _inline_pdf(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = text.replace(
        '&lt;span style=&quot;color:#c00000&quot;&gt;待补充&lt;/span&gt;',
        '<font color="#c00000">待补充</font>',
    )
    return text.replace("&lt;br&gt;", "<br/>")


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


def _parse_tree(lines: List[str], start: int) -> Tuple[List[Tuple[int, str]], int]:
    tree_lines: List[Tuple[int, str]] = []
    i = start
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        depth = max((len(line) - len(line.lstrip(" "))) // 2, 0)
        tree_lines.append((depth, stripped[2:].strip()))
        i += 1
    return tree_lines, i


def _table_class(rows: List[List[str]]) -> str:
    if not rows:
        return "data-table"
    col_count = len(rows[0])
    if _is_aging_jump_table(rows):
        return "data-table wide-table grouped-table"
    if col_count >= 8:
        return "data-table wide-table"
    if rows[0][:3] == ["客户名称", "应收账款", "其中：逾期账款"]:
        return "data-table overdue-table"
    return "data-table"


def _is_aging_jump_table(rows: List[List[str]]) -> bool:
    return len(rows) >= 2 and rows[0][:2] == ["账龄跳到", "净增加减值金额"] and rows[1][:2] == ["客户名称", "额"]


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
            parts.append(f'<div class="table-wrap"><table class="{_table_class(rows)}">')
            if _is_aging_jump_table(rows):
                parts.extend(_aging_jump_table_rows_html(rows))
            else:
                for row_index, row in enumerate(rows):
                    tag = "th" if row_index == 0 else "td"
                    cells = "".join(f"<{tag}>{_inline_html(cell)}</{tag}>" for cell in row)
                    parts.append(f"<tr>{cells}</tr>")
            parts.append("</table></div>")
            continue

        if stripped.startswith("- "):
            tree_lines, i = _parse_tree(lines, i)
            parts.append(_tree_to_html(tree_lines))
            continue

        if line.startswith("# "):
            parts.append(f"<h1>{_inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            parts.append(f"<h2>{_inline_html(line[3:])}</h2>")
        elif line.startswith("### "):
            parts.append(f"<h3>{_inline_html(line[4:])}</h3>")
        elif line.startswith("◇ "):
            parts.append(f'<p class="guide">{_inline_html(line)}</p>')
        elif line.startswith("备注：") and "逾期金额含诉讼" in line:
            # 5.1 的备注放在横向树图右下，避免图外重复一遍。
            pass
        elif line.startswith("备注："):
            parts.append(f'<p class="note">{_inline_html(line)}</p>')
        else:
            parts.append(f"<p>{_inline_html(line)}</p>")
        i += 1

    css = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #f4f5f7;
  color: #303236;
  font-family: "Microsoft YaHei", "Heiti SC", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  line-height: 1.72;
}
.page {
  width: 1160px;
  min-height: 100vh;
  margin: 28px auto;
  padding: 34px 36px 48px;
  background: #fff;
  border: 1px solid #d9dde3;
}
h1 {
  margin: 0 0 24px;
  font-size: 27px;
  line-height: 1.3;
  font-weight: 800;
  color: #3a3d42;
}
h2 {
  margin: 28px 0 16px;
  font-size: 22px;
  line-height: 1.35;
  font-weight: 800;
  color: #3a3d42;
}
h3 {
  margin: 34px 0 12px;
  font-size: 19px;
  font-weight: 800;
}
p {
  margin: 8px 0;
  font-size: 16px;
}
strong {
  font-weight: 800;
}
.pending {
  color: #c00000;
  font-weight: 800;
}
.guide {
  margin-top: 18px;
  font-size: 17px;
  font-weight: 800;
  color: #111;
}
.note {
  margin: 8px 0 18px;
  font-size: 14px;
  color: #333;
}
.receivable-chart { width: 1088px; margin: 8px 0 6px; }
.receivable-diagram { display: block; width: 1088px; height: 430px; }
.chart-line {
  stroke: #b8c1ca;
  stroke-width: 2;
  fill: none;
}
.chart-node-svg rect { fill: #c8f1b8; stroke: #c8f1b8; }
.chart-node-svg.root rect { fill: #75dc4f; stroke: #75dc4f; }
.chart-node-svg text { fill: #1c2f1a; font-weight: 800; }
.chart-node-svg.overdue text { fill: #d64242; }
.chart-note-svg { fill: #111; font-size: 13px; }
.chart-node {
  position: absolute;
  width: 118px;
  height: 45px;
  padding: 0 8px;
  box-sizing: border-box;
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
.chart-node.root {
  width: 145px;
  height: 70px;
  background: #75dc4f;
  font-size: 16px;
}
.chart-node.overdue {
  color: #d64242;
}
.chart-note {
  position: absolute;
  right: 128px;
  bottom: 10px;
  font-size: 13px;
  color: #111;
}
.tree-fallback {
  display: flex;
  flex-direction: row;
  align-items: center;
  min-height: 190px;
  gap: 34px;
}
.table-wrap {
  width: 100%;
  overflow-x: auto;
  margin: 10px 0 24px;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 15px;
  border-top: 2px solid #111;
  border-bottom: 2px solid #111;
}
.wide-table {
  min-width: 1120px;
  font-size: 13px;
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
  font-weight: 800;
  color: #111;
  border-bottom: 2px solid #111;
}
.grouped-table thead tr:first-child th {
  font-size: 15px;
}
.grouped-table thead tr:nth-child(2) th {
  border-bottom: 2px solid #111;
}
.data-table tr:last-child td {
  border-bottom: 0;
}
@media print {
  @page { size: A4 landscape; margin: 10mm; }
  body { background: #fff; }
  .page {
    width: auto;
    margin: 0;
    min-height: auto;
    padding: 0;
    border: 0;
  }
  .table-wrap { overflow: visible; }
  .wide-table { min-width: 0; font-size: 10px; }
}
"""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>第五章应收分析报告</title>
<style>{apply_html_theme(css)}</style>
</head>
<body><main class="page">{''.join(parts)}</main></body>
</html>
"""


def _tree_to_html(tree_lines: List[Tuple[int, str]]) -> str:
    root = _build_tree(tree_lines)
    if not root:
        return ""
    chart = _fixed_receivable_chart(root)
    if chart:
        return chart
    return _fallback_tree_html(root)


def _aging_jump_table_rows_html(rows: List[List[str]]) -> List[str]:
    header_1, header_2 = rows[0], rows[1]
    html_rows = [
        "<thead><tr>"
        f"<th>{_inline_html(header_1[0])}</th>"
        f"<th>{_inline_html(header_1[1])}</th>"
        f'<th colspan="2">{_inline_html(header_1[2])}</th>'
        f'<th colspan="2">{_inline_html(header_1[4])}</th>'
        f'<th colspan="2">{_inline_html(header_1[6])}</th>'
        "</tr>",
        "<tr>"
        + "".join(f"<th>{_inline_html(cell)}</th>" for cell in header_2)
        + "</tr></thead><tbody>",
    ]
    for row in rows[2:]:
        html_rows.append("<tr>" + "".join(f"<td>{_inline_html(cell)}</td>" for cell in row) + "</tr>")
    html_rows.append("</tbody>")
    return html_rows


def _build_tree(tree_lines: List[Tuple[int, str]]) -> Optional[TreeNode]:
    stack: List[Tuple[int, TreeNode]] = []
    root: Optional[TreeNode] = None
    for depth, text in tree_lines:
        node = TreeNode(text=text)
        if depth == 0 or not stack:
            root = node
            stack = [(depth, node)]
            continue
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            stack[-1][1].children.append(node)
        stack.append((depth, node))
    return root


def _fixed_receivable_chart(root: TreeNode) -> str:
    nodes = _flatten_tree(root)
    labels = {key: _node_text(nodes, key) for key in (
        "应收款项",
        "应收账款",
        "应收票据",
        "保证金",
        "供应链票证",
        "经销",
        "直销",
        "暴雷直销应收",
        "非暴雷直销应收",
    )}
    overdue_labels = _receivable_overdue_labels(root)
    if not labels["应收款项"] or not labels["应收账款"]:
        return ""

    positions, lines = _receivable_chart_geometry(labels, overdue_labels)
    svg_lines = "".join(
        f'<path class="chart-line" d="M{x1},{y1} L{x2},{y2}" />'
        for x1, y1, x2, y2 in lines
    )
    svg_nodes = []
    for left, top, width, height, text, class_name in positions.values():
        if not text:
            continue
        label_lines = _chart_label(text).split("\n")
        font_size = 19 if class_name == "root" else 17
        line_height = font_size * 1.18
        first_y = top + height / 2 - (len(label_lines) - 1) * line_height / 2 + font_size * 0.34
        tspans = "".join(
            f'<tspan x="{left + width / 2}" y="{first_y + index * line_height}">{escape(label)}</tspan>'
            for index, label in enumerate(label_lines)
        )
        svg_nodes.append(
            f'<g class="chart-node-svg {class_name}">'
            f'<rect x="{left}" y="{top}" width="{width}" height="{height}" rx="5" ry="5" />'
            f'<text text-anchor="middle" font-size="{font_size}">{tspans}</text></g>'
        )
    return (
        '<div class="receivable-chart">'
        f'<svg class="receivable-diagram" viewBox="0 0 1088 430" preserveAspectRatio="xMidYMid meet">'
        f'{svg_lines}{"".join(svg_nodes)}'
        '<text class="chart-note-svg" x="650" y="418">备注：逾期金额含诉讼，保证金不含保函</text>'
        '</svg>'
        + "</div>"
    )


def _receivable_chart_geometry(labels: Dict[str, str], overdue_labels: Dict[str, str]):
    """返回5.1共享布局；节点尺寸与连线锚点使用同一坐标系。"""
    positions = {
        "root": (20, 176, 170, 78, labels["应收款项"], "root"),
        "receivable": (245, 74, 145, 58, labels["应收账款"], ""),
        "note": (245, 164, 145, 58, labels["应收票据"], ""),
        "deposit": (245, 254, 145, 58, labels["保证金"], ""),
        "supply": (245, 344, 145, 58, labels["供应链票证"], ""),
        "dealer": (450, 30, 135, 58, labels["经销"], ""),
        "dealer_overdue": (615, 30, 150, 58, overdue_labels.get("dealer", ""), "overdue"),
        "direct": (450, 164, 135, 58, labels["直销"], ""),
        "storm": (615, 134, 150, 58, labels["暴雷直销应收"], ""),
        "storm_overdue": (805, 134, 130, 58, overdue_labels.get("storm", ""), "overdue"),
        "normal": (615, 264, 150, 58, labels["非暴雷直销应收"], ""),
        "normal_overdue": (805, 264, 130, 58, overdue_labels.get("normal", ""), "overdue"),
    }

    def left(key):
        return positions[key][0]

    def right(key):
        return positions[key][0] + positions[key][2]

    def center_y(key):
        return positions[key][1] + positions[key][3] / 2

    primary_trunk = 220
    account_trunk = 420
    direct_trunk = 600
    lines = [
        (right("root"), center_y("root"), primary_trunk, center_y("root")),
        (primary_trunk, center_y("receivable"), primary_trunk, center_y("supply")),
        *[(primary_trunk, center_y(key), left(key), center_y(key)) for key in ("receivable", "note", "deposit", "supply")],
        (right("receivable"), center_y("receivable"), account_trunk, center_y("receivable")),
        (account_trunk, center_y("dealer"), account_trunk, center_y("direct")),
        (account_trunk, center_y("dealer"), left("dealer"), center_y("dealer")),
        (account_trunk, center_y("direct"), left("direct"), center_y("direct")),
        (right("dealer"), center_y("dealer"), left("dealer_overdue"), center_y("dealer_overdue")),
        (right("direct"), center_y("direct"), direct_trunk, center_y("direct")),
        (direct_trunk, center_y("storm"), direct_trunk, center_y("normal")),
        (direct_trunk, center_y("storm"), left("storm"), center_y("storm")),
        (direct_trunk, center_y("normal"), left("normal"), center_y("normal")),
        (right("storm"), center_y("storm"), left("storm_overdue"), center_y("storm_overdue")),
        (right("normal"), center_y("normal"), left("normal_overdue"), center_y("normal_overdue")),
    ]
    return positions, lines


def _flatten_tree(root: TreeNode) -> List[TreeNode]:
    result = [root]
    for child in root.children:
        result.extend(_flatten_tree(child))
    return result


def _node_text(nodes: List[TreeNode], keyword: str) -> str:
    for node in nodes:
        if _node_label(node.text) == keyword:
            return node.text
    return ""


def _receivable_overdue_labels(root: TreeNode) -> Dict[str, str]:
    return {
        "dealer": _node_text_by_path(root, ("应收款项", "应收账款", "经销", "逾期（含诉讼）")),
        "storm": _node_text_by_path(root, ("应收款项", "应收账款", "直销", "暴雷直销应收", "逾期")),
        "normal": _node_text_by_path(root, ("应收款项", "应收账款", "直销", "非暴雷直销应收", "逾期")),
    }


def _node_text_by_path(root: TreeNode, path: Tuple[str, ...]) -> str:
    if not path or _node_label(root.text) != path[0]:
        return ""
    node = root
    for label in path[1:]:
        next_node = next((child for child in node.children if _node_label(child.text) == label), None)
        if next_node is None:
            return ""
        node = next_node
    return node.text


def _node_label(text: str) -> str:
    parts = text.rsplit(" ", 1)
    if len(parts) == 2 and re.search(r"\d", parts[1]):
        return parts[0]
    return text


def _chart_label(text: str) -> str:
    parts = text.rsplit(" ", 1)
    if len(parts) == 2 and re.search(r"\d", parts[1]):
        return parts[0] + "\n" + parts[1]
    return text


def _fallback_tree_html(root: TreeNode) -> str:
    def render(node: TreeNode) -> str:
        children = "".join(render(child) for child in node.children)
        node_class = "chart-node overdue" if "逾期" in node.text else "chart-node"
        if children:
            return f'<div class="tree-fallback"><div class="{node_class}">{_inline_html(_chart_label(node.text))}</div><div>{children}</div></div>'
        return f'<div class="{node_class}">{_inline_html(_chart_label(node.text))}</div>'

    return '<div class="receivable-chart">' + render(root) + "</div>"


def _markdown_to_pdf(markdown: str, output_path: Path) -> None:
    font = _register_pdf_font()

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CNTitle5",
            parent=styles["Title"],
            fontName=font,
            fontSize=18,
            leading=24,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#3a3d42"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNSection5",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=15,
            leading=20,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#3a3d42"),
            spaceBefore=9,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNSubTitle5",
            parent=styles["Heading3"],
            fontName=font,
            fontSize=12.5,
            leading=17,
            alignment=TA_LEFT,
            spaceBefore=8,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBody5",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=10,
            leading=14,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNGuide5",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=10.5,
            leading=15,
            spaceBefore=5,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNTable5",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=7.8,
            leading=10.2,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNTableSmall5",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=6.4,
            leading=8.2,
            alignment=TA_CENTER,
        )
    )

    story = []
    lines = markdown.splitlines()
    i = 0
    pending_table_heading = None
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("|"):
            rows, i = _parse_markdown_table(lines, i)
            table_group = [_build_pdf_table(rows, styles, font), Spacer(1, 3.2 * mm)]
            if pending_table_heading is not None:
                table_group.insert(0, pending_table_heading)
                pending_table_heading = None
                story.append(KeepTogether(table_group))
            else:
                story.extend(table_group)
            continue

        if stripped.startswith("- "):
            tree_lines, i = _parse_tree(lines, i)
            root = _build_tree(tree_lines)
            if root:
                story.append(_build_pdf_receivable_chart(root, font))
                story.append(Spacer(1, 3.2 * mm))
            continue

        if line.startswith("# "):
            story.append(Paragraph(_inline_pdf(line[2:]), styles["CNTitle5"]))
        elif line.startswith("## "):
            if line.startswith("## 5.2"):
                story.append(CondPageBreak(55 * mm))
            story.append(Paragraph(_inline_pdf(line[3:]), styles["CNSection5"]))
        elif line.startswith("### "):
            story.append(Paragraph(_inline_pdf(line[4:]), styles["CNSubTitle5"]))
        elif line.startswith("◇ "):
            guide = Paragraph(_inline_pdf(line), styles["CNGuide5"])
            if _next_content_is_table(lines, i + 1):
                pending_table_heading = guide
            else:
                story.append(guide)
        elif line.startswith("备注：") and "逾期金额含诉讼" in line:
            # PDF 树图中已包含 5.1 备注。
            pass
        elif stripped in {"应收款项结构："}:
            pass
        else:
            story.append(Paragraph(_inline_pdf(line), styles["CNBody5"]))
        i += 1

    def page_no(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(PAGE_SIZE[0] - PDF_MARGIN, 8 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        str(output_path),
        pagesize=PAGE_SIZE,
        rightMargin=PDF_MARGIN,
        leftMargin=PDF_MARGIN,
        topMargin=PDF_MARGIN,
        bottomMargin=PDF_MARGIN,
        title="第五章应收分析报告",
    )
    pdf.build(story, onFirstPage=page_no, onLaterPages=page_no)


def _next_content_is_table(lines: List[str], start: int) -> bool:
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        return stripped.startswith("|")
    return False


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


def _build_pdf_receivable_chart(root: TreeNode, font: str, available_width: Optional[float] = None) -> Drawing:
    nodes = _flatten_tree(root)
    labels = {key: _node_text(nodes, key) for key in (
        "应收款项",
        "应收账款",
        "应收票据",
        "保证金",
        "供应链票证",
        "经销",
        "直销",
        "暴雷直销应收",
        "非暴雷直销应收",
    )}
    overdue_labels = _receivable_overdue_labels(root)
    positions, lines = _receivable_chart_geometry(labels, overdue_labels)

    page_width = available_width if available_width is not None else PAGE_SIZE[0] - 2 * PDF_MARGIN
    width = page_width * 0.96
    height = 89 * mm
    scale_x = width / 1088
    scale_y = height / 430

    drawing = Drawing(width, height)

    def sx(value: float) -> float:
        return value * scale_x

    def sy(value: float) -> float:
        return height - value * scale_y

    def add_line(x1, y1, x2, y2):
        drawing.add(Line(sx(x1), sy(y1), sx(x2), sy(y2), strokeColor=colors.HexColor("#b8c1ca"), strokeWidth=1.2))

    def add_node(left, top, node_width, node_height, text, class_name=""):
        if not text:
            return
        x = sx(left)
        y = sy(top + node_height)
        fill = colors.HexColor("#75dc4f") if class_name == "root" else colors.HexColor("#c8f1b8")
        text_color = colors.HexColor("#d64242") if class_name == "overdue" else colors.HexColor("#1c2f1a")
        drawing.add(
            Rect(
                x,
                y,
                sx(node_width),
                node_height * scale_y,
                rx=3,
                ry=3,
                fillColor=fill,
                strokeColor=fill,
            )
        )
        lines = _chart_label(text).split("\n")
        font_size = 8.4 if class_name != "root" else 9.3
        start_y = y + node_height * scale_y / 2 + (len(lines) - 1) * font_size * 0.55
        for idx, label in enumerate(lines):
            drawing.add(
                String(
                    x + sx(node_width) / 2,
                    start_y - idx * font_size * 1.15,
                    label,
                    fontName=font,
                    fontSize=font_size,
                    fillColor=text_color,
                    textAnchor="middle",
                )
            )

    for x1, y1, x2, y2 in lines:
        add_line(x1, y1, x2, y2)

    for left, top, node_width, node_height, text, class_name in positions.values():
        add_node(left, top, node_width, node_height, text, class_name)

    drawing.add(
        String(
            sx(650),
            sy(414),
            "备注：逾期金额含诉讼，保证金不含保函",
            fontName=font,
            fontSize=8.2,
            fillColor=colors.HexColor("#111111"),
        )
    )
    drawing.hAlign = "CENTER"
    return drawing


def _build_pdf_table(rows: List[List[str]], styles, font: str) -> Table:
    col_count = len(rows[0]) if rows else 0
    is_aging_jump = _is_aging_jump_table(rows)
    table_style_name = "CNTableSmall5" if col_count >= 8 else "CNTable5"
    table_rows = []
    for row_index, row in enumerate(rows):
        table_rows.append(
            [
                Paragraph(_pdf_table_cell_text(cell, row_index, col_count), styles[table_style_name])
                for cell in row
            ]
        )
    col_widths = _pdf_col_widths(rows[0] if rows else [])
    table = Table(table_rows, colWidths=col_widths, repeatRows=2 if is_aging_jump else 1, hAlign="CENTER")

    style_commands = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111111")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fbfbfb")),
        ("GRID", (0, 0), (-1, -1), 0.28, colors.HexColor("#c9cdd2")),
        ("LINEABOVE", (0, 0), (-1, 0), 1.25, colors.HexColor("#111111")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.1, colors.HexColor("#111111")),
        ("LINEBELOW", (0, -1), (-1, -1), 1.25, colors.HexColor("#111111")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
        ("TOPPADDING", (0, 0), (-1, -1), 5.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
    ]
    if is_aging_jump:
        style_commands.extend(
            [
                ("SPAN", (2, 0), (3, 0)),
                ("SPAN", (4, 0), (5, 0)),
                ("SPAN", (6, 0), (7, 0)),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fbfbfb")),
                ("LINEBELOW", (0, 1), (-1, 1), 1.1, colors.HexColor("#111111")),
            ]
        )
    table.setStyle(TableStyle(style_commands))
    return table


def _pdf_table_cell_text(cell: str, row_index: int, col_count: int) -> str:
    text = _inline_pdf(cell)
    if row_index > 1 or (row_index == 1 and col_count != 8):
        return text

    replacements = {
        "净增加减值金额": "净增加减值金<br/>额",
        "当年增加减值损失": "当年增加<br/>减值损失",
        "其中：应收减值（含坏账）": "其中：应收减值<br/>（含坏账）",
        "其他类型减值（保证金、商票、票证等）": "其他类型减值<br/>（保证金、商票、票证等）",
    }
    if text.startswith("截止") and text.endswith("应收金额"):
        return text.replace("应收金额", "<br/>应收金额")
    if text in replacements:
        return replacements[text]
    if col_count >= 8 and "金额" in text:
        return text.replace("金额", "<br/>金额")
    return text


def _pdf_col_widths(header: List[str]) -> List[float]:
    page_width = PAGE_SIZE[0] - 2 * PDF_MARGIN
    col_count = len(header)
    if col_count == 2:
        return [page_width * 0.42, page_width * 0.58]
    if col_count == 3:
        return [page_width * 0.32, page_width * 0.34, page_width * 0.34]
    if col_count == 8:
        return [28 * mm, 28 * mm] + [(page_width - 56 * mm) / 6] * 6
    if col_count == 11:
        return [23 * mm, 20 * mm, 20 * mm] + [(page_width - 63 * mm) / 8] * 8
    if col_count:
        return [page_width / col_count] * col_count
    return [page_width]
