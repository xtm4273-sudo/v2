from reportlab.lib import colors as reportlab_colors

from ReportGenerator.report_theme import (
    BORDER,
    PRIMARY,
    REPORT_FONT_STACK,
    SOFT_BACKGROUND,
    apply_html_theme,
    colors,
)
from ReportGenerator.full_report_renderer import markdown_to_html


def test_html_theme_adds_green_palette_without_removing_layout_css():
    original = ".page { max-width: 980px; }"

    themed = apply_html_theme(original)

    assert original in themed
    assert PRIMARY in themed
    assert SOFT_BACKGROUND in themed
    assert BORDER in themed
    assert REPORT_FONT_STACK in themed
    assert "font-size: 18px !important" in themed
    assert "font-size: 32px !important" in themed
    assert "font-weight: 800 !important" in themed


def test_pdf_theme_maps_existing_heading_and_table_colors():
    assert colors.HexColor("#15293f") == reportlab_colors.HexColor(PRIMARY)
    assert colors.HexColor("#eef3f7") == reportlab_colors.HexColor(SOFT_BACKGROUND)


def test_pdf_theme_preserves_unmapped_colors():
    assert colors.HexColor("#ABCDEF") == reportlab_colors.HexColor("#ABCDEF")


def test_full_report_marks_rank_summary_table_for_customer_style():
    markdown = """# 绩效得分与预警

普通正文 20/34 不应套排名样式。

|  | 绩效排名 | 销量146万 | 分摊前利润45万 |
| --- | --- | --- | --- |
| 省区内排名 | 5/26 | 10/26 | 12/26 |
| 事业部内排名 | 36/1000 | 46/1000 | 65/1000 |
"""

    html = markdown_to_html(markdown)

    assert 'class="report-table rank-table"' in html
    assert ".rank-table td:not(:first-child)" in html
    assert '<span class="rank-current">5</span><span class="rank-total"> / 26</span>' in html
    assert '<span class="rank-current">36</span><span class="rank-total"> / 1000</span>' in html
    assert "普通正文 20/34 不应套排名样式。" in html
    assert '<span class="rank-current">20</span><span class="rank-total"> / 34</span>' not in html
    assert ".rank-table .rank-current" in html
    assert ".rank-table .rank-total" in html
    assert "font-style: normal" in html
    assert ".rank-table th {" in html
    assert "font-size: 18px !important" in html
    assert ".rank-table .rank-current {" in html
    assert "font-size: 16px !important" in html
    assert "font-size: 1.18em" not in html
    assert "color: #666666 !important" in html


def test_full_report_rebuilds_opening_metadata_as_phase_one_header():
    markdown = """# 杭州工业厂房经营部刘晨202606经营分析报告

工号：06427
姓名：刘晨
组织：城市焕新事业部 / 浙赣大区 / 浙西省区 / 杭州工业厂房经营部

杭州工业厂房经营部区域经理2026年1-6月经营分析报告

# 绩效得分与预警
"""

    html = markdown_to_html(markdown)

    assert 'class="report-header"' in html
    assert "2026年1-6月经营分析报告" in html
    assert "城市焕新事业部 &gt; 浙赣大区 &gt; 浙西省区 &gt; 杭州工业厂房经营部 刘晨" in html
    assert "范围：2026年1-6月" in html
    assert "工号：06427" not in html


def test_full_report_header_supports_previous_month_reporting_period_and_bold_title():
    markdown = """# 杭州工业厂房经营部刘晨202606经营分析报告

姓名：刘晨
组织：城市焕新事业部 / 浙赣大区 / 浙西省区 / 杭州工业厂房经营部

杭州工业厂房经营部区域经理2026年1-5月经营分析报告

# 绩效得分与预警
"""

    html = markdown_to_html(markdown)

    assert "2026年1-5月经营分析报告" in html
    assert "范围：2026年1-5月" in html
    assert "font-weight: 800 !important" in html


def test_full_report_uses_phase_one_action_and_summary_blocks():
    markdown = """# 测试202606经营分析报告

姓名：测试
组织：事业部 / 大区 / 省区 / 经营部

经营部区域经理2026年1-6月经营分析报告

# 三、销量分析

* 行动指南：制定补量动作。

## 八、总结

优势：利润表现突出。

短板：绩效得分偏低。

核心策略：
产品：优化产品结构。
"""

    html = markdown_to_html(markdown)

    assert 'class="action-guide"' in html
    assert 'class="summary-item summary-advantage"' in html
    assert 'class="summary-item summary-shortcoming"' in html
    assert 'class="summary-item summary-strategy"' in html
    assert "制定补量动作" in html


def test_full_report_hides_internal_comments_and_raw_missing_spans():
    markdown = """## 三、销量分析

| 指标 | 值 |
| --- | --- |
| 同比 | <span style="color:#c00000;font-weight:700">待补充</span> |

### 行动指南：

◇ 补充数据后制定行动。

<!-- 内部数据提示，不应出现在客户报告 -->
"""

    html = markdown_to_html(markdown)

    assert "&lt;span" not in html
    assert "内部数据提示" not in html
    assert '<span class="missing">待补充</span>' in html


def test_full_report_colors_direction_arrows_and_price_labels():
    markdown = """# 三、销量分析

### 正向指标（1-5月）
* **产品：**无机矿物内墙涂料8万（↑1991.4%）表现突出

### 风险指标（1-5月）
* **产品：**地坪漆55万（↓7.3%）

# 四、毛利率与产品结构

| 指标 | 详情 |
| --- | --- |
| 价格变动 | **均价上升：** 聚合物水泥防水涂料3.8元/KG（同比↑0.1元/KG）<br>**均价下降：** 地坪漆14.1元/KG（同比↓0.1元/KG） |
| 结构变化 | 地坪漆收入占比38%（占比↑7.3%）<br>内墙乳胶漆面漆收入占比13.7%（占比↓2.3%） |
"""

    html = markdown_to_html(markdown)

    assert '<span class="direction-up">↑1991.4%</span>' in html
    assert '<span class="direction-down">↓7.3%</span>' in html
    assert '<span class="direction-up">↑0.1元/KG</span>' in html
    assert '<span class="direction-down">↓0.1元/KG</span>' in html
    assert '<span class="direction-up">↑7.3%</span>' in html
    assert '<span class="direction-down">↓2.3%</span>' in html
    assert '<span class="direction-up price-label">均价上升：</span>' in html
    assert '<span class="direction-down price-label">均价下降：</span>' in html
    assert ".direction-up" in html
    assert ".direction-down" in html
