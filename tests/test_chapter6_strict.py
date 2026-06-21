"""使用 06427/202606/MODULE=6 的真实字段结构验证第六章严格映射。"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ReportGenerator.chapter6_strict import PENDING, build_chapter6_apipost_checklist, format_chapter6_strict


RAW_PATH = ROOT / "Reports" / "full_report_tests" / "202606" / "06427_刘晨" / "raw" / "module_6.json"


class Chapter6StrictMappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
        cls.markdown, cls.stats = format_chapter6_strict(cls.raw, period="202606")

    def test_real_response_identity_and_shape(self):
        data = self.raw["data"]
        self.assertEqual(data["区域经理工号"], "06427")
        self.assertEqual(data["月份"], "202606")
        self.assertEqual(data["章节名称"], "六、费用分析")
        self.assertEqual(len(data["章节数据"]), 26)

    def test_unique_total_keeps_original_precision_without_conversion(self):
        self.assertIn("6月费用11.993万元", self.markdown)
        self.assertNotIn("119930", self.markdown)
        source = self.stats["field_sources"]["chapter6.sample.total"]
        self.assertEqual(source["raw_values"], ["11.993万元"])
        self.assertEqual(source["calculation"], "无，直接取接口原始值并保持原始精度")

    def test_conflicting_rows_are_not_assigned_by_order_or_size(self):
        sources = self.stats["field_sources"]
        self.assertEqual(sources["chapter6.travel.total"]["status"], "重复冲突")
        self.assertEqual(sources["chapter6.efficiency.daily_total"]["status"], "重复冲突")
        self.assertIn("缺产品唯一标识", sources["chapter6.sample.product1"]["status"])
        self.assertIn(PENDING, self.markdown)
        self.assertNotIn("14759.530元", self.markdown)
        self.assertNotIn("2858.000元", self.markdown)

    def test_missing_fields_are_not_calculated_from_zero_or_deduction(self):
        sources = self.stats["field_sources"]
        self.assertEqual(sources["chapter6.travel.yoy_rate"]["status"], "取值字段缺失")
        self.assertEqual(sources["chapter6.sample.yoy_delta"]["status"], "取值字段缺失")
        self.assertNotIn("同比增长", self.markdown)
        self.assertNotIn("-11.993万元", self.markdown)

    def test_checklist_has_required_columns_and_copyable_search(self):
        checklist = build_chapter6_apipost_checklist(self.stats)
        self.assertIn("| 报告位置 | ApiPost搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态 |", checklist)
        self.assertIn('`"指标名称": "差旅费"`', checklist)
        self.assertIn('`"指标路径": "六、费用分析-差旅费"`', checklist)
        self.assertIn('`"指标名称": "样板样漆费用"`', checklist)


if __name__ == "__main__":
    unittest.main()
