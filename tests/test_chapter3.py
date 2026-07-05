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
    build_chapter3_risk_product_names,
    format_chapter3_data,
    normalize_chapter3_records,
)


def metric(
    name,
    path,
    date_type,
    actual,
    target=0.0,
    yoy=0.0,
    deduction=0.0,
    rate="0.000",
    unit="万",
    customer_name="",
    customer_code="",
):
    row = {
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
    if customer_name:
        row["客户名称"] = customer_name
    if customer_code:
        row["客户编码"] = customer_code
    return row


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
        markdown, stats = format_chapter3_data(self.real, period="202605")
        self.assertIn("| 销量 | 5月 | 本季度累计 | 1-5月累计 |", markdown)
        self.assertIn("| 实际 | 15.66 | 48.89 | 145.61 |", markdown)
        self.assertIn("|  | 实际 | 0家 | 1家 | 1家 |", markdown)
        self.assertIn("年度20个存量生效客户目标已完成3个（差距17个），100个出货项目目标已完成26个（差距74个）", markdown)
        self.assertNotIn("15.66万", markdown)
        self.assertEqual(stats["有效指标数"], 72)
        self.assertEqual(stats["conflicts"], [])

    def test_path_only_rows_with_trailing_dash_map_key_sections(self):
        response = json.loads(json.dumps(self.real, ensure_ascii=False))
        for row in response["data"]["章节数据"]:
            row["指标名称"] = ""
            row["指标路径"] = row["指标路径"] + "-"

        markdown, stats = format_chapter3_data(response, period="202605")

        self.assertIn("| 实际 | 15.66 | 48.89 | 145.61 |", markdown)
        self.assertIn("|  | 实际 | 0家 | 1家 | 1家 |", markdown)
        self.assertIn("年度20个存量生效客户目标已完成3个（差距17个），100个出货项目目标已完成26个（差距74个）", markdown)
        self.assertEqual(stats["销量概况数"], 3)
        self.assertGreaterEqual(stats["过程指标数"], 6)

    def test_chapter33_matches_customer_template_without_detail_tables(self):
        markdown, _ = format_chapter3_data(self.real, period="202605")
        self.assertIn("### 正向指标（1-5月）", markdown)
        self.assertIn("产品：**无机矿物内墙涂料8万（↑1991.41%）、一体板7万（↑100.00%）、弹性涂料7万（↑80.11%）表现突出", markdown)
        self.assertIn("客户：**产销客户数同比持平（增减0个）", markdown)
        self.assertIn("项目：**产销项目数同比增长5.13%（增加2个）", markdown)
        self.assertIn("地产系统行业收入增长39.93%，占比增长4.88%", markdown)
        self.assertIn("### 风险指标（1-5月）", markdown)
        self.assertIn("地坪漆55万（↓7.31%），销售量下降6.35%", markdown)
        self.assertIn("客户：**客均销量9万（↓25.05%）", markdown)
        self.assertIn("项目：**单项目销量4万（↓28.71%）", markdown)
        self.assertIn("市政公建行业收入下降44.74%，占比下降8.93%", markdown)
        self.assertIn("工业行业收入下降18.42%，占比增长4.56%", markdown)
        self.assertNotIn("产品收入与销售量明细", markdown)
        self.assertNotIn("行业销量与占比明细", markdown)

    def test_sales_yoy_fields_are_calculated_from_actual_and_yoy(self):
        markdown, _ = format_chapter3_data(self.real, period="202605")
        self.assertIn(MISSING, markdown)
        self.assertIn("| 同比增长率 | -64.6% | -51.9% | -25.0% |", markdown)
        self.assertIn("| 同比差额 | -28.62 | -52.86 | -48.66 |", markdown)

    def test_sales_overview_matches_confirmed_reference_values(self):
        rows = []
        values = {
            "月": ("54.77", "15.659", "44.275", "28.600"),
            "季": ("118.97", "48.888", "101.744", "41.100"),
            "年": ("214.48", "145.611", "194.275", "67.900"),
        }
        for date_type, (target, actual, yoy, rate) in values.items():
            rows.append(metric("销量", "三、销量分析-销量", date_type, actual, yoy=yoy))
            reference_yoy = {"月": "44.27", "季": "101.74", "年": "194.28"}[date_type]
            rows.append(metric("销量", "三、销量分析-销量-销量", date_type, "0.000", target=target, yoy=reference_yoy, rate=rate, unit=""))

        markdown, _ = format_chapter3_data(rows, period="202605")

        self.assertIn("| 目标 | 54.77 | 118.97 | 214.48 |", markdown)
        self.assertIn("| 实际 | 15.66 | 48.89 | 145.61 |", markdown)
        self.assertIn("| 达成率 | 28.6% | 41.1% | 67.9% |", markdown)
        self.assertIn("| 达成差额 | 39.11 | 70.08 | 68.87 |", markdown)
        self.assertIn("| 同比增长率 | -64.6% | -51.9% | -25.1% |", markdown)
        self.assertIn("| 同比差额 | -28.61 | -52.85 | -48.67 |", markdown)

    def test_process_negative_growth_uses_counts_and_calculates_rate(self):
        markdown, _ = format_chapter3_data(self.real, period="202605")
        self.assertIn("负增长（1-5月）指标包含：打样项目数", markdown)
        self.assertIn("|  | 差距 | -3个 | -6个 | -6个 |", markdown)
        self.assertIn("|  | 增长率 | -27% | -32% | -21% |", markdown)

    def test_hides_negative_growth_line_when_sample_count_is_not_down(self):
        rows = [metric("", "三、销量分析-打样项目数-", "年", "29.000", yoy=23.0, unit="个")]
        markdown, _ = format_chapter3_data(rows, period="202605")
        self.assertNotIn("负增长（1-5月）指标包含", markdown)

    def test_process_growth_formula_is_in_apipost_checklist(self):
        checklist = build_chapter3_apipost_checklist(normalize_chapter3_records(self.real), "202606")
        self.assertIn("实际值 - 同期数", checklist)
        self.assertIn("（实际值 - 同期数）÷同期数×100%", checklist)
        self.assertIn("`-20.69%`", checklist)

    def test_customer_decline_top3_uses_customer_level_sales_rows(self):
        rows = [
            metric("客户甲", "三、销量分析-各客户销量-客户甲", "年", "10", yoy="30", unit="万"),
            metric("客户乙", "三、销量分析-各客户销量-客户乙", "年", "5", yoy="35", unit="万"),
            metric("客户丙", "三、销量分析-各客户销量-客户丙", "年", "20", yoy="25", unit="万"),
            metric("客户丁", "三、销量分析-各客户销量-客户丁", "年", "40", yoy="10", unit="万"),
        ]
        markdown, _ = format_chapter3_data(rows, period="202605")
        self.assertIn("1-5月销量下降金额前三的客户包含：客户乙（↓30万）、客户甲（↓20万）、客户丙（↓5万）", markdown)

    def test_customer_decline_top3_uses_supplemented_customer_fields(self):
        path = "三、销量分析-销量-销量下降金额前三的客户"
        rows = [
            metric("销量下降金额前三的客户", path, "年", "-3.820", customer_name="杭州铭匠工程技术有限公司", customer_code="HN37129024"),
            metric("销量下降金额前三的客户", path, "年", "-33.547", customer_name="杭州汇锦新材料有限公司", customer_code="ZJ07023014"),
            metric("销量下降金额前三的客户", path, "年", "-23.696", customer_name="杭州鼎跃建材有限公司", customer_code="ZJ08024671"),
        ]

        markdown, stats = format_chapter3_data(rows, period="202605")
        checklist = build_chapter3_apipost_checklist(normalize_chapter3_records(rows), "202606")

        self.assertIn("1-5月销量下降金额前三的客户包含：杭州汇锦新材料有限公司（↓34万）、杭州鼎跃建材有限公司（↓24万）、杭州铭匠工程技术有限公司（↓4万）", markdown)
        self.assertNotIn(f"1-5月销量下降金额前三的客户包含：{MISSING}", markdown)
        self.assertEqual(stats["conflicts"], [])
        self.assertNotIn("3.3 缺少客户下降金额前三明细", stats["warnings"])
        self.assertIn('"客户名称": "杭州汇锦新材料有限公司"', checklist)
        self.assertIn("客户下降金额前三明细已按接口行级", checklist)

    def test_customer_decline_sentence_is_hidden_when_detail_is_missing(self):
        rows = [
            metric("客均销量", "三、销量分析-销量-客均销量", "年", "26", yoy="80", unit="万"),
        ]

        markdown, stats = format_chapter3_data(rows, period="202605")
        checklist = build_chapter3_apipost_checklist(normalize_chapter3_records(rows), "202606")

        self.assertIn("客户：**客均销量26万", markdown)
        self.assertNotIn("销量下降金额前三的客户包含", markdown)
        self.assertNotIn("3.3 缺少客户下降金额前三明细", stats["warnings"])
        self.assertIn("客户下降金额前三明细未提供，报告不展示该句。", checklist)

    def test_customer_decline_sentence_is_hidden_when_detail_is_non_negative(self):
        path = "三、销量分析-销量-销量下降金额前三的客户"
        rows = [
            metric("客均销量", "三、销量分析-销量-客均销量", "年", "26", yoy="80", unit="万"),
            metric("销量下降金额前三的客户", path, "年", "69.960", customer_name="西安长住久安物资有限公司", customer_code="SX001"),
            metric("销量下降金额前三的客户", path, "年", "0.000", customer_name="零增长客户", customer_code="SX002"),
        ]

        markdown, stats = format_chapter3_data(rows, period="202605")
        checklist = build_chapter3_apipost_checklist(normalize_chapter3_records(rows), "202606")

        customer_line = next(line for line in markdown.splitlines() if line.startswith("* **客户：**客均销量"))
        self.assertNotIn("销量下降金额前三的客户包含", customer_line)
        self.assertNotIn(MISSING, customer_line)
        self.assertNotIn("3.3 缺少客户下降金额前三明细", stats["warnings"])
        self.assertIn("客户下降金额前三明细未出现负数下降金额，报告不展示该句。", checklist)

    def test_absent_risk_dimensions_are_not_reported_as_missing_data(self):
        rows = [
            metric("销量", "三、销量分析-销量", "年", "120", target="100", yoy="80", rate="120.000"),
            metric("产品甲", "三、销量分析-各产品销量-产品甲", "年", "20", yoy="10", unit="万"),
            metric("产品甲", "三、销量分析-各产品销售量-产品甲", "年", "50", yoy="40", unit="吨"),
            metric("地产系统", "三、销量分析-各行业销量-地产系统", "年", "30", yoy="20", unit="万"),
            metric("地产系统", "三、销量分析-各行业收入占比-地产系统", "年", "15", yoy="10", unit="%"),
        ]

        markdown, _ = format_chapter3_data(rows, period="202605")

        self.assertIn("* **产品：**无明显下降产品", markdown)
        self.assertIn("* **行业：**无明显下降行业", markdown)
        risk_section = markdown.split("### 风险指标（1-5月）", 1)[1]
        self.assertNotIn("* **产品：**" + MISSING, risk_section)
        self.assertNotIn("* **行业：**" + MISSING, risk_section)

    def test_absent_positive_dimensions_are_not_reported_as_missing_data(self):
        rows = [
            metric("销量", "三、销量分析-销量", "年", "120", target="100", yoy="80", rate="120.000"),
        ]

        markdown, _ = format_chapter3_data(rows, period="202605")
        positive_section = markdown.split("### 正向指标（1-5月）", 1)[1].split("### 风险指标", 1)[0]

        self.assertIn("* **产品：**无明显增长产品", positive_section)
        self.assertIn("* **行业：**无明显增长行业", positive_section)
        self.assertNotIn("* **产品：**" + MISSING, positive_section)
        self.assertNotIn("* **行业：**" + MISSING, positive_section)

    def test_zero_yoy_process_growth_is_not_reported_as_missing_data(self):
        rows = [
            metric("产销客户数", "三、销量分析-销量-产销客户数", "年", "11", yoy="0", unit="个"),
            metric("产销项目数", "三、销量分析-销量-产销项目数", "年", "16", yoy="0", unit="个"),
            metric("", "三、销量分析-打样项目数-", "月", "1", yoy="0", unit="个"),
        ]

        markdown, _ = format_chapter3_data(rows, period="202605")

        self.assertIn("产销客户数同比增长100.00%（增加11个）", markdown)
        self.assertIn("产销项目数同比增长100.00%（增加16个）", markdown)
        self.assertIn("|  | 增长率 | 100%", markdown)
        self.assertNotIn("同比增长" + MISSING, markdown)

    def test_negative_customer_and_project_counts_move_to_risk_with_directional_words(self):
        rows = [
            metric("产销客户数", "三、销量分析-销量-产销客户数", "年", "3", yoy="18", unit="个"),
            metric("产销项目数", "三、销量分析-销量-产销项目数", "年", "9", yoy="18", unit="个"),
            metric("客均销量", "三、销量分析-销量-客均销量", "年", "26", yoy="80", unit="万"),
            metric("单项目销量", "三、销量分析-销量-单项目销量", "年", "12", yoy="30", unit="万"),
        ]

        markdown, _ = format_chapter3_data(rows, period="202605")
        positive_section = markdown.split("### 正向指标（1-5月）", 1)[1].split("### 风险指标", 1)[0]
        risk_section = markdown.split("### 风险指标（1-5月）", 1)[1]

        self.assertNotIn("产销客户数同比", positive_section)
        self.assertNotIn("产销项目数同比", positive_section)
        self.assertIn("产销客户数同比下降83.33%（减少15个）", risk_section)
        self.assertIn("产销项目数同比下降50.00%（减少9个）", risk_section)
        self.assertNotIn("同比增长-", markdown)
        self.assertNotIn("增加-", markdown)

    def test_risk_product_names_match_chapter33_risk_rule(self):
        rows = [
            metric("真石漆", "三、销量分析-各产品销量-真石漆", "年", "10", yoy="30", unit="万"),
            metric("真石漆", "三、销量分析-各产品销售量-真石漆", "年", "20", yoy="60", unit="万"),
            metric("内墙乳胶漆面漆", "三、销量分析-各产品销量-内墙乳胶漆面漆", "年", "28", yoy="14", unit="万"),
            metric("内墙乳胶漆面漆", "三、销量分析-各产品销售量-内墙乳胶漆面漆", "年", "30", yoy="15", unit="万"),
            metric("只金额下降产品", "三、销量分析-各产品销量-只金额下降产品", "年", "5", yoy="10", unit="万"),
            metric("只金额下降产品", "三、销量分析-各产品销售量-只金额下降产品", "年", "8", yoy="4", unit="万"),
        ]

        self.assertEqual(build_chapter3_risk_product_names({"data": {"章节数据": rows}}), ["真石漆"])

    def test_conflicting_exact_duplicate_becomes_missing(self):
        rows = [
            metric("销量", "三、销量分析-销量-销量", "月", "1.000"),
            metric("销量", "三、销量分析-销量-销量", "月", "2.000"),
        ]
        markdown, stats = format_chapter3_data(rows, period="202605")
        self.assertIn(f"| 实际 | {MISSING} | {MISSING} | {MISSING} |", markdown)
        self.assertEqual(len(stats["conflicts"]), 1)

    def test_does_not_infer_missing_date_type_from_array_order(self):
        rows = [metric("销量", "三、销量分析-销量-销量", "", "15.659")]
        markdown, _ = format_chapter3_data(rows, period="202605")
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
