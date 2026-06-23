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
        assert data.time_allocation.project_ratio == 0.56
        assert data.time_allocation.customer_ratio == 0.44

    def test_normalize_empty_data(self):
        from ReportGenerator.chapter7_generator import normalize_chapter7_data

        data = normalize_chapter7_data({"code": 1, "data": {"月份": "202606"}})
        assert data.total_visit.actual is None
        assert data.time_allocation.project_ratio is None


class TestChapter7Markdown:
    def test_build_markdown(self):
        from ReportGenerator.chapter7_generator import normalize_chapter7_data, build_chapter7_markdown

        fixture = _load_fixture()
        data = normalize_chapter7_data(fixture, period="202606")
        md = build_chapter7_markdown(data)

        assert "## 七、行销行为" in md
        assert "### 拜访量" in md
        assert "拜访总频次" in md
        assert "45次" in md
        assert "75.0%" in md
        assert "扣绩效5分" in md
        assert "还差15次" in md
        assert "项目拜访频次" in md
        assert "25次" in md
        assert "83.3%" in md
        assert "### 时间分配" in md
        assert "56.0%" in md
        assert "44.0%" in md
        assert "### 行动指南：" in md

    def test_build_markdown_empty_data(self):
        from ReportGenerator.chapter7_generator import normalize_chapter7_data, build_chapter7_markdown

        data = normalize_chapter7_data({"月份": "202606"})
        md = build_chapter7_markdown(data)
        assert "## 七、行销行为" in md
        assert "数据暂未提供" in md

    def test_format_chapter7_data(self):
        from ReportGenerator.chapter7_generator import format_chapter7_data

        fixture = _load_fixture()
        md, stats = format_chapter7_data(fixture, period="202606")

        assert "## 七、行销行为" in md
        assert stats["拜访总频次"] == 45.0
        assert stats["拜访总达成率"] == 75.0


class TestChapter7DisplayRules:
    """批注[31]条件展示规则测试。"""

    def test_hide_deduction_when_over_100(self):
        from ReportGenerator.chapter7_generator import _build_visit_line, VisitMetric

        m = VisitMetric(actual=65, target=60, achievement_rate=108.3, deduction_score=0)
        text = _build_visit_line(m, "拜访总频次", "5月")

        assert "65次" in text
        assert "108.3%" in text
        assert "扣绩效" not in text
        assert "还差" not in text

    def test_show_deduction_when_under_100(self):
        from ReportGenerator.chapter7_generator import _build_visit_line, VisitMetric

        m = VisitMetric(actual=45, target=60, achievement_rate=75.0, deduction_score=-5)
        text = _build_visit_line(m, "拜访总频次", "5月")

        assert "扣绩效5分" in text
        assert "还差15次" in text

    def test_no_gap_when_exact_target(self):
        from ReportGenerator.chapter7_generator import _build_visit_line, VisitMetric

        m = VisitMetric(actual=60, target=60, achievement_rate=100.0, deduction_score=0)
        text = _build_visit_line(m, "拜访总频次", "5月")

        assert "扣绩效" not in text
        assert "还差" not in text


class TestChapter7Helpers:
    def test_fmt_int(self):
        from ReportGenerator.chapter7_generator import _fmt_int
        assert _fmt_int(45) == "45"
        assert _fmt_int(None) == "—"
        assert _fmt_int(45.7) == "45"

    def test_fmt_percent(self):
        from ReportGenerator.chapter7_generator import _fmt_percent
        assert _fmt_percent(75.0) == "75.0%"
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
        assert "## 七、行销行为" in md

    @pytest.mark.asyncio
    async def test_run_async_without_ai(self):
        from ReportGenerator.chapter7_generator import Chapter7Generator

        fixture = _load_fixture()
        gen = Chapter7Generator(data=fixture, period="202606")
        md = await gen.run_async()
        assert "## 七、行销行为" in md
