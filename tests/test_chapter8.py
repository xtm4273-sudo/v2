"""第八章单元测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def _load_fixture() -> dict:
    fixture_path = BASE_DIR / "Data" / "fixtures" / "chapter8_mock.json"
    with fixture_path.open("r", encoding="utf-8") as f:
        return json.load(f)


class TestChapter8DataNormalization:
    def test_normalize_from_full_response(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")

        assert data.metadata["月份"] == "202606"
        assert data.metadata["区域经理工号"] == "86002542"

        # 绩效
        assert data.performance.score == 108.0
        assert data.performance.rank_province == "5/26"
        assert data.performance.rank_bu == "36/1000"
        assert data.performance.sales == 580.0
        assert data.performance.profit == 35.0

        # 正向信号
        assert len(data.positive_signals) == 6
        assert data.positive_signals[0].dimension == "产品"
        assert data.positive_signals[0].metric_name == "真石漆收入"
        assert data.positive_signals[0].is_outstanding is True

        # 负向信号
        assert len(data.negative_signals) == 7
        assert data.negative_signals[0].dimension == "产品"
        assert data.negative_signals[0].severity == "medium"
        high_signals = [s for s in data.negative_signals if s.severity == "high"]
        assert len(high_signals) == 4

        # 维度汇总
        ds = data.dimension_summary
        assert len(ds.product.top_growing) == 3
        assert ds.product.top_growing[0]["product_name"] == "真石漆"
        assert len(ds.product.top_declining) == 3
        assert ds.project.project_count == 32
        assert ds.project.single_project_revenue == 18.1
        assert ds.channel.channel_count == 8
        assert ds.customer.customer_count == 18
        assert ds.customer.avg_revenue_per_customer == 32.2
        assert ds.receivable.overdue_amount == 28.0
        assert ds.receivable.impairment_amount == 5.2
        assert ds.receivable.finance_cost == 3200.0
        assert ds.sampling.sample_expense == 4500.0
        assert ds.sampling.yoy_direction == "up"

    def test_normalize_empty_data(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data

        data = normalize_chapter8_data({"code": 1, "data": {"月份": "202606"}})
        assert data.performance.score is None
        assert data.positive_signals == []
        assert data.negative_signals == []
        assert data.dimension_summary.product.top_growing == []

    def test_normalize_data_object(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture["data"], period="202606")

        assert data.metadata["月份"] == "202606"
        assert data.performance.score == 108.0


class TestChapter8Markdown:
    def test_build_markdown_rule_based(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data, build_chapter8_markdown

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        md = build_chapter8_markdown(data)

        assert "## 八、总结" in md
        assert "优势：" in md
        assert "短板：" in md
        assert "核心策略：" in md

        # 6 个维度策略必须出现
        assert "产品：" in md
        assert "项目：" in md
        assert "渠道：" in md
        assert "客户：" in md
        assert "应收：" in md
        assert "打样：" in md

        # 最后一个策略应以句号结尾
        assert md.rstrip().endswith("。")

    def test_build_markdown_empty_data(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data, build_chapter8_markdown

        data = normalize_chapter8_data({"月份": "202606"})
        md = build_chapter8_markdown(data)

        assert "## 八、总结" in md
        assert "数据不足" in md

    def test_format_chapter8_data(self):
        from ReportGenerator.chapter8_generator import format_chapter8_data

        fixture = _load_fixture()
        md, stats = format_chapter8_data(fixture, period="202606")

        assert "## 八、总结" in md
        assert stats["正向信号数"] == 6
        assert stats["负向信号数"] == 7
        assert stats["绩效得分"] == 108.0


class TestChapter8AdvantageRule:
    """规则版优势生成测试。"""

    def test_advantage_with_signals(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data, _build_rule_advantage

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        text = _build_rule_advantage(data)

        assert "108分" in text
        assert "真石漆" in text
        assert "多彩漆" in text
        assert text.endswith("。")

    def test_advantage_empty_signals(self):
        from ReportGenerator.chapter8_generator import Chapter8Data, _build_rule_advantage

        data = Chapter8Data(metadata={"月份": "202606"})
        text = _build_rule_advantage(data)
        assert "暂无特别突出的正向指标" in text

    def test_advantage_outstanding_priority(self):
        from ReportGenerator.chapter8_generator import Chapter8Data, Chapter8Signal, PerformanceSummary, _build_rule_advantage

        data = Chapter8Data(
            metadata={"月份": "202606"},
            performance=PerformanceSummary(score=105),
            positive_signals=[
                Chapter8Signal(dimension="产品", metric_name="普通产品", change_display="↑5%", is_outstanding=False),
                Chapter8Signal(dimension="产品", metric_name="明星产品", change_display="↑60%", is_outstanding=True),
            ],
        )
        text = _build_rule_advantage(data)

        # is_outstanding 的应该排在前面
        assert text.index("明星产品") < text.index("普通产品")


class TestChapter8WeaknessRule:
    """规则版短板生成测试。"""

    def test_weakness_with_signals(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data, _build_rule_weakness

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        text = _build_rule_weakness(data)

        assert "毛利率" in text
        assert text.endswith("。")

    def test_weakness_empty_signals(self):
        from ReportGenerator.chapter8_generator import Chapter8Data, _build_rule_weakness

        data = Chapter8Data(metadata={"月份": "202606"})
        text = _build_rule_weakness(data)
        assert "数据不足" in text

    def test_weakness_high_severity_first(self):
        from ReportGenerator.chapter8_generator import Chapter8Data, Chapter8Signal, _build_rule_weakness

        data = Chapter8Data(
            metadata={"月份": "202606"},
            negative_signals=[
                Chapter8Signal(dimension="产品", metric_name="低风险", change_display="↓2%", severity="medium"),
                Chapter8Signal(dimension="应收", metric_name="高风险", change_display="↑50%", severity="high"),
            ],
        )
        text = _build_rule_weakness(data)

        # high severity 应该排在 medium 前面
        assert text.index("高风险") < text.index("低风险")


class TestChapter8StrategiesRule:
    """规则版六维度策略生成测试。"""

    def test_all_six_dimensions(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data, _build_rule_strategies

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        strategies = _build_rule_strategies(data)

        assert len(strategies) == 6
        assert any("产品：" in s for s in strategies)
        assert any("项目：" in s for s in strategies)
        assert any("渠道：" in s for s in strategies)
        assert any("客户：" in s for s in strategies)
        assert any("应收：" in s for s in strategies)
        assert any("打样：" in s for s in strategies)

    def test_product_strategy_growing_and_declining(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data
        from ReportGenerator.chapter8_generator import _build_dim_strategy

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        text = _build_dim_strategy("产品", data.dimension_summary)

        assert "主推" in text
        assert "真石漆" in text
        assert "下滑" in text

    def test_product_strategy_growing_only(self):
        from ReportGenerator.chapter8_generator import ProductDimension, DimensionSummary
        from ReportGenerator.chapter8_generator import _build_dim_strategy

        ds = DimensionSummary(
            product=ProductDimension(
                top_growing=[{"product_name": "真石漆", "revenue": 58, "yoy_change_pct": 58.0}],
                top_declining=[],
            )
        )
        text = _build_dim_strategy("产品", ds)
        assert "主推真石漆" in text
        assert "下滑" not in text

    def test_product_strategy_empty(self):
        from ReportGenerator.chapter8_generator import DimensionSummary
        from ReportGenerator.chapter8_generator import _build_dim_strategy

        ds = DimensionSummary()
        text = _build_dim_strategy("产品", ds)
        assert "产品：" in text
        # 应有通用回退文案
        assert len(text) > 4

    def test_receivable_strategy_with_data(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data
        from ReportGenerator.chapter8_generator import _build_dim_strategy

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        text = _build_dim_strategy("应收", data.dimension_summary)

        assert "28" in text or "逾期" in text
        assert "5.2" in text or "减值" in text

    def test_sampling_strategy_up(self):
        from ReportGenerator.chapter8_generator import SamplingDimension, DimensionSummary
        from ReportGenerator.chapter8_generator import _build_dim_strategy

        ds = DimensionSummary(
            sampling=SamplingDimension(sample_expense=4500, yoy_direction="up")
        )
        text = _build_dim_strategy("打样", ds)
        assert "4500元" in text
        assert "增加" in text or "转化" in text

    def test_sampling_strategy_down(self):
        from ReportGenerator.chapter8_generator import SamplingDimension, DimensionSummary
        from ReportGenerator.chapter8_generator import _build_dim_strategy

        ds = DimensionSummary(
            sampling=SamplingDimension(sample_expense=3000, yoy_direction="down")
        )
        text = _build_dim_strategy("打样", ds)
        assert "下降" in text or "保持" in text

    def test_dimension_order(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data, _build_rule_strategies, DIMENSION_ORDER

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        strategies = _build_rule_strategies(data)

        for i, dim in enumerate(DIMENSION_ORDER):
            assert dim + "：" in strategies[i]


class TestChapter8AIWriter:
    """AI Writer 响应解析测试。"""

    def test_parse_valid_json(self):
        from ReportGenerator.chapter8_ai_writer import _parse_summary_response

        text = '''```json
{
  "advantage": "高增长、绩效优秀。",
  "weakness": "毛利率侵蚀。",
  "strategies": ["产品：主推真石漆", "项目：推进落地"]
}
```'''
        result = _parse_summary_response(text)
        assert result["advantage"] == "高增长、绩效优秀。"
        assert result["weakness"] == "毛利率侵蚀。"
        assert len(result["strategies"]) == 2

    def test_parse_plain_json(self):
        from ReportGenerator.chapter8_ai_writer import _parse_summary_response

        text = '{"advantage": "增长良好。", "weakness": "应收积压。", "strategies": ["产品：优化结构"]}'
        result = _parse_summary_response(text)
        assert result["advantage"] == "增长良好。"
        assert result["weakness"] == "应收积压。"
        assert result["strategies"] == ["产品：优化结构"]

    def test_parse_empty(self):
        from ReportGenerator.chapter8_ai_writer import _parse_summary_response

        assert _parse_summary_response("") == {}
        assert _parse_summary_response("not json at all") == {}

    def test_parse_semicolon_separated_strategies(self):
        from ReportGenerator.chapter8_ai_writer import _parse_summary_response

        text = '{"advantage": "稳。", "weakness": "跌。", "strategies": "产品：推；项目：落地"}'
        result = _parse_summary_response(text)
        assert len(result["strategies"]) == 2
        assert result["strategies"][0] == "产品：推"

    def test_validate_result_missing_fields(self):
        from ReportGenerator.chapter8_ai_writer import _validate_result

        result = _validate_result({"advantage": "仅优势"})
        assert result["advantage"] == "仅优势"
        assert "weakness" not in result
        assert "strategies" not in result

    def test_writer_generate_no_model(self):
        from ReportGenerator.chapter8_ai_writer import Chapter8SummaryWriter
        import asyncio

        writer = Chapter8SummaryWriter(model=None)
        result = asyncio.run(
            writer.generate(
                action_context={},
                fallback_advantage="规则优势",
                fallback_weakness="规则短板",
                fallback_strategies=["产品：规则策略"],
            )
        )
        assert result["advantage"] == "规则优势"
        assert result["weakness"] == "规则短板"
        assert result["strategies"] == ["产品：规则策略"]

    def test_writer_rejects_numbers_not_present_in_facts(self):
        from ReportGenerator.chapter8_ai_writer import Chapter8SummaryWriter
        import asyncio

        async def model(_messages):
            return '''{"advantage":"项目完成26个。","weakness":"目标100个。","strategies":["项目：推进剩余74个项目"]}'''

        writer = Chapter8SummaryWriter(model=model)
        result = asyncio.run(
            writer.generate(
                action_context={"facts": [{"actual": 26, "target": 100}]},
                fallback_advantage="规则优势",
                fallback_weakness="规则短板",
                fallback_strategies=["项目：规则策略"],
            )
        )
        assert result == {
            "advantage": "规则优势",
            "weakness": "规则短板",
            "strategies": ["项目：规则策略"],
        }


class TestChapter8DataDict:
    def test_to_dict(self):
        from ReportGenerator.chapter8_generator import normalize_chapter8_data

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        d = data.to_dict()

        assert d["performance"]["score"] == 108.0
        assert len(d["positive_signals"]) == 6
        assert len(d["negative_signals"]) == 7
        assert len(d["dimension_summary"]["产品"]["top_growing"]) == 3
        assert d["dimension_summary"]["应收"]["overdue_amount"] == 28.0


class TestChapter8GeneratorClass:
    def test_run_sync(self):
        from ReportGenerator.chapter8_generator import Chapter8Generator

        fixture = _load_fixture()
        gen = Chapter8Generator(data=fixture, period="202606")
        md = gen.run()
        assert "## 八、总结" in md
        assert "核心策略：" in md

    @pytest.mark.asyncio
    async def test_run_async_without_ai(self):
        from ReportGenerator.chapter8_generator import Chapter8Generator

        fixture = _load_fixture()
        gen = Chapter8Generator(data=fixture, period="202606")
        md = await gen.run_async()
        assert "## 八、总结" in md
        assert "核心策略：" in md


class TestChapter8DisplayRules:
    """批注[32]六维度覆盖测试。"""

    def test_markdown_output_matches_v5_template_structure(self):
        """验证输出结构与 V5 模板对齐。"""
        from ReportGenerator.chapter8_generator import normalize_chapter8_data, build_chapter8_markdown

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        md = build_chapter8_markdown(data)

        lines = md.strip().split("\n")
        # 第1行：## 八、总结
        assert lines[0] == "## 八、总结"
        # 第3行：优势：
        assert lines[2].startswith("优势：")
        # 第5行：短板：
        assert lines[4].startswith("短板：")
        # 第7行：核心策略：
        assert lines[6] == "核心策略："
        # 后续6行：六维度策略
        strategy_lines = [l for l in lines[7:] if l.strip() and not l.strip().startswith("<!--")]
        assert len(strategy_lines) == 6

    def test_no_dangling_punctuation(self):
        """验证没有多余标点。"""
        from ReportGenerator.chapter8_generator import normalize_chapter8_data, build_chapter8_markdown

        fixture = _load_fixture()
        data = normalize_chapter8_data(fixture, period="202606")
        md = build_chapter8_markdown(data)

        assert "；。" not in md
        assert "。。" not in md
