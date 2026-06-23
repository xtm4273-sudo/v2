"""统一报告视觉主题。

所有 HTML 与 ReportLab PDF 渲染器都通过本模块使用一期绿色色板，
避免各章节分别维护颜色。
"""
from __future__ import annotations

from reportlab.lib import colors as _reportlab_colors


PRIMARY = "#2E7D32"
SECONDARY = "#66BB6A"
SOFT_BACKGROUND = "#F1F8E9"
TEXT_MAIN = "#333333"
TEXT_MUTED = "#666666"
DANGER = "#D32F2F"
PAGE_BACKGROUND = "#F0F2F5"
SURFACE = "#FFFFFF"
BORDER = "#DDE7DD"


# HTML 主题作为最后一层样式注入，不改变各章节原有版式。
GREEN_THEME_CSS = f"""
/* Shared phase-one green report theme */
h1, h2, h3 {{
  color: {PRIMARY} !important;
}}
/*
 * Chromium 会因应收结构图的固定宽度将整页缩放到约 72%。
 * 以下字号按 PDF 最终点数反向校准：正文/表格约 9.7pt，报告标题约 16.5pt。
 */
p {{ font-size: 18px !important; }}
table {{ font-size: 18px !important; }}
.report-header-title {{ font-size: 30px !important; }}
.report-header-breadcrumb,
.report-header-meta {{ font-size: 18px !important; }}
.page > h1 {{
  border-left: 5px solid {SECONDARY};
  padding-left: 12px;
}}
h2 {{
  border-color: {SECONDARY} !important;
}}
table th,
.data-table th,
.chapter4-table th {{
  background: {PRIMARY} !important;
  color: {SURFACE} !important;
  border-color: {BORDER} !important;
}}
table td,
.data-table td,
.chapter4-table td {{
  border-color: {BORDER} !important;
}}
p.bullet::before,
.bullet::before {{
  color: {SECONDARY} !important;
}}
.pending,
.pending-value,
.missing {{
  color: {DANGER} !important;
}}

/* 客户范本中的排名摘要表：浅绿整块、无网格、大留白。 */
table.rank-table {{
  border: 0 !important;
  border-collapse: separate;
  border-spacing: 0;
  background: {SOFT_BACKGROUND};
  margin: 14px 0 24px;
}}
.rank-table th,
.rank-table td {{
  border: 0 !important;
  background: {SOFT_BACKGROUND} !important;
  vertical-align: middle;
}}
.rank-table th {{
  padding: 13px 10px 8px !important;
  text-align: center !important;
  font-weight: 800;
  color: {PRIMARY} !important;
}}
.rank-table td {{
  padding: 10px 10px 13px !important;
  text-align: center !important;
}}
.rank-table th:first-child,
.rank-table td:first-child {{
  width: 18%;
  text-align: left !important;
  font-style: normal;
  font-weight: 400;
}}
.rank-table td:not(:first-child) {{
  font-size: 26px;
  font-style: italic;
}}

.action-guide {{
  margin: 12px 0 22px;
  padding: 11px 15px;
  border-left: 4px solid #FFA000;
  border-radius: 4px;
  background: #FFF8E1;
  break-inside: avoid;
}}
.action-guide-title {{
  margin: 0 0 5px;
  color: {TEXT_MAIN};
  font-weight: 800;
}}
.action-guide p {{
  margin: 4px 0;
  font-size: 17.5px !important;
}}

.summary-item {{
  margin: 11px 0;
  padding: 13px 15px;
  border-radius: 6px;
  break-inside: avoid;
}}
.summary-item h3 {{
  margin: 0 0 7px;
  font-size: 15px;
}}
.summary-item p {{ margin: 4px 0; font-size: 17.5px !important; }}
.summary-group {{
  break-before: page;
  break-inside: avoid;
}}
.summary-group > h1 {{
  border-left: 5px solid {SECONDARY};
  padding-left: 12px;
}}
.summary-advantage {{ background: #E3F2FD; color: #0D47A1; }}
.summary-advantage h3 {{ color: #0D47A1 !important; }}
.summary-shortcoming {{ background: #FFEBEE; color: #B71C1C; }}
.summary-shortcoming h3 {{ color: #B71C1C !important; }}
.summary-strategy {{ background: #FFF3E0; color: #E65100; }}
.summary-strategy h3 {{ color: #E65100 !important; }}
"""


def apply_html_theme(css: str) -> str:
    """在保留原有布局的前提下追加统一颜色主题。"""
    return f"{css.rstrip()}\n{GREEN_THEME_CSS}"


_PDF_COLOR_MAP = {
    # 标题与强调文字
    "#15293f": PRIMARY,
    "#16324f": PRIMARY,
    "#1f3348": PRIMARY,
    "#244b73": PRIMARY,
    "#3a3d42": PRIMARY,
    "#222222": PRIMARY,
    "#111111": PRIMARY,
    "#0b5cad": PRIMARY,
    # 表头与浅色区域
    "#d9d9d9": SOFT_BACKGROUND,
    "#edf3f8": SOFT_BACKGROUND,
    "#eef3f7": SOFT_BACKGROUND,
    "#f1f2f4": SOFT_BACKGROUND,
    "#fbfbfb": SOFT_BACKGROUND,
    # 边框
    "#bfc3c8": BORDER,
    "#c5c8cc": BORDER,
    "#c9cdd2": BORDER,
    "#ccd6e0": BORDER,
    "#cfd8e3": BORDER,
}


class _ThemedReportLabColors:
    """代理 reportlab.lib.colors，只替换报告主题色。"""

    def HexColor(self, value: str):  # noqa: N802 - 保持 ReportLab 的方法名
        themed_value = _PDF_COLOR_MAP.get(value.lower(), value)
        return _reportlab_colors.HexColor(themed_value)

    def __getattr__(self, name: str):
        return getattr(_reportlab_colors, name)


colors = _ThemedReportLabColors()
