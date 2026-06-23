"""使用 06427/202606/MODULE=5 的真实字段结构验证第五章严格映射。"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ReportGenerator.chapter5_strict import PENDING, build_chapter5_apipost_checklist, format_chapter5_strict


RAW_PATH = ROOT / "Reports" / "full_report_tests" / "202606" / "06427_刘晨" / "raw" / "module_5.json"


class Chapter5StrictMappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
        cls.markdown, cls.stats = format_chapter5_strict(cls.raw, period="202606")

    def test_real_response_identity_and_shape(self):
        data = self.raw["data"]
        self.assertEqual(data["区域经理工号"], "06427")
        self.assertEqual(data["月份"], "202606")
        self.assertEqual(data["章节名称"], "五、应收分析")
        self.assertEqual(len(data["章节数据"]), 132)

    def test_unique_fields_keep_original_precision(self):
        self.assertIn("应收款项总额：99.162万元", self.markdown)
        self.assertIn("应收减值-27.885万元", self.markdown)
        self.assertIn("规模变动增加减值0.688万元", self.markdown)
        self.assertNotIn("99.2万元", self.markdown)

    def test_only_documented_unit_conversion_is_calculated(self):
        self.assertIn("6月财务费用3100.000元", self.markdown)
        source = self.stats["field_sources"]["chapter5.finance.expense"]
        self.assertEqual(source["raw_values"], ["0.310万元"])
        self.assertIn("×10000", source["calculation"])

    def test_repeated_customer_rows_are_not_grouped_by_order(self):
        sources = self.stats["field_sources"]
        self.assertIn("重复冲突", sources["chapter5.overdue_top"]["status"])
        self.assertIn("缺客户唯一键", sources["chapter5.finance_top"]["status"])
        self.assertNotIn("客户1（接口未提供名称）", self.markdown)
        self.assertIn(PENDING, self.markdown)

    def test_checklist_has_required_columns_and_copyable_search(self):
        checklist = build_chapter5_apipost_checklist(self.stats)
        self.assertIn("| 报告位置 | ApiPost搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态 |", checklist)
        self.assertIn('`"指标名称": "应收款项"`', checklist)
        self.assertIn('`"指标路径": "五、应收分析-应收款项"`', checklist)

    def test_omit_rule_uses_direct_total_and_threshold_only(self):
        omit = self.stats["省略判断"]
        self.assertFalse(omit["是否省略第五章"])
        self.assertIn("99.162万元不低于10万元", omit["原因"])


if __name__ == "__main__":
    unittest.main()
