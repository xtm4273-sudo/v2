"""第三章严格字段映射测试。"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Data import EMPTY_DATA_MESSAGE, ChapterDataError
from ReportGenerator.chapter3_generator import (
    MISSING,
    build_chapter3_apipost_checklist,
    format_chapter3_data,
    normalize_chapter3_records,
)


def metric(name, path, date_type, actual, target=0.0, yoy=0.0, deduction=0.0, rate="0.000", unit="万"):
    return {
        "指标名称": name,
        "指标路径": path,
        "指标数据": {
            "实际值": actual,
            "目标值": target,
            "同期数": yoy,
            "扣分值": deduction,
            "达成率": rate,
            "单位": unit,
            "日期类型": date_type,
        },
    }


class Chapter3StrictMappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real_path = ROOT / "Reports/full_report_tests/202606/06427_刘晨/raw/module_3.json"
        cls.real = json.loads(cls.real_path.read_text(encoding="utf-8"))

    def test_real_module3_structure_and_identity(self):
        self.assertEqual(self.real["code"], 1)
        self.assertEqual(self.real["data"]["章节名称"], "三、销量分析")
        self.assertEqual(self.real["data"]["区域经理工号"], "06427")
        self.assertEqual(self.real["data"]["月份"], "202606")
        self.assertEqual(len(self.real["data"]["章节数据"]), 72)

    def test_preserves_real_json_precision_and_exact_dimensions(self):
        markdown, stats = format_chapter3_data(self.real, period="202606")
        self.assertIn("| 实际 | 15.659万 | 48.888万 | 145.611万 |", markdown)
        self.assertIn("|  | 实际 | 0.000家 | 1.000家 | 1.000家 |", markdown)
        self.assertNotIn("15.66万", markdown)
        self.assertEqual(stats["有效指标数"], 72)
        self.assertEqual(stats["conflicts"], [])

    def test_chapter33_matches_customer_template_without_detail_tables(self):
        markdown, _ = format_chapter3_data(self.real, period="202606")
        self.assertIn("* 正向指标（1-6月）", markdown)
        self.assertIn("产品：无机矿物内墙涂料7.550万（↑1991.41%）、弹性涂料7.372万（↑80.11%）、其他产品（界面剂、胶粘剂、辅材等）6.232万（↑149.08%）表现突出", markdown)
        self.assertIn("客户：产销客户数同比增长0.00%（增加0.000个）", markdown)
        self.assertIn("项目：产销项目数同比增长5.13%（增加2.000个）", markdown)
        self.assertIn("地产系统行业收入增长39.93%，占比增长4.88%", markdown)
        self.assertIn("* 风险指标（1-6月）", markdown)
        self.assertIn("地坪漆55.326万（↓7.31%），销售量下降6.35%", markdown)
        self.assertIn("客户：客均销量9.101万（↓25.05%）", markdown)
        self.assertIn("项目：单项目销量3.551万（↓28.71%）", markdown)
        self.assertIn("市政公建行业收入下降44.74%，占比下降8.93%", markdown)
        self.assertNotIn("产品收入与销售量明细", markdown)
        self.assertNotIn("行业销量与占比明细", markdown)

    def test_missing_fields_are_red_and_not_calculated(self):
        markdown, _ = format_chapter3_data(self.real, period="202606")
        self.assertIn(MISSING, markdown)
        self.assertIn(f"| 同比增长率 | {MISSING} | {MISSING} | {MISSING} |", markdown)
        self.assertNotIn("-64.63%", markdown)

    def test_process_negative_growth_uses_counts_and_calculates_rate(self):
        markdown, _ = format_chapter3_data(self.real, period="202606")
        self.assertIn("负增长（1-6月）指标包含：打样项目数", markdown)
        self.assertIn("|  | 差距 | -3.000个 | -6.000个 | -6.000个 |", markdown)
        self.assertIn("|  | 增长率 | -27.27% | -31.58% | -20.69% |", markdown)

    def test_hides_negative_growth_line_when_sample_count_is_not_down(self):
        rows = [metric("", "三、销量分析-打样项目数-", "年", "29.000", yoy=23.0, unit="个")]
        markdown, _ = format_chapter3_data(rows, period="202606")
        self.assertNotIn("负增长（1-6月）指标包含", markdown)

    def test_process_growth_formula_is_in_apipost_checklist(self):
        checklist = build_chapter3_apipost_checklist(normalize_chapter3_records(self.real), "202606")
        self.assertIn("实际值 - 同期数", checklist)
        self.assertIn("（实际值 - 同期数）÷同期数×100%", checklist)
        self.assertIn("`-20.69%`", checklist)

    def test_conflicting_exact_duplicate_becomes_missing(self):
        rows = [
            metric("销量", "三、销量分析-销量-销量", "月", "1.000"),
            metric("销量", "三、销量分析-销量-销量", "月", "2.000"),
        ]
        markdown, stats = format_chapter3_data(rows, period="202606")
        self.assertIn(f"| 实际 | {MISSING} | {MISSING} | {MISSING} |", markdown)
        self.assertEqual(len(stats["conflicts"]), 1)

    def test_does_not_infer_missing_date_type_from_array_order(self):
        rows = [metric("销量", "三、销量分析-销量-销量", "", "15.659")]
        markdown, _ = format_chapter3_data(rows, period="202606")
        self.assertIn(f"| 实际 | {MISSING} | {MISSING} | {MISSING} |", markdown)

    def test_apipost_search_fragments_are_copyable(self):
        records = normalize_chapter3_records(self.real)
        checklist = build_chapter3_apipost_checklist(records, "202606")
        self.assertIn('"指标名称": "销量"', checklist)
        self.assertIn('"日期类型": "月"', checklist)
        self.assertIn("| 报告位置 | ApiPost 搜索内容 | 取值字段 | 报告值 | 状态 |", checklist)
        self.assertIn("## 需要特别确认", checklist)

    def test_empty_data_raises_visible_error(self):
        with self.assertRaises(ChapterDataError) as ctx:
            format_chapter3_data([])
        self.assertIn(EMPTY_DATA_MESSAGE, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
