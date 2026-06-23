"""第二章严格字段映射测试。"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Data import ChapterDataError
from ReportGenerator.chapter2_generator import (
    PENDING_HTML,
    build_apipost_checklist,
    build_chapter2_markdown,
    build_chapter2_stats,
    normalize_chapter2_data,
)
from ReportGenerator.chapter2_renderer import save_final_html, save_final_pdf


REAL_RESPONSE = (
    ROOT / "Reports" / "chapter1_2_flow_tests" / "202606" / "06427_刘晨" / "raw" / "module_2.json"
)


class Chapter2StrictMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real_response = json.loads(REAL_RESPONSE.read_text(encoding="utf-8"))

    def test_real_module2_field_structure_maps_33_exact_cells(self):
        data = normalize_chapter2_data(self.real_response, period="202606")

        self.assertEqual(data.metadata["source_module"], 2)
        self.assertEqual(data.metadata["manager_id"], "06427")
        self.assertEqual(data.metadata["month"], "202606")
        self.assertEqual(data.metadata["title"], "二、利润概况")
        self.assertEqual(data.metadata["source_row_count"], 33)
        self.assertEqual(len(data.cells), 33)

        revenue_month = data.cells["chapter2.profit_table.revenue.month"]
        self.assertEqual(revenue_month.metric_name, "营业收入（不含税）")
        self.assertEqual(revenue_month.metric_path, "二、利润概况-营业收入（不含税）")
        self.assertEqual(revenue_month.date_type, "月")
        self.assertEqual(revenue_month.value_path, "指标数据.实际值")
        self.assertEqual(revenue_month.raw_value, "13.857")
        self.assertEqual(revenue_month.report_value, "13.857万元")
        self.assertEqual(revenue_month.calculation, "无；直接取值")
        self.assertEqual(revenue_month.status, "正常")

    def test_report_preserves_raw_precision(self):
        markdown = build_chapter2_markdown(normalize_chapter2_data(self.real_response))

        self.assertIn("13.857万元", markdown)
        self.assertIn("128.860万元", markdown)
        self.assertIn("1.170万元", markdown)
        self.assertNotIn("13.86万元", markdown)

    def test_gross_margin_uses_customer_confirmed_percent_x100_formula(self):
        data = normalize_chapter2_data(self.real_response)
        stats = build_chapter2_stats(data)

        expected = {"month": "16.5%", "quarter": "19.0%", "year": "21.8%"}
        for key, report_value in expected.items():
            cell = data.cells[f"chapter2.profit_table.gross_margin_rate.{key}"]
            self.assertEqual(cell.status, "正常")
            self.assertEqual(cell.report_value, report_value)
            self.assertEqual(cell.calculation, "指标数据.实际值 × 100")
        self.assertEqual(stats["正常"], 33)
        self.assertEqual(stats["单位冲突"], 0)
        self.assertEqual(stats["计算字段"], 3)

    def test_missing_date_type_is_not_inferred_from_array_order(self):
        response = copy.deepcopy(self.real_response)
        response["data"]["章节数据"][0]["指标数据"].pop("日期类型")

        data = normalize_chapter2_data(response)

        cell = data.cells["chapter2.profit_table.revenue.month"]
        self.assertEqual(cell.status, "缺失")
        self.assertEqual(cell.report_value, PENDING_HTML)

    def test_similar_name_does_not_match(self):
        response = copy.deepcopy(self.real_response)
        response["data"]["章节数据"][0]["指标名称"] = "营业收入"

        data = normalize_chapter2_data(response)

        self.assertEqual(data.cells["chapter2.profit_table.revenue.month"].status, "缺失")

    def test_conflicting_exact_duplicate_is_pending(self):
        response = copy.deepcopy(self.real_response)
        duplicate = copy.deepcopy(response["data"]["章节数据"][0])
        duplicate["指标数据"]["实际值"] = "99.999"
        response["data"]["章节数据"].append(duplicate)

        data = normalize_chapter2_data(response)
        cell = data.cells["chapter2.profit_table.revenue.month"]

        self.assertEqual(cell.status, "数值冲突")
        self.assertEqual(cell.report_value, PENDING_HTML)
        self.assertEqual(len(cell.candidates), 2)

    def test_apipost_checklist_has_copyable_search_and_required_columns(self):
        checklist = build_apipost_checklist(normalize_chapter2_data(self.real_response))

        self.assertIn("报告位置 | ApiPost 搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态", checklist)
        self.assertIn('"指标名称": "营业收入（不含税）"', checklist)
        self.assertIn('"指标路径": "二、利润概况-营业收入（不含税）"', checklist)
        self.assertIn('"日期类型": "月"', checklist)
        self.assertIn('"月份": "202606"', checklist)
        self.assertIn("1-6月累计", checklist)

    def test_empty_response_fails_visibly(self):
        with self.assertRaises(ChapterDataError):
            normalize_chapter2_data({"data": {"章节数据": []}})

    def test_renderer_includes_calculated_margin_and_creates_pdf(self):
        markdown = build_chapter2_markdown(normalize_chapter2_data(self.real_response))
        output_dir = ROOT / "test_output" / "chapter2_renderer"
        html_path = output_dir / "chapter2_test_output.html"
        pdf_path = output_dir / "chapter2_test_output.pdf"

        save_final_html(markdown, html_path)
        save_final_pdf(markdown, pdf_path)

        html = html_path.read_text(encoding="utf-8")
        self.assertIn("16.5%", html)
        self.assertNotIn('<span class="pending-value">待补充</span>', html)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
