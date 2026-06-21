"""第六章唯一公开入口的真实字段结构测试。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ReportGenerator.chapter6_generator import PENDING, build_chapter6_apipost_checklist, format_chapter6_data
from ReportGenerator.chapter6_renderer import _markdown_to_html


RAW_PATH = ROOT / "Reports" / "chapter6_strict_06427_202606" / "raw" / "employee_06427_month_202606_module_6.json"


def _load_real_response() -> dict:
    return json.loads(RAW_PATH.read_text(encoding="utf-8"))


def _generate():
    return format_chapter6_data(_load_real_response(), period="202606")


def test_public_generator_uses_strict_mapping_for_real_response():
    markdown, stats = _generate()

    assert "6月费用4398.500元" in markdown
    assert "出差天数49.000天" in markdown
    assert "差旅费969元" not in markdown
    assert "field_sources" in stats


def test_real_response_identity_and_shape():
    data = _load_real_response()["data"]

    assert data["区域经理工号"] == "06427"
    assert data["月份"] == "202606"
    assert data["章节名称"] == "六、费用分析"
    assert len(data["章节数据"]) == 43


def test_unique_fields_keep_original_precision_without_conversion():
    markdown, stats = _generate()
    sources = stats["field_sources"]

    assert "4398.500元" in markdown
    assert "49.000天" in markdown
    assert "4398.50元" not in markdown
    assert sources["chapter6.sample.total"]["raw_values"] == ["4398.500元"]
    assert sources["chapter6.efficiency.days"]["raw_values"] == ["49.000天"]
    assert sources["chapter6.sample.total"]["calculation"] == "无，直接取接口原始值并保持原始精度"


def test_conflicting_rows_are_not_assigned_by_order_or_size():
    markdown, stats = _generate()
    sources = stats["field_sources"]

    assert sources["chapter6.travel.total"]["status"] == "重复冲突"
    assert sources["chapter6.efficiency.daily_total"]["status"] == "重复冲突"
    assert "缺产品唯一标识" in sources["chapter6.sample.product1"]["status"]
    assert sources["chapter6.sample.product1"]["matched_count"] == 7
    assert PENDING in markdown
    assert "7115.500元" not in markdown
    assert "1429.200元" not in markdown


def test_missing_fields_are_not_calculated_from_period_or_deduction():
    markdown, stats = _generate()
    sources = stats["field_sources"]

    assert sources["chapter6.travel.yoy_rate"]["status"] == "取值字段缺失"
    assert sources["chapter6.sample.yoy_delta"]["status"] == "取值字段缺失"
    assert "同比增长" not in markdown
    assert "MODULE=6" not in markdown


def test_cleaned_data_keeps_full_report_downstream_view():
    _, stats = _generate()
    cleaned = stats["cleaned_data"]

    assert cleaned["travel_expense"]["efficiency"]["days"] == "49.000"
    assert cleaned["sample_paint_expense"]["total"]["value"] == "4398.500"


def test_checklist_has_required_columns_and_copyable_search():
    _, stats = _generate()
    checklist = build_chapter6_apipost_checklist(stats)

    assert "| 报告位置 | ApiPost搜索内容 | 取值字段 | 原始值 | 报告值 | 处理方式 | 状态 |" in checklist
    assert '`"指标名称": "差旅费"`' in checklist
    assert '`"指标路径": "六、费用分析-差旅费"`' in checklist
    assert '`"日期类型": "月"`' in checklist
    assert "ZEMPLOYEE=06427" in checklist


def test_renderer_marks_pending_values_red():
    markdown, _ = _generate()
    html = _markdown_to_html(markdown)

    assert '<span class="pending">待补充</span>' in html
