"""使用 MOUDLE=4 真实字段结构验证第四章严格映射。"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ReportGenerator.chapter4_generator import (
    MISSING_MARK,
    PRICE_DIFF_CATEGORY,
    SHARE_DIFF_CATEGORY,
    build_chapter4_apipost_checklist,
    collect_metric_evidence,
    extract_chapter2_gross_margin_rate,
    format_chapter4_data,
)
from ReportGenerator.chapter4_renderer import save_final_html, save_final_pdf


REAL_RAW_PATH = (
    Path(__file__).resolve().parents[1]
    / "Reports" / "full_report_tests" / "202606" / "06427_刘晨" / "raw" / "module_4.json"
)


class Chapter4StrictMappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.response = json.loads(REAL_RAW_PATH.read_text(encoding="utf-8"))

    def test_real_response_identity_and_field_structure(self):
        subject = self.response["data"]
        self.assertEqual(subject["区域经理工号"], "06427")
        self.assertEqual(subject["月份"], "202606")
        self.assertEqual(subject["章节名称"], "四、毛利率与产品结构")
        self.assertEqual(len(subject["章节数据"]), 44)
        first = subject["章节数据"][0]
        self.assertIn("指标名称", first)
        self.assertIn("指标路径", first)
        self.assertIn("实际值", first["指标数据"])
        self.assertIn("单位", first["指标数据"])

    def test_exact_path_mapping_preserves_original_precision(self):
        evidence, conflicts, warnings = collect_metric_evidence(self.response["data"]["章节数据"])
        by_path = {item.metric_path: item for item in evidence}
        path = "四、毛利率与产品结构-各产品的均价差异-内墙乳胶漆面漆"
        self.assertEqual(by_path[path].category, PRICE_DIFF_CATEGORY)
        self.assertEqual(by_path[path].value_raw, "187.636")
        self.assertEqual(len([x for x in evidence if x.category == PRICE_DIFF_CATEGORY]), 22)
        self.assertEqual(len([x for x in evidence if x.category == SHARE_DIFF_CATEGORY]), 22)
        self.assertEqual(conflicts, [])
        self.assertEqual(warnings, [])

    def test_path_only_rows_with_trailing_dash_map_products(self):
        response = copy.deepcopy(self.response)
        for row in response["data"]["章节数据"]:
            row["指标名称"] = ""
            row["指标路径"] = f"{row['指标路径'].rstrip('-')}-"

        markdown, stats = format_chapter4_data(response, period="202606", gross_margin_rate="21.8%")

        self.assertIn("地坪漆收入占比38.0%（占比↑7.3%）", markdown)
        self.assertEqual(stats["均价差异正常证据数"], 22)
        self.assertEqual(stats["收入占比差异正常证据数"], 22)
        self.assertEqual(stats["warnings"], [])

    def test_chapter2_gross_margin_rate_supports_path_only_rows(self):
        response = {
            "data": {
                "月份": "202606",
                "章节名称": "二、利润概况",
                "章节数据": [
                    {
                        "指标名称": "",
                        "指标路径": "二、利润概况-毛利率-",
                        "指标数据": {"实际值": "0.260", "日期类型": "年"},
                    }
                ],
            }
        }

        self.assertEqual(extract_chapter2_gross_margin_rate(response), "26.0%")

    def test_near_name_or_near_path_is_not_matched(self):
        row = copy.deepcopy(self.response["data"]["章节数据"][0])
        row["指标路径"] = row["指标路径"].replace("均价差异", "均价差异值")
        evidence, conflicts, warnings = collect_metric_evidence([row])
        self.assertEqual(evidence, [])
        self.assertEqual(conflicts, [])
        self.assertIn("无法精确匹配", warnings[0])

    def test_same_exact_metric_with_conflicting_values_is_pending(self):
        row = copy.deepcopy(self.response["data"]["章节数据"][0])
        conflict = copy.deepcopy(row)
        conflict["指标数据"]["实际值"] = "999.001"
        evidence, conflicts, _warnings = collect_metric_evidence([row, conflict])
        self.assertEqual(evidence, [])
        self.assertEqual(conflicts[0]["状态"], "待补充")
        self.assertEqual(conflicts[0]["冲突原始值"], ["187.636", "999.001"])

    def test_report_uses_rules_for_structure_and_action_guide(self):
        markdown, stats = format_chapter4_data(
            self.response,
            period="202606",
            gross_margin_rate="21.8%",
            action_guide_actions={"structure_action": "AI不应覆盖", "price_action": "AI不应覆盖"},
        )
        self.assertIn("## 四、毛利率与产品结构", markdown)
        self.assertIn("个人毛利率21.8%", markdown)
        self.assertIn("地坪漆收入占比38.0%（占比↑7.3%）", markdown)
        self.assertIn("产品结构：** 地坪漆产品收入占比提升。", markdown)
        self.assertNotIn("AI不应覆盖", markdown)
        self.assertEqual(stats["均价差异正常证据数"], 22)
        self.assertEqual(stats["收入占比差异正常证据数"], 22)
        self.assertEqual(stats["行动指南来源"], "规则模板")

    def test_report_period_can_differ_from_source_period(self):
        markdown, stats = format_chapter4_data(
            self.response,
            period="202605",
            source_period="202606",
            gross_margin_rate="21.8%",
        )

        self.assertIn("## 四、毛利率与产品结构", markdown)
        self.assertIn("个人毛利率21.8%", markdown)
        self.assertEqual(stats["接口校验月份"], "202606")

    def test_latest_sales_share_path_and_price_top3_rules(self):
        def row(name, category, actual, yoy, unit):
            return {
                "指标名称": name,
                "指标路径": f"四、毛利率与产品结构-{category}-{name}",
                "指标数据": {"实际值": actual, "同期数": yoy, "扣分值": -float(actual), "单位": unit},
            }

        values = [
            ("地坪漆", 37.996, 30.723, 14.072, 14.218),
            ("内墙乳胶漆面漆", 13.688, 16.037, 2.915, 3.08),
            ("聚合物水泥防水涂料", 10.432, 16.301, 3.760, 3.64),
            ("无机矿物内墙涂料", 5.185, 0.186, 5.563, 6.42),
            ("弹性涂料", 5.063, 2.107, 7.801, 6.433),
            ("其他产品（界面剂、胶粘剂、辅材等）", 4.280, 1.288, 3.500, 3.49),
        ]
        rows = []
        for name, share, share_yoy, price, price_yoy in values:
            rows.append(row(name, "各产品销量占比差异", share, share_yoy, "%"))
            rows.append(row(name, "各产品的均价差异", price, price_yoy, "元/KG"))
        response = {"data": {"月份": "202606", "章节名称": "四、毛利率与产品结构", "章节数据": rows}}
        markdown, _ = format_chapter4_data(response, period="202606", gross_margin_rate="21.8%")
        self.assertIn("聚合物水泥防水涂料3.8元/KG（同比↑0.1元/KG）", markdown)
        self.assertIn("地坪漆14.1元/KG（同比↓0.1元/KG）", markdown)
        self.assertIn("价格：** 稳住价格，重点稳住地坪漆、内墙乳胶漆面漆、无机矿物内墙涂料的价格。", markdown)

    def test_apipost_checklist_has_required_columns_and_copyable_search(self):
        _markdown, stats = format_chapter4_data(self.response, period="202606")
        checklist = build_chapter4_apipost_checklist(stats)
        for heading in ("报告位置", "ApiPost 搜索内容", "取值字段", "原始值", "报告值", "处理方式", "状态"):
            self.assertIn(heading, checklist)
        self.assertIn('"指标路径": "四、毛利率与产品结构-各产品的均价差异-内墙乳胶漆面漆"', checklist)
        self.assertIn("187.636元/KG", checklist)

    def test_renderer_marks_missing_values_red_in_html_and_writes_pdf(self):
        markdown, _stats = format_chapter4_data(self.response, period="202606")
        output_dir = Path(__file__).resolve().parents[1] / "test_output" / "chapter4_renderer"
        html_path = output_dir / "chapter4_test_output.html"
        pdf_path = output_dir / "chapter4_test_output.pdf"
        save_final_html(markdown, html_path)
        save_final_pdf(markdown, pdf_path)
        html = html_path.read_text(encoding="utf-8")
        self.assertIn('<span class="missing">待补充</span>', html)
        self.assertIn("color: #c00000", html)
        self.assertGreater(pdf_path.stat().st_size, 1000)

    def test_empty_data_renders_zero_and_hides_action_guide(self):
        markdown, stats = format_chapter4_data(
            {"data": {"月份": "202606", "章节名称": "四、毛利率与产品结构", "章节数据": []}},
            period="202606",
        )

        self.assertIn("个人毛利率0.0%", markdown)
        self.assertIn("暂无明显均价上升产品", markdown)
        self.assertIn("暂无明显均价下降产品", markdown)
        self.assertIn("暂无产品结构变化数据", markdown)
        self.assertNotIn("### 行动指南：", markdown)
        self.assertNotIn("◇ **产品结构：**", markdown)
        self.assertEqual(stats["数据状态"], "empty_fallback")
        self.assertEqual(stats["缺失字段"], [])


if __name__ == "__main__":
    unittest.main()
