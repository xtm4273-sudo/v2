"""测试第一章绩效得分与预警生成器。"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Data import EMPTY_DATA_MESSAGE, ChapterDataError
from ReportGenerator.chapter1_generator import (
    Chapter1Generator,
    format_chapter1_data,
    normalize_chapter1_data,
    profit_bonus_base,
)
from ReportGenerator.chapter1_renderer import save_final_html, save_final_pdf


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "Data" / "fixtures" / "chapter1_mock.json"


class Chapter1GeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_normalizes_fixture_without_ai_fields(self):
        data = normalize_chapter1_data(self.sample_response, period="202606")

        self.assertEqual(data.metadata["manager_name"], "李泽豪")
        self.assertEqual(data.performance_score.actual, 108)
        self.assertEqual(data.performance_score.province_rank, 5)
        self.assertEqual(data.sales.province_rank, 10)
        self.assertEqual(data.profit.business_rank, 65)
        self.assertEqual([item.name for item in data.underperforming_items], ["招商生效客户", "有效落地项目"])
        self.assertEqual(data.quarter_bonus.sales_actual, 80)
        self.assertEqual(data.year_end_profit.accumulated_profit, 20)
        self.assertEqual(data.field_sources["chapter1.rank_table.sales_province_rank"]["source"], "章节数据[3].指标数据.省区排名")

    def test_builds_markdown_with_template_sections_and_fixed_text(self):
        markdown, stats = format_chapter1_data(self.sample_response, period="202606")

        self.assertIn("闽南经营部区域经理2026年1-6月经营分析报告", markdown)
        self.assertIn("# 绩效得分与预警", markdown)
        self.assertIn("## 1.1 绩效得分情况", markdown)
        self.assertIn("## 1.2 本季度目标达成奖预警", markdown)
        self.assertIn("## 1.3 年终利润达成奖预警", markdown)
        self.assertIn("季度目标达成奖=个人季度实际销量×0.6%×个人季度销量达成率", markdown)
        self.assertIn("年终利润达成奖=个人年度分摊前利润绝对值对应的奖金基数*个人销量达成率（上限1.2倍）", markdown)
        self.assertIn("请注意：", markdown)
        self.assertNotIn("行动指南", markdown)
        self.assertNotIn("AI", markdown)
        self.assertEqual(stats["有效未达百绩效项目数"], 2)

    def test_rank_and_performance_tables_match_template(self):
        markdown, _stats = format_chapter1_data(self.sample_response, period="202606")

        self.assertIn("|  | 绩效排名 | 销量80万 | 分摊前利润20万 |", markdown)
        self.assertIn("| 省区内排名 | 5/26 | 10/26 | 12/26 |", markdown)
        self.assertIn("| 事业部内排名 | 36/1000 | 46/1000 | 65/1000 |", markdown)
        self.assertIn("| 月平均绩效得分（不含其他奖惩） | 108分（TOP 20%） | 招商生效客户、有效落地项目 |", markdown)
        self.assertIn("| 招商生效客户 | 达成率：70% | 全年总扣分12分，月平均得分19分（权重20分） |", markdown)

    def test_bonus_warning_table_marks_unconfirmed_rules_as_pending(self):
        markdown, _stats = format_chapter1_data(self.sample_response, period="202606")

        self.assertIn("|  | 距离80%达成率（发放硬性条件） | 待补充 |", markdown)
        self.assertIn("|  | 距离同期销量持平（负增长将同比例打折） | 待补充 |", markdown)
        self.assertIn("|  | 距离100%达成率还差 | 待补充 |", markdown)
        self.assertIn("|  | 合计（潜在逾期总额） | 80万 |", markdown)
        self.assertIn("|  | 25年同期逾期金额（含法诉，仅考虑25年同期，不考虑交接后的逾期） | 60万 |", markdown)
        self.assertIn("（1）0逾期则奖金100%发放", markdown)
        self.assertIn("逐季度按0.85打折", markdown)

    def test_report_preserves_api_decimal_precision(self):
        response = copy.deepcopy(self.sample_response)
        quarter_sales = next(
            row for row in response["data"]["章节数据"] if row["指标名称"] == "个人季度实际销量"
        )
        quarter_sales["指标数据"]["实际值"] = "48.888"

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("| 个人季度实际销量 | 本季度累计销量 | 48.888万 |", markdown)
        self.assertNotIn("| 个人季度实际销量 | 本季度累计销量 | 48.89万 |", markdown)

    def test_conflicting_duplicate_rate_is_pending(self):
        response = copy.deepcopy(self.sample_response)
        duplicate = copy.deepcopy(
            next(row for row in response["data"]["章节数据"] if row["指标名称"] == "个人季度实际销量")
        )
        duplicate["指标数据"]["达成率"] = "0.411"
        response["data"]["章节数据"].append(duplicate)

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("|  | 当前达成率 | 待补充 |", markdown)

    def test_profit_bonus_base_is_pending_until_customer_provides_brackets(self):
        pending = ("待补充", "上一档奖金基数规则待客户补充，暂不进行区间判断。")
        self.assertEqual(profit_bonus_base(20), pending)
        self.assertEqual(profit_bonus_base(35), pending)
        self.assertEqual(profit_bonus_base(None), pending)

    def test_year_end_warning_marks_base_and_next_bracket_pending_without_api_base(self):
        markdown, _stats = format_chapter1_data(self.sample_response, period="202606")

        self.assertIn("奖金基数为待补充。上一档奖金基数规则待客户补充", markdown)
        self.assertNotIn("20万-40万", markdown)

    def test_year_end_warning_keeps_explicit_api_base_without_inferring_brackets(self):
        response = copy.deepcopy(self.sample_response)
        response["data"]["章节数据"].append(
            {
                "指标名称": "奖金基数",
                "指标路径": "",
                "指标数据": {"实际值": "0.6", "单位": "万元", "日期类型": "年"},
            }
        )

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("奖金基数为0.6万。上一档奖金基数规则待客户补充", markdown)
        self.assertNotIn("60万-80万", markdown)

    def test_generator_accepts_full_response(self):
        markdown = Chapter1Generator(data=self.sample_response, period="202606").run()
        self.assertIn("# 绩效得分与预警", markdown)
        self.assertIn("本季度末逾期金额对应的各类情形", markdown)

    def test_empty_data_raises_visible_error(self):
        with self.assertRaises(ChapterDataError) as ctx:
            format_chapter1_data([])
        self.assertIn(EMPTY_DATA_MESSAGE, str(ctx.exception))

    def test_renderer_saves_html_and_pdf(self):
        markdown, _stats = format_chapter1_data(self.sample_response, period="202606")
        output_dir = Path(__file__).resolve().parents[1] / "test_output" / "chapter1_renderer"
        html_path = output_dir / "chapter1_test_output.html"
        pdf_path = output_dir / "chapter1_test_output.pdf"

        save_final_html(markdown, html_path)
        save_final_pdf(markdown, pdf_path)

        html = html_path.read_text(encoding="utf-8")
        self.assertIn("第一章绩效得分与预警报告", html)
        self.assertIn("绩效得分与预警", html)
        self.assertIn("季度目标达成奖", html)
        self.assertIn('<span class="pending-value">待补充</span>', html)
        self.assertIn('class="data-table rank-table"', html)
        self.assertIn(".rank-table td:not(:first-child)", html)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
