"""第七章单元测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def _load_fixture() -> dict:
    fixture_path = BASE_DIR / "Data" / "fixtures" / "chapter7_mock.json"
    with fixture_path.open("r", encoding="utf-8") as f:
        return json.load(f)


class TestChapter7DataNormalization:
    def test_normalize_from_full_response(self):
        from ReportGenerator.chapter7_generator import normalize_chapter7_data

        fixture = _load_fixture()
        data = normalize_chapter7_data(fixture, period="202606")

        assert data.metadata["月份"] == "202606"
        assert data.total_visit.actual == 45.0
        assert data.total_visit.target == 60.0
        assert data.total_visit.achievement_rate == 75.0
        assert data.total_visit.deduction_score == -5.0
        assert data.project_visit.actual == 25.0
        assert data.project_visit.target == 30.0
        assert data.project_visit.achievement_rate == 83.3
        assert data.time_allocation.project_ratio == 56.0
        assert data.time_allocation.customer_ratio == 44.0

    def test_normalize_empty_data(self):
        from ReportGenerator.chapter7_generator import normalize_chapter7_data

        data = normalize_chapter7_data({"code": 1, "data": {"月份": "202606"}})
        assert data.total_visit.actual is None
        assert data.time_allocation.project_ratio is None

    def test_normalize_from_api_metric_rows(self):
        from ReportGenerator.chapter7_generator import normalize_chapter7_data

        response = {
            "code": 1,
            "data": {
                "月份": "202606",
                "区域经理工号": "06427",
                "区域经理姓名": "刘晨",
                "章节名称": "七、行销行为",
                "章节数据": [
                    {
                        "指标名称": "拜访总频次",
                        "指标路径": "七、行销行为-拜访量-拜访总频次",
                        "指标数据": {"实际值": "66", "目标值": "60", "达成率": "110", "扣分值": "0"},
                    },
                    {
                        "指标名称": "项目拜访频次",
                        "指标路径": "七、行销行为-拜访量-项目拜访频次",
                        "指标数据": {"实际值": "22", "目标值": "30", "达成率": "73.3", "扣分值": "-2"},
                    },
                    {
                        "指标名称": "项目拜访占比",
                        "指标路径": "七、行销行为-时间分配-项目拜访占比",
                        "指标数据": {"实际值": "0.40"},
                    },
                    {
                        "指标名称": "客户拜访占比",
                        "指标路径": "七、行销行为-时间分配-客户拜访占比",
                        "指标数据": {"实际值": "60"},
                    },
                ],
            },
        }

        data = normalize_chapter7_data(response, period="202606")

        assert data.metadata["区域经理工号"] == "06427"
        assert data.total_visit.actual == 66.0
        assert data.total_visit.target == 60.0
        assert data.total_visit.achievement_rate == 110.0
        assert data.project_visit.actual == 22.0
        assert data.project_visit.target == 30.0
        assert data.project_visit.achievement_rate == 73.3
        assert data.project_visit.deduction_score == -2.0
        assert data.time_allocation.project_ratio == 40.0
        assert data.time_allocation.customer_ratio == 60.0
        assert data.warnings == []


class TestChapter7Markdown:
    def test_build_markdown(self):
        from ReportGenerator.chapter7_generator import normalize_chapter7_data, build_chapter7_markdown

        fixture = _load_fixture()
        data = normalize_chapter7_data(fixture, period="202606")
        md = build_chapter7_markdown(data)

        assert "# 七、行销行为" in md
        assert "## 7.1 拜访量" in md
        assert "拜访总频次" in md
        assert "45次" in md
        assert "75%" in md
        assert "扣绩效" not in md
        assert "还差" not in md
        assert "项目拜访频次" in md
        assert "25次" in md
        assert "83%" in md
        assert "## 7.2 时间分配" in md
        assert "56%" in md
        assert "44%" in md
        assert "## 7.3 行动指南" not in md

    def test_build_markdown_empty_data(self):
        from ReportGenerator.chapter7_generator import normalize_chapter7_data, build_chapter7_markdown

        data = normalize_chapter7_data({"月份": "202606"})
        md = build_chapter7_markdown(data)
        assert "# 七、行销行为" in md
        assert "数据暂未提供" in md

    def test_format_chapter7_data(self):
        from ReportGenerator.chapter7_generator import format_chapter7_data

        fixture = _load_fixture()
        md, stats = format_chapter7_data(fixture, period="202606")

        assert "# 七、行销行为" in md
        assert stats["拜访总频次"] == 45.0
        assert stats["拜访总达成率"] == 75.0

    def test_format_reference_style_from_module7_rows(self):
        from ReportGenerator.chapter7_generator import format_chapter7_data

        response = {
            "code": 1,
            "data": {
                "月份": "202605",
                "章节名称": "七、行销行为诊断",
                "章节数据": [
                    {"指标名称": "拜访量", "指标路径": "七、行销行为诊断-拜访量", "指标数据": {"实际值": "104.000", "单位": "次"}},
                    {"指标名称": "拜访量", "指标路径": "七、行销行为诊断-拜访量", "指标数据": {"实际值": "1.733", "单位": "%"}},
                    {"指标名称": "项目拜访", "指标路径": "七、行销行为诊断-项目拜访", "指标数据": {"实际值": "46.000", "单位": "次"}},
                    {"指标名称": "项目拜访", "指标路径": "七、行销行为诊断-项目拜访", "指标数据": {"实际值": "1.150", "单位": "%"}},
                    {"指标名称": "各类拜访的次数占比", "指标路径": "七、行销行为诊断-时间分配-各类拜访的次数占比", "指标数据": {"实际值": "0.558", "单位": "%"}},
                    {"指标名称": "各类拜访的次数占比", "指标路径": "七、行销行为诊断-时间分配-各类拜访的次数占比", "指标数据": {"实际值": "0.442", "单位": "%"}},
                ],
            },
        }

        md, stats = format_chapter7_data(response, period="202605")

        assert "5月拜访总频次 104次，拜访达成率173%。项目拜访频次 46次，拜访达成率115%。" in md
        assert "44%用于项目拜访，56%用于客户拜访。" in md
        assert "行动指南" not in md
        assert stats["拜访总频次"] == 104.0
        assert stats["拜访总达成率"] == 173.3
        assert stats["项目拜访频次"] == 46.0
        assert stats["项目拜访达成率"] == 115.0
        assert stats["项目拜访占比"] == 44.2
        assert stats["客户拜访占比"] == 55.8

    def test_format_reference_style_prefers_nonzero_duplicate_rows(self):
        from ReportGenerator.chapter7_generator import format_chapter7_data

        response = {
            "code": 1,
            "data": {
                "月份": "202605",
                "章节名称": "七、行销行为诊断",
                "章节数据": [
                    {"指标名称": "拜访量", "指标路径": "七、行销行为诊断-拜访量", "指标数据": {"实际值": "0.000", "单位": "次"}},
                    {"指标名称": "项目拜访", "指标路径": "七、行销行为诊断-项目拜访", "指标数据": {"实际值": "0.000", "单位": "次"}},
                    {"指标名称": "拜访量", "指标路径": "七、行销行为诊断-拜访量", "指标数据": {"实际值": "104.000", "单位": "次"}},
                    {"指标名称": "拜访量", "指标路径": "七、行销行为诊断-拜访量", "指标数据": {"实际值": "1.733", "单位": "%"}},
                    {"指标名称": "项目拜访", "指标路径": "七、行销行为诊断-项目拜访", "指标数据": {"实际值": "46.000", "单位": "次"}},
                    {"指标名称": "项目拜访", "指标路径": "七、行销行为诊断-项目拜访", "指标数据": {"实际值": "1.150", "单位": "%"}},
                ],
            },
        }

        md, stats = format_chapter7_data(response, period="202605")

        assert "5月拜访总频次 104次" in md
        assert "项目拜访频次 46次" in md
        assert stats["拜访总频次"] == 104.0
        assert stats["项目拜访频次"] == 46.0

    def test_api_rows_keep_total_and_project_visit_rates_separate(self):
        from ReportGenerator.chapter7_generator import format_chapter7_data

        response = {
            "code": 1,
            "data": {
                "月份": "202605",
                "章节名称": "七、行销行为诊断",
                "章节数据": [
                    {"指标名称": "本月拜访总频次", "指标路径": "七、行销行为诊断-拜访量-本月拜访总频次", "指标数据": {"实际值": "112.000", "单位": "次"}},
                    {"指标名称": "拜访达成率", "指标路径": "七、行销行为诊断-拜访量-拜访达成率", "指标数据": {"实际值": "1.867", "单位": "%"}},
                    {"指标名称": "本月项目拜访频次", "指标路径": "七、行销行为诊断-项目拜访-本月项目拜访频次", "指标数据": {"实际值": "111.000", "单位": "次"}},
                    {"指标名称": "拜访达成率", "指标路径": "七、行销行为诊断-项目拜访-拜访达成率", "指标数据": {"实际值": "2.775", "单位": "%"}},
                ],
            },
        }

        md, stats = format_chapter7_data(response, period="202605")

        assert "5月拜访总频次 112次，拜访达成率187%。项目拜访频次 111次，拜访达成率278%。" in md
        assert stats["拜访总达成率"] == 186.7
        assert stats["项目拜访达成率"] == 277.5

    def test_time_allocation_does_not_double_scale_percent_points(self):
        from ReportGenerator.chapter7_generator import format_chapter7_data

        response = {
            "code": 1,
            "data": {
                "月份": "202605",
                "章节名称": "七、行销行为诊断",
                "章节数据": [
                    {"指标名称": "客户拜访占比", "指标路径": "七、行销行为诊断-时间分配-各类拜访的次数占比-客户拜访占比", "指标数据": {"实际值": "0.009", "单位": "%"}},
                    {"指标名称": "项目拜访占比", "指标路径": "七、行销行为诊断-时间分配-各类拜访的次数占比-项目拜访占比", "指标数据": {"实际值": "0.991", "单位": "%"}},
                ],
            },
        }

        md, stats = format_chapter7_data(response, period="202605")

        assert "99%用于项目拜访，1%用于客户拜访。" in md
        assert stats["项目拜访占比"] == 99.1
        assert stats["客户拜访占比"] == 0.9


class TestChapter7DisplayRules:
    """第七章按客户参考图展示为简洁口径。"""

    def test_visit_line_omits_deduction_and_gap(self):
        from ReportGenerator.chapter7_generator import _build_visit_line, VisitMetric

        m = VisitMetric(actual=45, target=60, achievement_rate=75.0, deduction_score=-5)
        text = _build_visit_line(m, "拜访总频次", "5月")

        assert "45次" in text
        assert "75%" in text
        assert "扣绩效" not in text
        assert "还差" not in text

    def test_reference_style_visit_sentence(self):
        from ReportGenerator.chapter7_generator import _build_visit_line, VisitMetric

        m = VisitMetric(actual=104, target=60, achievement_rate=173.3, deduction_score=0)
        text = _build_visit_line(m, "拜访总频次", "5月")

        assert text == "5月拜访总频次 104次，拜访达成率173%"


class TestChapter7Helpers:
    def test_fmt_int(self):
        from ReportGenerator.chapter7_generator import _fmt_int
        assert _fmt_int(45) == "45"
        assert _fmt_int(None) == "—"
        assert _fmt_int(45.7) == "45"

    def test_fmt_percent(self):
        from ReportGenerator.chapter7_generator import _fmt_percent
        assert _fmt_percent(75.0) == "75%"
        assert _fmt_percent(None) == "—"

    def test_month_label(self):
        from ReportGenerator.chapter7_generator import month_label
        assert month_label("202605") == "5月"
        assert month_label("") == "报告月"


class TestChapter7GeneratorClass:
    def test_run_sync(self):
        from ReportGenerator.chapter7_generator import Chapter7Generator

        fixture = _load_fixture()
        gen = Chapter7Generator(data=fixture, period="202606")
        md = gen.run()
        assert "# 七、行销行为" in md

    @pytest.mark.asyncio
    async def test_run_async_without_ai(self):
        from ReportGenerator.chapter7_generator import Chapter7Generator

        fixture = _load_fixture()
        gen = Chapter7Generator(data=fixture, period="202606")
        md = await gen.run_async()
        assert "# 七、行销行为" in md
