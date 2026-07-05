"""第六章唯一公开入口的真实字段结构测试。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ReportGenerator.chapter6_generator import PENDING, build_chapter6_apipost_checklist, format_chapter6_data
from ReportGenerator.chapter6_renderer import _markdown_to_html


def _load_real_response() -> dict:
    def row(name, path, actual, same, unit="元", date_type="月"):
        return {"指标名称": name, "指标路径": path, "指标数据": {
            "实际值": str(actual), "同期数": same, "单位": unit, "日期类型": date_type,
        }}
    c = "六、费用分析"
    rows = [
        row("差旅费总额", f"{c}-差旅费-差旅费总额", "7115.500", 0),
        row("交通费", f"{c}-差旅费-交通费", "418.000", 0),
        row("住宿费", f"{c}-差旅费-住宿费", "1337.500", 0),
        row("车辆费", f"{c}-差旅费-车辆费", "3840.000", 0),
        row("其他费用", f"{c}-差旅费-其他费用", "1520.000", 0),
        row("出差天数", f"{c}-差旅费-出差天数", "49.000", 0, "天"),
        row("交通费/天", f"{c}-差旅费-每天花费金额-交通费/天", "8.530", 0),
        row("住宿费/天", f"{c}-差旅费-每天花费金额-住宿费/天", "27.300", 0),
        row("车辆费/天", f"{c}-差旅费-每天花费金额-车辆费/天", "78.370", 0),
        row("其他费用/天", f"{c}-差旅费-每天花费金额-其他费用/天", "31.020", 0),
        row("样板样漆费用", f"{c}-样板样漆费用-样板样漆费用", "4398.500", 4172.47),
        row("地坪漆", f"{c}-样板样漆费用-样板样漆费用-地坪漆", "1429.200", 2002.2),
        row("真石漆", f"{c}-样板样漆费用-样板样漆费用-真石漆", "894.400", 0),
        row("水包水", f"{c}-样板样漆费用-样板样漆费用-水包水", "516.000", 0),
    ]
    return {"code": 1, "data": {"区域经理工号": "06427", "月份": "202606", "章节名称": c, "章节数据": rows}}


def _load_context_response() -> dict:
    chapter6 = _load_real_response()
    chapter2 = {"code": 1, "data": {"章节名称": "二、利润概况", "章节数据": [
        {"指标名称": "营业收入（不含税）", "指标路径": "二、利润概况-营业收入（不含税）", "指标数据": {
            "实际值": "13.857", "同期数": 0, "单位": "万元", "日期类型": "月",
        }},
    ]}}
    chapter3 = {"code": 1, "data": {"章节名称": "三、销量分析", "章节数据": [
        {"指标名称": "销量", "指标路径": "三、销量分析-销量", "指标数据": {
            "实际值": "15.659", "同期数": 44.275, "单位": "万", "日期类型": "月",
        }},
        {"指标名称": "地坪漆", "指标路径": "三、销量分析-各产品销量-地坪漆", "指标数据": {
            "实际值": "55.326", "同期数": 59.687, "单位": "万", "日期类型": "年",
        }},
        {"指标名称": "真石漆", "指标路径": "三、销量分析-各产品销量-真石漆", "指标数据": {
            "实际值": "7.217", "同期数": 21.152, "单位": "万", "日期类型": "年",
        }},
        {"指标名称": "水包水", "指标路径": "三、销量分析-各产品销量-水包水", "指标数据": {
            "实际值": "0.133", "同期数": 1.278, "单位": "万", "日期类型": "年",
        }},
    ]}}
    chapter5 = {"code": 1, "data": {"章节名称": "五、应收分析", "章节数据": [
        {"指标名称": "个人本月新增到期款", "指标路径": "五、应收分析-个人本月新增到期款", "指标数据": {
            "实际值": "15.131", "同期数": 0, "单位": "万元", "日期类型": "",
        }},
    ]}}
    return {2: chapter2, 3: chapter3, 5: chapter5, 6: chapter6}


def _generate():
    return format_chapter6_data(_load_real_response(), period="202605")


def test_public_generator_uses_strict_mapping_for_real_response():
    markdown, stats = _generate()

    assert "5月费用4399元" in markdown
    assert "出差天数49天" in markdown
    assert "5月差旅费7116元" in markdown
    assert "field_sources" in stats


def test_real_response_identity_and_shape():
    data = _load_real_response()["data"]

    assert data["区域经理工号"] == "06427"
    assert data["月份"] == "202606"
    assert data["章节名称"] == "六、费用分析"
    assert len(data["章节数据"]) == 14


def test_display_rounding_and_source_precision_are_separated():
    markdown, stats = _generate()
    sources = stats["field_sources"]

    assert "4399元" in markdown
    assert "49天" in markdown
    assert sources["chapter6.sample.total"]["raw_values"] == ["4398.500元"]
    assert sources["chapter6.efficiency.days"]["raw_values"] == ["49.000天"]
    assert sources["chapter6.sample.total"]["calculation"] == "无，直接取接口原始值并保持原始精度"


def test_named_rows_and_top_products_are_mapped_without_array_order():
    markdown, stats = _generate()
    sources = stats["field_sources"]

    assert sources["chapter6.travel.total"]["status"] == "正常"
    assert sources["chapter6.efficiency.daily_total"]["status"] == "正常"
    assert sources["chapter6.sample.top_products"]["matched_count"] == 3
    assert "地坪漆1429元、真石漆894元、水包水516元" in markdown


def test_path_only_rows_are_mapped_when_metric_name_is_blank():
    response = json.loads(json.dumps(_load_real_response(), ensure_ascii=False))
    for item in response["data"]["章节数据"]:
        item["指标名称"] = ""
        item["指标路径"] = item["指标路径"] + "-"

    markdown, stats = format_chapter6_data(response, period="202605")
    sources = stats["field_sources"]

    assert sources["chapter6.travel.total"]["status"] == "正常"
    assert sources["chapter6.sample.total"]["status"] == "正常"


def test_sample_total_ignores_blank_placeholder_when_named_month_row_exists():
    response = json.loads(json.dumps(_load_real_response(), ensure_ascii=False))
    c = "六、费用分析"
    response["data"]["章节数据"] = [
        {
            "指标名称": "",
            "指标路径": f"{c}-样板样漆费用-样板样漆费用-",
            "指标数据": {"实际值": "0.000", "同期数": 0, "单位": "元", "日期类型": "月"},
        },
        {
            "指标名称": "样板样漆费用",
            "指标路径": f"{c}-样板样漆费用-样板样漆费用",
            "指标数据": {"实际值": "163.250", "同期数": 0, "单位": "元", "日期类型": "月"},
        },
    ]

    markdown, stats = format_chapter6_data(response, period="202605")
    source = stats["field_sources"]["chapter6.sample.total"]

    assert "5月费用163元，同比增加163元。" in markdown
    assert "其中费用排名前三的产品" not in markdown
    assert "产品为" not in markdown
    assert source["status"] == "正常"
    assert source["raw_values"] == ["163.250元"]


def test_confirmed_formulas_are_applied():
    markdown, stats = _generate()
    sources = stats["field_sources"]

    assert sources["chapter6.travel.yoy_rate"]["status"] == "正常"
    assert sources["chapter6.sample.yoy_delta"]["status"] == "正常"
    assert "同比增长100%（同期数为0）" in markdown
    assert "平均每天花费145元" in markdown
    assert "交通费9元/天、住宿费27元/天、车辆费78元/天、其他31元/天" in markdown
    assert "交通费同比增加418元、住宿费同比增加1338元、车辆费同比增加3840元、其他同比增加1520元" in markdown
    assert "备注：5月出差天数是按差旅报销流程申请日期" in markdown
    assert "同比增加226元" in markdown
    assert "同比增长5.4%，同比差额226元" not in markdown
    assert "同比差额" not in markdown
    assert "MODULE=6" not in markdown


def test_yoy_delta_uses_directional_wording():
    response = _load_real_response()
    for item in response["data"]["章节数据"]:
        name = item["指标名称"]
        if name == "交通费":
            item["指标数据"]["同期数"] = 500
        elif name == "住宿费":
            item["指标数据"]["同期数"] = "1337.500"

    markdown, _ = format_chapter6_data(response, period="202605")

    assert "交通费同比减少82元" in markdown
    assert "住宿费同比持平" in markdown
    assert "车辆费同比增加3840元" in markdown


def test_travel_total_yoy_rate_uses_directional_wording():
    response = _load_real_response()
    for item in response["data"]["章节数据"]:
        if item["指标名称"] == "差旅费总额":
            item["指标数据"]["同期数"] = "8115.500"

    markdown, _ = format_chapter6_data(response, period="202605")

    assert "5月差旅费7116元，同比下降12.3%" in markdown
    assert "同比增长-" not in markdown


def test_action_guide_uses_cross_chapter_rules_when_context_is_available():
    markdown, stats = format_chapter6_data(
        _load_real_response(),
        period="202605",
        context_raw_data=_load_context_response(),
    )

    assert "本月差旅费增长、但收入下滑且本月新增逾期，需警惕出差效率与出差质量。" in markdown
    assert "样板样漆费用增加但地坪漆、真石漆、水包水等对应产品收入下滑，需关注样板样漆费用投入产出效率。" in markdown
    assert "固定模板规则" not in markdown
    assert stats["field_sources"]["chapter6.action.travel"]["status"] == "正常"


def test_zero_travel_days_are_not_reported_as_missing_data():
    response = _load_real_response()
    for item in response["data"]["章节数据"]:
        if item["指标名称"] == "差旅费总额":
            item["指标数据"]["实际值"] = "0.000"
        if item["指标名称"] == "出差天数":
            item["指标数据"]["实际值"] = "0.000"

    markdown, stats = format_chapter6_data(response, period="202605")

    assert "出差效率：5月出差天数0天。" in markdown
    assert "平均每天花费" not in markdown
    assert "平均每天花费待补充" not in markdown
    assert stats["field_sources"]["chapter6.efficiency.daily_total"]["status"] == "不适用"


def test_zero_travel_total_and_same_period_hide_category_yoy_details():
    response = _load_real_response()
    for item in response["data"]["章节数据"]:
        if item["指标名称"] == "差旅费总额":
            item["指标数据"]["实际值"] = "0.000"
            item["指标数据"]["同期数"] = "0.000"

    markdown, _ = format_chapter6_data(response, period="202605")
    travel_section = markdown.split("## 6.2", 1)[0]

    assert "5月差旅费0元，同比持平。" in travel_section
    assert "其中交通费同比" not in travel_section


def test_action_guide_falls_back_to_neutral_text_when_rules_do_not_trigger():
    markdown, stats = format_chapter6_data(_load_real_response(), period="202605")

    assert "## 6.3 行动指南" in markdown
    assert "本月费用未触发重点预警" in markdown
    assert "\n待补充\n" not in markdown
    assert stats["field_sources"]["chapter6.action.travel"]["status"] == "未触发"


def test_cleaned_data_keeps_full_report_downstream_view():
    _, stats = _generate()
    cleaned = stats["cleaned_data"]

    assert cleaned["travel_expense"]["efficiency"]["days"] == "49.000"
    assert cleaned["sample_paint_expense"]["total"]["value"] == "4398.500"
    assert cleaned["sample_paint_expense"]["total"]["same_period"] == "4172.47"
    assert cleaned["sample_paint_expense"]["total"]["yoy_value"] == "4172.47"
    assert cleaned["sample_paint_expense"]["by_product"][0]["name"] == "地坪漆"


def test_checklist_has_required_columns_and_copyable_search():
    _, stats = _generate()
    checklist = build_chapter6_apipost_checklist(stats)

    assert "| 报告位置 | ApiPost搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态 |" in checklist
    assert '`"指标名称": "差旅费总额"`' in checklist
    assert '`"指标路径": "六、费用分析-差旅费-差旅费总额"`' in checklist
    assert '`"日期类型": "月"`' in checklist
    assert "ZEMPLOYEE=06427" in checklist


def test_renderer_marks_pending_values_red():
    response = _load_real_response()
    response["data"]["章节数据"] = [
        item
        for item in response["data"]["章节数据"]
        if item["指标名称"] != "样板样漆费用"
    ]
    markdown, _ = format_chapter6_data(response, period="202605")
    html = _markdown_to_html(markdown)

    assert '<span class="pending">待补充</span>' in html
