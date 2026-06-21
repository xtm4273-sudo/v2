"""使用 MOUDLE=4 真实字段结构验证第四章严格映射。"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Data import EMPTY_DATA_MESSAGE, ChapterDataError
from ReportGenerator.chapter4_generator import (
    MISSING_MARK,
    PRICE_DIFF_CATEGORY,
    SHARE_DIFF_CATEGORY,
    build_chapter4_apipost_checklist,
    collect_metric_evidence,
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

    def test_report_does_not_infer_current_values_direction_or_top3(self):
        markdown, stats = format_chapter4_data(self.response, period="202606")
        self.assertIn("## 四、毛利率与产品结构", markdown)
        self.assertGreaterEqual(markdown.count(MISSING_MARK), 7)
        self.assertNotIn("187.64", markdown)
        self.assertNotIn("37.996", markdown)
        self.assertEqual(stats["均价差异正常证据数"], 22)
        self.assertEqual(stats["收入占比差异正常证据数"], 22)
        self.assertEqual(stats["计算字段"], [])
        self.assertIn("产品收入占比排名", stats["缺失字段"])

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

    def test_empty_data_raises_visible_error(self):
        with self.assertRaises(ChapterDataError) as ctx:
            format_chapter4_data([])
        self.assertIn(EMPTY_DATA_MESSAGE, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
