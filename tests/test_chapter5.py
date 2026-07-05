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

    def test_omitted_chapter_still_outputs_explanation_markdown(self):
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

        markdown, stats = format_chapter5_data(response)

        self.assertTrue(stats["省略判断"]["是否省略第五章"])
        self.assertIn("# 五、应收分析", markdown)
        self.assertIn("个人应收款项总额：10.0万元。", markdown)
        self.assertIn("本章按规则省略：个人应收款项小于等于 10 万。", markdown)

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
        self.assertIn("| 客户名称 | 截止6月应收金额 | 当年增加减值损失 | 其中：应收减值（含坏账） | 工抵房减值 | 其他类型减值（保证金、商票、票证等） |", markdown)
        self.assertIn("| A客户 | 30.0万元 | 8.0万元 | 5.0万元 | 2.0万元 | 1.0万元 |", markdown)
        self.assertIn("◇ **7月未清收预计跳账龄的 TOP5 客户**", markdown)
        self.assertIn("预计跳账龄客户明细：", markdown)
        self.assertIn("| 账龄跳到 | 净增加减值金 | 1 年≤账龄＜2 年 |  | 2 年≤账龄＜3 年 |  | 账龄 ≥3 年 |  |", markdown)
        self.assertIn("| 客户名称 | 额 | 应收金额 | 减值损失 | 应收金额 | 减值损失 | 应收金额 | 减值损失 |", markdown)
        self.assertIn("◇ 6月财务费用6元=利息支出8元-利息收入2元", markdown)
        self.assertIn("◇ 6月财务费用排名前三的客户为A客户（3000元）、B客户（2000元）、C客户（1000元）。", markdown)
        self.assertIn("| 客户名称 | 财务费用 |", markdown)
        self.assertFalse(stats["省略判断"]["是否省略第五章"])
        self.assertEqual(stats["逾期客户数"], 5)

    def test_path_only_rows_with_trailing_dash_map_summary_and_top_customers(self):
        def metric(path, value, customer_code="", customer_name="", unit="万元"):
            return {
                "指标名称": "",
                "指标路径": f"{path.rstrip('-')}-",
                "客户编码": customer_code,
                "客户名称": customer_name,
                "指标数据": {"实际值": str(value), "单位": unit},
            }

        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "章节数据": [
                    metric("五、应收分析-应收款项", 122.928),
                    metric("五、应收分析-应收账款", 122.928),
                    metric("五、应收分析-应收账款-经销", 122.928),
                    metric("五、应收分析-个人本月新增到期款", 53.865),
                    metric("五、应收分析-当年增加减值损失", 0.710),
                    metric("五、应收分析-当年增加减值损失-应收减值（含坏账）", 0.710),
                    metric("五、应收分析-当年增加减值损失-工抵房减值", 0),
                    metric("五、应收分析-当年增加减值损失-其他类型减值", 0),
                    metric("五、应收分析-本月财务费用", 0.512),
                    metric("五、应收分析-本月财务费用-利息支出", 0.512),
                    metric("五、应收分析-本月财务费用-利息收入", 0),
                    metric("五、应收分析-本月财务费用-利息支出-应收账款资金占用费", 0.512),
                    metric("五、应收分析-本月财务费用-利息支出-应收票据资金占用费", 0),
                    metric("五、应收分析-本月财务费用-利息支出-其他类型资金占用费", 0),
                    metric("五、应收分析-减值损失影响金额TOP5客户-应收金额", 19.361, "C001", "A客户"),
                    metric("五、应收分析-减值损失影响金额TOP5客户-当年增加减值损失", 0.570, "C001", "A客户"),
                    metric("五、应收分析-减值损失影响金额TOP5客户-应收减值（含坏账）", 0.570, "C001", "A客户"),
                    metric("五、应收分析-减值损失影响金额TOP5客户-工抵房减值", 0, "C001", "A客户"),
                    metric("五、应收分析-减值损失影响金额TOP5客户-其他类型减值", 0, "C001", "A客户"),
                    metric("五、应收分析-本月若未清收预计跳账龄的TOP5客户-净增加减值金额", 0, "C001", "A客户"),
                    metric("五、应收分析-本月财务费用-财务费用排名前三的客户", 0.081, "C001", "A客户"),
                ],
            }
        }

        markdown, stats = format_chapter5_data(response, period="202605")

        self.assertIn("应收款项总额：122.9万元", markdown)
        self.assertIn("◇ 当年增加减值损失=应收减值0.7万元+工抵房减值0.0万元+其他类型减值0.0万元", markdown)
        self.assertIn("◇ 5月财务费用5120元=利息支出5120元-利息收入0元", markdown)
        self.assertIn("| A客户 | 19.4万元 | 0.6万元 | 0.6万元 | 0.0万元 | 0.0万元 |", markdown)
        self.assertIn("5月财务费用排名前三的客户为A客户（810元）", markdown)
        self.assertEqual(stats["减值损失客户数"], 1)
        self.assertEqual(stats["财务费用客户数"], 1)

    def test_impairment_receivable_header_uses_report_period_month(self):
        markdown, _stats = format_chapter5_data(self.sample_response, period="202605")

        self.assertIn("| 客户名称 | 截止5月应收金额 | 当年增加减值损失 |", markdown)
        self.assertNotIn("| 客户名称 | 截止4月应收金额 | 当年增加减值损失 |", markdown)

    def test_empty_overdue_and_due_top_lists_render_no_customer_messages(self):
        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "receivable_tree": {
                    "name": "应收款项",
                    "amount": 99.162,
                    "unit": "万元",
                },
                "next_month_due_total": {"value": 0, "unit": "万元"},
                "章节数据": [],
            }
        }

        markdown, stats = format_chapter5_data(response, period="202605")

        self.assertIn("◇ **暂无逾期金额前五客户**", markdown)
        self.assertIn("◇ **暂无6月新增到期款**", markdown)
        self.assertNotIn("当前数据未提供逾期客户明细", markdown)
        self.assertNotIn("当前数据未提供次月新增到期款客户明细", markdown)
        self.assertNotIn("| 客户名称 | 应收账款 | 其中：逾期账款 |", markdown)
        self.assertNotIn("| 客户名称 | 6月新增到期款 |", markdown)
        self.assertNotIn("6月新增到期款0.0万元，金额排名前五客户", markdown)
        self.assertEqual(stats["逾期客户数"], 0)
        self.assertEqual(stats["次月到期客户数"], 0)

    def test_impairment_customer_zero_detail_rows_are_grouped_by_customer(self):
        def metric(name, value, customer_code, customer_name):
            return {
                "指标名称": name,
                "指标路径": f"五、应收分析-减值损失影响金额TOP5客户-{name}",
                "客户编码": customer_code,
                "客户名称": customer_name,
                "指标数据": {"实际值": str(value), "单位": "万元"},
            }

        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "章节数据": [
                    metric("工抵房减值", "0.000", "C001", "A客户"),
                    metric("其他类型减值", "0.000", "C001", "A客户"),
                    metric("工抵房减值", "0.000", "C002", "B客户"),
                    metric("其他类型减值", "0.000", "C002", "B客户"),
                    metric("应收金额", "30.000", "C002", "B客户"),
                    metric("当年增加减值损失", "1.200", "C002", "B客户"),
                    metric("应收减值（含坏账）", "1.200", "C002", "B客户"),
                    metric("应收金额", "10.000", "C001", "A客户"),
                    metric("当年增加减值损失", "0.500", "C001", "A客户"),
                    metric("应收减值（含坏账）", "0.500", "C001", "A客户"),
                ],
            }
        }

        markdown, stats = format_chapter5_data(response, period="202605")

        self.assertIn("| B客户 | 30.0万元 | 1.2万元 | 1.2万元 | 0.0万元 | 0.0万元 |", markdown)
        self.assertIn("| A客户 | 10.0万元 | 0.5万元 | 0.5万元 | 0.0万元 | 0.0万元 |", markdown)
        self.assertEqual(stats["减值损失客户数"], 2)

    def test_impairment_top_missing_amount_fields_render_as_zero(self):
        def metric(name, value, customer_code, customer_name):
            return {
                "指标名称": name,
                "指标路径": f"五、应收分析-减值损失影响金额TOP5客户-{name}",
                "客户编码": customer_code,
                "客户名称": customer_name,
                "指标数据": {"实际值": str(value), "单位": "万元"},
            }

        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "章节数据": [
                    metric("当年增加减值损失", "1.066", "C001", "缺应收客户"),
                    metric("应收减值（含坏账）", "1.066", "C001", "缺应收客户"),
                ],
            }
        }

        markdown, stats = format_chapter5_data(response, period="202605")

        self.assertIn("| 缺应收客户 | 0.0万元 | 1.1万元 | 1.1万元 | 0.0万元 | 0.0万元 |", markdown)
        self.assertNotIn("| 缺应收客户 | — |", markdown)
        self.assertEqual(stats["减值损失客户数"], 1)

    def test_zero_aging_jump_data_renders_no_customer_message(self):
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
                    metric("当年增加减值损失", "五、应收分析-当年增加减值损失", 0),
                    metric("净增加减值金额", "五、应收分析-本月若未清收预计跳账龄的TOP5客户-净增加减值金额", 0),
                    metric("1 年≤账龄＜2 年", "五、应收分析-本月若未清收预计跳账龄的TOP5客户-应收金额-1 年≤账龄＜2 年", 0),
                    metric("1 年≤账龄＜2 年", "五、应收分析-本月若未清收预计跳账龄的TOP5客户-减值损失-1 年≤账龄＜2 年", 0),
                ],
            }
        }

        markdown, stats = format_chapter5_data(response, period="202605")

        self.assertIn("◇ **暂无6月未清收预计跳账龄的客户**", markdown)
        self.assertNotIn("◇ **6月未清收预计跳账龄的 TOP5 客户**", markdown)
        self.assertNotIn("◇ **6月若未清收预计跳账龄的 TOP5 客户**", markdown)
        self.assertNotIn("预计跳账龄客户明细：待补充。", markdown)
        self.assertNotIn("预计跳账龄客户明细：", markdown)
        self.assertNotIn("| 账龄跳到 | 净增加减值金 |", markdown)
        self.assertEqual(stats["跳账龄数据状态"], "zero")

    def test_nonzero_aging_jump_data_renders_customer_detail_table(self):
        def metric(name, path, value, customer_code, customer_name, unit="万元"):
            return {
                "指标名称": name,
                "指标路径": path,
                "客户编码": customer_code,
                "客户名称": customer_name,
                "指标数据": {"实际值": str(value), "单位": unit},
            }

        section = "五、应收分析-本月若未清收预计跳账龄的TOP5客户"
        response = {
            "data": {
                "月份": "202606",
                "章节名称": "五、应收分析",
                "章节数据": [
                    metric("应收款项", "五、应收分析-应收款项", 99.162, "", ""),
                    metric("当年增加减值损失", "五、应收分析-当年增加减值损失", 0, "", ""),
                    metric("净增加减值金额", f"{section}-净增加减值金额", 4, "C001", "A客户"),
                    metric("1 年≤账龄＜2 年", f"{section}-应收金额-1 年≤账龄＜2 年", 12, "C001", "A客户"),
                    metric("1 年≤账龄＜2 年", f"{section}-减值损失-1 年≤账龄＜2 年", 2.4, "C001", "A客户"),
                    metric("2 年≤账龄＜3 年", f"{section}-应收金额-2 年≤账龄＜3 年", 8, "C001", "A客户"),
                    metric("2 年≤账龄＜3 年", f"{section}-减值损失-2 年≤账龄＜3 年", 3.2, "C001", "A客户"),
                    metric("账龄≥3 年", f"{section}-应收金额-账龄≥3 年", 3, "C001", "A客户"),
                    metric("账龄≥3 年", f"{section}-减值损失-账龄≥3 年", 1.8, "C001", "A客户"),
                    metric("净增加减值金额", f"{section}-净增加减值金额", 0, "C002", "B客户"),
                ],
            }
        }

        markdown, stats = format_chapter5_data(response, period="202605")

        self.assertIn("◇ **6月未清收预计跳账龄的 TOP5 客户**", markdown)
        self.assertNotIn("◇ **暂无6月未清收预计跳账龄的客户**", markdown)
        self.assertNotIn("◇ **6月若未清收预计跳账龄的 TOP5 客户**", markdown)
        self.assertIn("预计跳账龄客户明细：", markdown)
        self.assertIn("| A客户 | 4.0万元 | 12.0万元 | 2.4万元 | 8.0万元 | 3.2万元 | 3.0万元 | 1.8万元 |", markdown)
        self.assertNotIn("B客户", markdown)
        self.assertEqual(stats["跳账龄数据状态"], "nonzero")

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

    def test_flat_metric_rows_use_customer_name_and_due_total_from_interface(self):
        def metric(name, path, value, unit="万元", customer_name="", customer_code=""):
            return {
                "客户名称": customer_name,
                "客户编码": customer_code,
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
                    metric("个人本月新增到期款", "五、应收分析-个人本月新增到期款", 15.131),
                    metric("应收账款", "五、应收分析-逾期金额前五客户-应收账款", 22.240, customer_name="杭州鹏远装饰工程有限公司", customer_code="ZJ57143015"),
                    metric("逾期账款", "五、应收分析-逾期金额前五客户-应收账款-逾期账款", 22.240, customer_name="杭州鹏远装饰工程有限公司", customer_code="ZJ57143015"),
                    metric("应收账款", "五、应收分析-逾期金额前五客户-应收账款", 12.533, customer_name="杭州锦易置业有限公司", customer_code="ZJ57111423"),
                    metric("逾期账款", "五、应收分析-逾期金额前五客户-应收账款-逾期账款", 12.533, customer_name="杭州锦易置业有限公司", customer_code="ZJ57111423"),
                    metric("本月新增到期款", "五、应收分析-本月新增到期款前五客户-本月新增到期款", 11.049, customer_name="杭州鼎跃建材有限公司", customer_code="ZJ08024671"),
                    metric("本月新增到期款", "五、应收分析-本月新增到期款前五客户-本月新增到期款", 4.082, customer_name="杭州欣荣新型材料有限公司", customer_code="ZJ01071467"),
                ],
            }
        }

        markdown, stats = format_chapter5_data(response, period="202605")

        self.assertIn("◇ **6月新增到期款15.1万元，金额排名前五客户：**", markdown)
        self.assertIn("| 杭州鹏远装饰工程有限公司 | 22.2万元 | 22.2万元 |", markdown)
        self.assertIn("| 杭州鼎跃建材有限公司 | 11.0万元 |", markdown)
        self.assertNotIn("接口未提供名称", markdown)
        self.assertNotIn("客户名称待补充", markdown)
        self.assertEqual(stats["cleaned_data"]["overdue_top_customers"][0]["customer_name"], "杭州鹏远装饰工程有限公司")
        self.assertEqual(stats["cleaned_data"]["overdue_top_customers"][0]["extra"]["customer_code"], "ZJ57143015")
        self.assertEqual(stats["cleaned_data"]["next_month_due_total"]["value"], 15.131)

    def test_generator_accepts_full_response(self):
        markdown = Chapter5Generator(data=self.sample_response, period="202606").run()
        self.assertIn("## 5.4 行动指南", markdown)

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
        self.assertIn("| 客户名称 | 截止6月应收金额 | 当年增加减值损失 |", markdown)
        self.assertNotIn("◇ 行动指南：", markdown)

    async def test_ai_action_guide_falls_back_when_model_missing(self):
        markdown, stats = await format_chapter5_data_with_ai(self.sample_response, period="202606")

        self.assertEqual(stats["行动指南生成方式"], "规则")
        self.assertIn("◇ 当年补提减值损失，需要减少应收、缩短账龄", markdown)


if __name__ == "__main__":
    unittest.main()
