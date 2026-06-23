# 第一、二章报告数据流日志

## 运行步骤

### build_requests
- detail: `[{'job_id': '06427', 'time': '202606', 'module': 1}, {'job_id': '06427', 'time': '202606', 'module': 2}]`

### fetch_api
- detail: `并发请求 MOUDLE=1 和 MOUDLE=2 完成`

### validate_module_1
- status: `ok`
- message: `数据正常`
- chapter_name: `一、绩效得分与预警`
- row_count: `30`
- raw_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/raw/module_1.json`

### validate_module_2
- status: `ok`
- message: `数据正常`
- chapter_name: `二、利润概况`
- row_count: `33`
- raw_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/raw/module_2.json`

### normalize_chapter_1
- detail: `第一章接口数据 -> 轻量字段映射 -> Chapter1Data -> Markdown`

字段来源见下方“第一章字段来源”。
- cleaned_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/cleaned/chapter1_cleaned.json`
- markdown_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/markdown/chapter1.md`

### normalize_chapter_2
- detail: `第二章接口 data.章节数据 -> 按 指标名称 + 日期类型 组织利润概况表 -> Markdown`
- row_count: `33`
- cleaned_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/cleaned/chapter2_cleaned.json`
- markdown_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/markdown/chapter2.md`

### render_report
- detail: `第一章 Markdown + 第二章 Markdown -> 连续版 HTML/PDF`
- markdown_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/markdown/chapter1_2_report.md`
- html_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/html/chapter1_2_report.html`
- pdf_path: `/Users/ppp/Desktop/三棵树/SimpleIntellReportV2/Reports/chapter1_2_flow_tests/202606/06427_刘晨/pdf/chapter1_2_report.pdf`

## 第一章字段来源

| 报告字段 | 状态 | 来源 | 原始值 | 是否 fallback |
| --- | --- | --- | --- | --- |
| chapter1.performance_score.actual | ok | 章节数据[16].指标数据.实际值 | 55.700 | False |
| chapter1.rank_table.performance_province_rank | ok | 章节数据[16].指标数据.省区排名 | 20 | False |
| chapter1.rank_table.performance_business_rank | ok | 章节数据[16].指标数据.部门排名 | 565 | False |
| chapter1.rank_table.sales_amount | ok | 章节数据[0].指标数据.实际值 | 145.611 | False |
| chapter1.rank_table.sales_province_rank | ok | 章节数据[8].指标数据.省区排名 | 24 | False |
| chapter1.rank_table.sales_business_rank | ok | 章节数据[14].指标数据.部门排名 | 486 | False |
| chapter1.rank_table.profit_amount | ok | 章节数据[1].指标数据.实际值 | 44.987 | False |
| chapter1.rank_table.profit_province_rank | ok | 章节数据[9].指标数据.省区排名 | 6 | False |
| chapter1.rank_table.profit_business_rank | ok | 章节数据[15].指标数据.部门排名 | 177 | False |
| chapter1.quarter_bonus.sales_actual | ok | 章节数据[23].指标数据.实际值 | 48.888 | False |
| chapter1.quarter_bonus.achievement_rate | ok | 章节数据[23].指标数据.达成率 | 0.411 | False |
| chapter1.quarter_bonus.overdue_amount | ok | 章节数据[4].指标数据.实际值 | 47.049 | True |
| chapter1.quarter_bonus.due_amount | ok | 章节数据[28].指标数据.实际值 | 15.130 | False |
| chapter1.quarter_bonus.same_period_overdue | ok | 章节数据[29].指标数据.实际值 | 77.050 | False |
| chapter1.year_end_profit.accumulated_profit | ok | 章节数据[1].指标数据.实际值 | 44.987 | False |
| chapter1.year_end_profit.bonus_base | ok | 章节数据[2].指标数据.实际值 | 0.600 | False |
| chapter1.performance.underperforming_items | ok | 按 指标路径 包含 未达百绩效项目 且排除 月平均得分/全年总扣分 的记录生成 |  |  |

## 数据如何进入报告

1. 脚本构造两个请求：`MOUDLE=1` 和 `MOUDLE=2`。
2. 接口返回后，原始响应保存到 `raw/module_1.json` 和 `raw/module_2.json`。
3. 第一章先经过字段映射，生成 `cleaned/chapter1_cleaned.json`，其中 `field_sources` 记录每个排名表字段来自哪条接口记录。
4. 第一章 Markdown 表格只读取清洗后的 `Chapter1Data`，不再临时猜字段。
5. 第二章读取 `data.章节数据`，按 `指标名称 + 日期类型` 组装利润概况表。
6. 两章 Markdown 合并后，由总报告渲染器生成连续 HTML/PDF。
