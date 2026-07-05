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
from ReportGenerator.full_report_renderer import markdown_to_html as full_markdown_to_html


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "Data" / "fixtures" / "chapter1_mock.json"
LIVE_MODULE1_PATH = (
    Path(__file__).resolve().parents[1]
    / "Reports" / "full_report_live_strict" / "202606" / "06427_刘晨" / "raw" / "module_1.json"
)
CURRENT_MODULE1_PATH = (
    Path(__file__).resolve().parents[1]
    / "output" / "period_adjusted_reports" / "202606" / "06427_刘晨" / "raw" / "module_1.json"
)


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
        self.assertIn("# 一、绩效得分与预警", markdown)
        self.assertIn("## 1.1 绩效得分情况", markdown)
        self.assertIn("## 1.2 本季度目标达成奖预警", markdown)
        self.assertIn("## 1.3 年终利润达成奖预警", markdown)
        self.assertIn("季度目标达成奖=个人季度实际销量×0.6%×个人季度销量达成率", markdown)
        self.assertIn("年终利润达成奖=个人年度分摊前利润绝对值对应的奖金基数*个人销量达成率（上限1.2倍）", markdown)
        self.assertIn("请注意：", markdown)
        self.assertNotIn("行动指南", markdown)
        self.assertNotIn("AI", markdown)
        self.assertEqual(stats["有效未达百绩效项目数"], 2)

    def test_explicit_report_period_overrides_source_month_for_display(self):
        markdown, _stats = format_chapter1_data(self.sample_response, period="202605")

        self.assertIn("闽南经营部区域经理2026年1-5月经营分析报告", markdown)
        self.assertNotIn("2026年1-6月经营分析报告", markdown)

    def test_rank_and_performance_tables_match_template(self):
        markdown, _stats = format_chapter1_data(self.sample_response, period="202606")

        self.assertIn("|  | 绩效排名 | 销量80万 | 分摊前利润20万 |", markdown)
        self.assertIn("| 省区内排名 | 5/26 | 10/26 | 12/26 |", markdown)
        self.assertIn("| 事业部内排名 | 36/1000 | 46/1000 | 65/1000 |", markdown)
        self.assertIn("| 月平均绩效得分（不含其他奖惩） | 108分（TOP5%） | 未达百绩效项目：招商生效客户、有效落地项目 |", markdown)
        self.assertIn("| 招商生效客户 | 得分率：70% | 全年总扣分12分，月平均得分待补充（权重20分） |", markdown)

    def test_monthly_scores_use_direct_records_without_calculation_fallback(self):
        response = copy.deepcopy(self.sample_response)
        response["data"]["章节数据"].extend(
            [
                {
                    "指标名称": "月平均得分",
                    "指标路径": "一、绩效得分与预警-未达百绩效项目-月平均得分",
                    "指标数据": {"实际值": "18.375", "达成率": "0.700"},
                },
                {
                    "指标名称": "月平均得分",
                    "指标路径": "一、绩效得分与预警-未达百绩效项目-月平均得分",
                    "指标数据": {"实际值": "7.125", "达成率": "0.850"},
                },
            ]
        )

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("月平均得分18.375分（权重20分）", markdown)
        self.assertIn("月平均得分7.125分（权重20分）", markdown)
        self.assertNotIn("月平均得分19分", markdown)

    def test_monthly_scores_prefer_explicit_indicator_key(self):
        response = copy.deepcopy(self.sample_response)
        response["data"]["章节数据"].extend(
            [
                {
                    "指标名称": "有效落地项目",
                    "指标路径": "一、绩效得分与预警-未达百绩效项目-月平均得分-有效落地项目",
                    "指标数据": {"实际值": "7.125", "达成率": "0.700"},
                },
                {
                    "指标名称": "招商生效客户",
                    "指标路径": "一、绩效得分与预警-未达百绩效项目-月平均得分-招商生效客户",
                    "指标数据": {"实际值": "18.375", "达成率": "0.700"},
                },
            ]
        )

        data = normalize_chapter1_data(response, period="202606")
        scores = {item.name: item.monthly_score for item in data.underperforming_items}
        match_methods = {
            item["item_name"]: item["match_method"]
            for item in data.field_sources["chapter1.performance.monthly_scores"]["items"]
        }

        self.assertEqual(scores["招商生效客户"], 18.375)
        self.assertEqual(scores["有效落地项目"], 7.125)
        self.assertEqual(match_methods["招商生效客户"], "explicit_indicator")
        self.assertEqual(match_methods["有效落地项目"], "explicit_indicator")

    def test_live_quarter_bonus_mapping_weights_and_merged_groups(self):
        response = json.loads(LIVE_MODULE1_PATH.read_text(encoding="utf-8"))

        markdown, _stats = format_chapter1_data(response, period="202605")
        section = markdown.split("## 1.2", 1)[1].split("## 1.3", 1)[0]
        html = full_markdown_to_html(markdown)

        self.assertIn("月平均得分28.37分（权重30分）", markdown)
        self.assertIn("月平均得分7.33分（权重10分）", markdown)
        self.assertIn("月平均得分10分（权重50分）", markdown)
        self.assertIn("|  | 当前达成率 | 41.1% |", section)
        self.assertIn("|  | 距离80%达成率（发放硬性条件）还差 | 46万 |", section)
        self.assertIn("|  | 距离同期销量持平（负增长将同比例打折）还差 | 53万 |", section)
        self.assertIn("|  | 距离100%达成率还差 | 70万，预计奖金0.12万 |", section)
        self.assertIn("|  | 合计（潜在逾期总额） | 62万 |", section)
        self.assertNotIn("待补充", section)
        self.assertEqual(html.count('rowspan="'), 2)
        self.assertIn(
            "截止5月本年累计分摊前利润45万，奖金基数为0.6。"
            "若到年底分摊前利润在60万-80万（含）之间，奖金基数为1.2。",
            markdown,
        )

    def test_rank_table_amounts_round_to_integer_wan_for_live_data(self):
        response = json.loads(LIVE_MODULE1_PATH.read_text(encoding="utf-8"))

        markdown, _stats = format_chapter1_data(response, period="202605")

        self.assertIn("|  | 绩效排名 | 销量146万元 | 分摊前利润45万元 |", markdown)
        self.assertNotIn("销量145.611万元", markdown)
        self.assertNotIn("分摊前利润44.987万元", markdown)

    def test_current_quarter_bonus_mapping_survives_zero_targets_and_duplicate_records(self):
        response = json.loads(CURRENT_MODULE1_PATH.read_text(encoding="utf-8"))

        markdown, _stats = format_chapter1_data(response, period="202605")
        section = markdown.split("## 1.2", 1)[1].split("## 1.3", 1)[0]

        self.assertIn("| 个人季度实际销量 | 本季度累计销量 | 49万 |", section)
        self.assertIn("|  | 当前达成率 | 41.1% |", section)
        self.assertIn("|  | 距离80%达成率（发放硬性条件）还差 | 46万 |", section)
        self.assertIn("|  | 距离同期销量持平（负增长将同比例打折）还差 | 53万 |", section)
        self.assertIn("|  | 距离100%达成率还差 | 70万，预计奖金0.12万 |", section)

    def test_rank_table_marks_missing_population_totals_as_pending(self):
        response = copy.deepcopy(self.sample_response)
        total_keys = {
            "省区总人数", "省区人数", "省区总数",
            "事业部总人数", "部门总人数", "事业部总数",
        }
        for row in response["data"]["章节数据"]:
            metric = row.get("指标数据", {})
            for key in total_keys:
                metric.pop(key, None)

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("| 省区内排名 | 5/待补充 | 10/待补充 | 12/待补充 |", markdown)
        self.assertIn("| 事业部内排名 | 36/待补充 | 46/待补充 | 65/待补充 |", markdown)
        self.assertIn("108分（TOP待补充）", markdown)

    def test_top_uses_business_rank_and_hides_values_after_top_20_percent(self):
        response = copy.deepcopy(self.sample_response)
        metric = next(
            row["指标数据"]
            for row in response["data"]["章节数据"]
            if row["指标名称"] == "绩效总分"
        )
        metric["省区排名"] = 1
        metric["省区总人数"] = 100
        metric["部门排名"] = 21
        metric["部门总人数"] = 100

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("| 月平均绩效得分（不含其他奖惩） | 108分 |", markdown)
        self.assertNotIn("TOP", markdown.split("## 1.2", 1)[0].split("## 1.1", 1)[1])

    def test_top_uses_5_percent_buckets_through_top_20(self):
        cases = ((5, "TOP5%"), (6, "TOP10%"), (11, "TOP15%"), (16, "TOP20%"))
        for business_rank, expected in cases:
            with self.subTest(business_rank=business_rank):
                response = copy.deepcopy(self.sample_response)
                metric = next(
                    row["指标数据"]
                    for row in response["data"]["章节数据"]
                    if row["指标名称"] == "绩效总分"
                )
                metric["部门排名"] = business_rank
                metric["部门总人数"] = 100

                markdown, _stats = format_chapter1_data(response, period="202606")

                self.assertIn(f"108分（{expected}）", markdown)

    def test_bonus_warning_table_marks_unconfirmed_rules_as_pending(self):
        markdown, _stats = format_chapter1_data(self.sample_response, period="202606")

        self.assertIn("|  | 距离80%达成率（发放硬性条件）还差 | 待补充 |", markdown)
        self.assertIn("|  | 距离同期销量持平（负增长将同比例打折）还差 | 10万 |", markdown)
        self.assertIn("|  | 距离100%达成率还差 | 待补充 |", markdown)
        self.assertIn("|  | 合计（潜在逾期总额） | 80万 |", markdown)
        self.assertIn("|  | 25年同期逾期金额（含法诉，仅考虑25年同期，不考虑交接后的逾期） | 60万 |", markdown)
        self.assertIn("（1）0逾期则奖金100%发放", markdown)
        self.assertIn("逐季度按0.85打折", markdown)

    def test_quarter_bonus_amounts_are_rounded_to_integer_wan(self):
        response = copy.deepcopy(self.sample_response)
        quarter_sales = next(
            row for row in response["data"]["章节数据"] if row["指标名称"] == "个人季度实际销量"
        )
        quarter_sales["指标数据"]["实际值"] = "48.888"

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("| 个人季度实际销量 | 本季度累计销量 | 49万 |", markdown)
        self.assertNotIn("| 个人季度实际销量 | 本季度累计销量 | 48.888万 |", markdown)

    def test_conflicting_duplicate_rate_is_pending(self):
        response = copy.deepcopy(self.sample_response)
        duplicate = copy.deepcopy(
            next(row for row in response["data"]["章节数据"] if row["指标名称"] == "个人季度实际销量")
        )
        duplicate["指标数据"]["达成率"] = "0.411"
        response["data"]["章节数据"].append(duplicate)

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("|  | 当前达成率 | 待补充 |", markdown)

    def test_profit_bonus_base_uses_confirmed_profit_ladder(self):
        self.assertEqual(
            profit_bonus_base(20),
            ("0.3", "若到年底分摊前利润在40万-60万（含）之间，奖金基数为0.6。"),
        )
        self.assertEqual(
            profit_bonus_base(45),
            ("0.6", "若到年底分摊前利润在60万-80万（含）之间，奖金基数为1.2。"),
        )
        self.assertEqual(
            profit_bonus_base(410),
            ("12", "若到年底分摊前利润在400万以上，奖金基数为12。"),
        )
        self.assertEqual(
            profit_bonus_base(None),
            ("待补充", "若到年底分摊前利润在60万-80万（含）之间，奖金基数为1.2。"),
        )

    def test_year_end_warning_calculates_current_base_without_api_base(self):
        markdown, _stats = format_chapter1_data(self.sample_response, period="202606")

        self.assertIn("奖金基数为0.3。若到年底分摊前利润在40万-60万（含）之间，奖金基数为0.6", markdown)

    def test_year_end_warning_combines_api_base_with_confirmed_next_bracket(self):
        response = copy.deepcopy(self.sample_response)
        response["data"]["章节数据"].append(
            {
                "指标名称": "奖金基数",
                "指标路径": "",
                "指标数据": {"实际值": "0.6", "单位": "万元", "日期类型": "年"},
            }
        )

        markdown, _stats = format_chapter1_data(response, period="202606")

        self.assertIn("奖金基数为0.6。若到年底分摊前利润在40万-60万（含）之间，奖金基数为0.6", markdown)

    def test_generator_accepts_full_response(self):
        markdown = Chapter1Generator(data=self.sample_response, period="202606").run()
        self.assertIn("# 一、绩效得分与预警", markdown)
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
        self.assertIn('<span class="rank-current">5</span><span class="rank-total">/26</span>', html)
        self.assertIn(".rank-table .rank-current", html)
        self.assertIn(".rank-table .rank-total", html)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
