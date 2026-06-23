"""测试第五章应收分析数据契约与接口预留。"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ReportGenerator.chapter5_generator import (
    Chapter5Generator,
    amount_to_wan,
    build_chapter5_action_context,
    format_chapter5_data,
    format_chapter5_data_with_ai,
    infer_chapter5_omit,
    month_labels,
    normalize_chapter5_data,
)


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "Data" / "fixtures" / "chapter5_mock.json"


class Chapter5GeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_accepts_future_module5_interface_shell(self):
        response = {
            "code": 1,
            "message": "success",
            "data": {
                "月份": "",
                "部门编码": "",
                "区域经理工号": "",
                "部门名称": "",
                "区域经理姓名": "",
                "岗位名称": "",
                "客户编码": "",
                "客户名称": "",
                "章节名称": "",
                "章节数据": [],
            },
            "timestamp": 1781528012359,
            "executeTime": 10,
        }

        data = normalize_chapter5_data(response, period="202606")

        self.assertEqual(data.metadata["月份"], "202606")
        self.assertIsNone(data.receivable_tree)
        self.assertIn("接口章节数据为空", data.warnings[0])

    def test_normalizes_mock_contract_and_sorts_top_lists(self):
        data = normalize_chapter5_data(self.sample_response)

        self.assertEqual(data.metadata["月份"], "202606")
        self.assertEqual(data.receivable_tree.name, "应收款项")
        self.assertEqual(data.receivable_tree.amount.value, 100)
        self.assertEqual([row.customer_name for row in data.overdue_top_customers], ["A客户", "B客户", "C客户", "D客户", "E客户"])
        self.assertEqual([row.customer_name for row in data.financial_expense_top_customers], ["A客户", "B客户", "C客户"])

    def test_omit_rule_converts_yuan_to_wan(self):
        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "receivable_tree": {
                    "name": "应收款项",
                    "amount": 90000,
                    "unit": "元",
                },
                "章节数据": [],
            }
        }

        data = normalize_chapter5_data(response)
        omit = infer_chapter5_omit(data)

        self.assertTrue(omit["是否省略第五章"])
        self.assertEqual(omit["依据"]["value_wan"], 9)

    def test_omit_rule_includes_exact_10_wan_boundary(self):
        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "receivable_tree": {
                    "name": "应收款项",
                    "amount": 10,
                    "unit": "万元",
                },
                "章节数据": [],
            }
        }

        data = normalize_chapter5_data(response)
        omit = infer_chapter5_omit(data)

        self.assertTrue(omit["是否省略第五章"])
        self.assertEqual(omit["原因"], "个人应收款项小于等于 10 万")

    def test_omit_rule_keeps_chapter_above_10_wan(self):
        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "receivable_tree": {
                    "name": "应收款项",
                    "amount": 10.01,
                    "unit": "万元",
                },
                "章节数据": [],
            }
        }

        data = normalize_chapter5_data(response)
        omit = infer_chapter5_omit(data)

        self.assertFalse(omit["是否省略第五章"])
        self.assertEqual(omit["原因"], "个人应收款项大于 10 万")

    def test_missing_receivable_total_does_not_omit(self):
        data = normalize_chapter5_data({"data": {"月份": "202606", "章节数据": []}})
        omit = infer_chapter5_omit(data)

        self.assertFalse(omit["是否省略第五章"])
        self.assertIn("缺个人应收款项总额", omit["原因"])

    def test_builds_first_step_markdown_from_mock(self):
        markdown, stats = format_chapter5_data(self.sample_response)

        self.assertIn("# 五、应收分析", markdown)
        self.assertIn("## 5.1 应收款项概况", markdown)
        self.assertIn("应收款项总额：100.0万元", markdown)
        self.assertIn("- 应收账款 90.0万元", markdown)
        self.assertIn("备注：逾期金额含诉讼，保证金不含保函。", markdown)
        self.assertIn("| 客户名称 | 应收账款 | 其中：逾期账款 |", markdown)
        self.assertIn("| A客户 | 300000元 | 120000元 |", markdown)
        self.assertIn("◇ **7月新增到期款金额排名前五客户：**", markdown)
        self.assertIn("| 客户名称 | 7月新增到期款 |", markdown)
        self.assertIn("◇ 当年增加减值损失=应收减值16.0万元+工抵房减值6.0万元+其他类型减值4.0万元", markdown)
        self.assertIn("| 客户名称 | 截止5月应收金额 | 当年增加减值损失 | 其中：应收减值（含坏账） | 工抵房减值 | 其他类型减值（保证金、商票、票证等） |", markdown)
        self.assertIn("| A客户 | 30.0万元 | 8.0万元 | 5.0万元 | 2.0万元 | 1.0万元 |", markdown)
        self.assertIn("◇ **7月若未清收预计跳账龄的 TOP5 客户**", markdown)
        self.assertIn("| 账龄跳到 | 净增加减值金 | 1 年≤账龄＜2 年 |  | 2 年≤账龄＜3 年 |  | 账龄 ≥3 年 |  |", markdown)
        self.assertIn("| 客户名称 | 额 | 应收金额 | 减值损失 | 应收金额 | 减值损失 | 应收金额 | 减值损失 |", markdown)
        self.assertIn("◇ 6月财务费用6元=利息支出8元-利息收入2元", markdown)
        self.assertIn("◇ 6月财务费用排名前三的客户为A客户（3000元）、B客户（2000元）、C客户（1000元）。", markdown)
        self.assertIn("| 客户名称 | 财务费用 |", markdown)
        self.assertFalse(stats["省略判断"]["是否省略第五章"])
        self.assertEqual(stats["逾期客户数"], 5)

    def test_builds_receivable_tree_from_flat_metric_paths(self):
        def metric(name, path, value, unit="万元"):
            return {
                "指标名称": name,
                "指标路径": path,
                "指标数据": {"实际值": str(value), "单位": unit},
            }

        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "章节数据": [
                    metric("应收款项", "五、应收分析-应收款项", 99.162),
                    metric("应收票据", "五、应收分析-应收票据", 0),
                    metric("保证金", "五、应收分析-保证金", 0),
                    metric("供应链票证", "五、应收分析-供应链票证", 0),
                    metric("应收账款", "五、应收分析-应收账款", 99.162),
                    metric("经销", "五、应收分析-应收账款-经销", 74.353),
                    metric("逾期（含诉讼）", "五、应收分析-应收账款-经销-逾期（含诉讼）", 22.24),
                    metric("直销", "五、应收分析-应收账款-直销", 24.809),
                    metric("暴雷直销应收", "五、应收分析-应收账款-直销-暴雷直销应收", 24.809),
                    metric("逾期", "五、应收分析-应收账款-直销-暴雷直销应收-逾期", 24.809),
                    metric("非暴雷直销应收", "五、应收分析-应收账款-直销-非暴雷直销应收", 0),
                    metric("逾期", "五、应收分析-应收账款-直销-非暴雷直销应收-逾期", 0),
                ],
            }
        }

        markdown, stats = format_chapter5_data(response)

        self.assertIn("- 应收账款 99.2万元", markdown)
        self.assertIn("  - 经销 74.4万元", markdown)
        self.assertIn("    - 逾期（含诉讼） 22.2万元", markdown)
        self.assertIn("  - 直销 24.8万元", markdown)
        self.assertIn("    - 暴雷直销应收 24.8万元", markdown)
        self.assertIn("      - 逾期 24.8万元", markdown)
        self.assertEqual(stats["cleaned_data"]["receivable_tree"]["children"][3]["name"], "应收账款")

    def test_generator_accepts_full_response(self):
        markdown = Chapter5Generator(data=self.sample_response, period="202606").run()
        self.assertIn("### 行动指南：", markdown)

    def test_month_and_unit_helpers(self):
        self.assertEqual(month_labels("202606"), ("6月", "7月"))
        self.assertEqual(month_labels("202612"), ("12月", "1月"))
        self.assertEqual(amount_to_wan(90000, "元"), 9)
        self.assertEqual(amount_to_wan(9, "万元"), 9)
        self.assertIsNone(amount_to_wan(9, "未知"))

    def test_builds_action_context_for_ai_writer(self):
        data = normalize_chapter5_data(self.sample_response)
        omit = infer_chapter5_omit(data)

        context = build_chapter5_action_context(data, omit)

        self.assertEqual(context["metadata"]["月份"], "202606")
        self.assertEqual(context["应收款项总额"]["display"], "100.0万元")
        self.assertEqual(context["逾期金额前五客户"][0]["客户名称"], "A客户")
        self.assertEqual(context["减值损失影响金额TOP5客户"][0]["金额"]["display"], "8.0万元")
        self.assertIn("1年<=账龄<2年", context["预计跳账龄TOP5客户"][0]["账龄区间"])


class Chapter5AIWriterTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    async def test_ai_action_guide_only_replaces_action_guide(self):
        async def fake_model(_system_prompt, user_prompt):
            self.assertIn("逾期金额前五客户", user_prompt)
            return "行动指南：请优先跟进 A客户 逾期清收，并结合预计跳账龄客户制定本月回款计划。"

        markdown, stats = await format_chapter5_data_with_ai(
            self.sample_response,
            period="202606",
            model=fake_model,
        )

        self.assertEqual(stats["行动指南生成方式"], "AI")
        self.assertIn("◇ 请优先跟进 A客户 逾期清收，并结合预计跳账龄客户制定本月回款计划。", markdown)
        self.assertIn("◇ 当年增加减值损失=应收减值16.0万元+工抵房减值6.0万元+其他类型减值4.0万元", markdown)
        self.assertIn("| 客户名称 | 截止5月应收金额 | 当年增加减值损失 |", markdown)
        self.assertNotIn("◇ 行动指南：", markdown)

    async def test_ai_action_guide_falls_back_when_model_missing(self):
        markdown, stats = await format_chapter5_data_with_ai(self.sample_response, period="202606")

        self.assertEqual(stats["行动指南生成方式"], "规则")
        self.assertIn("◇ 当年补提减值损失，需要减少应收、缩短账龄", markdown)


if __name__ == "__main__":
    unittest.main()
