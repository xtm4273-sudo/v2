"""统一 AI 文案包测试。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ReportAI.fact_pack import build_fact_pack
from ReportAI.model import ModelResponse
from ReportAI.settings import AIConfigurationError, AISettings
from ReportAI.writer import DIMENSIONS, ReportAIWriter


def valid_payload(number="12"):
    return {
        "chapter3": {"action": {"text": f"围绕销量{number}万制定补量动作。", "evidence_ids": ["C3-001"]}},
        "chapter4": {
            "structure_action": {"text": "优先核查产品结构变化。", "evidence_ids": ["C4-001"]},
            "price_action": {"text": "结合现有差异证据制定稳价动作。", "evidence_ids": ["C4-001"]},
        },
        "chapter5": {"action": {"text": "优先跟进逾期回款。", "evidence_ids": ["C5-001"]}},
        "chapter7": {"action": {"text": "补齐拜访频次缺口。", "evidence_ids": ["C7-001"]}},
        "chapter8": {
            "advantage": {"text": "本期销量表现稳健。", "evidence_ids": ["C8-001"]},
            "weakness": {"text": "应收风险仍需关注。", "evidence_ids": ["C8-001"]},
            "strategies": [
                {"dimension": dim, "text": f"{dim}维度持续落实改善动作。", "evidence_ids": ["C8-001"]}
                for dim in DIMENSIONS
            ],
        },
    }


class FakeModel:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    async def complete(self, _system, _user):
        import json
        payload = self.payloads[self.calls]
        self.calls += 1
        return ModelResponse(json.dumps(payload, ensure_ascii=False), request_id=f"r{self.calls}", latency_ms=10)


class ReportAIWriterTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fact_pack = build_fact_pack({
            "chapter3": {"销量": "12万"},
            "chapter4": {"数据状态": "待补充"},
            "chapter5": {"风险": "逾期"},
            "chapter7": {"风险": "拜访不足"},
            "chapter8": {"总结事实": "销量稳健，应收需关注"},
        })
        self.settings = AISettings(api_key="test-key")

    async def test_one_call_returns_all_sections(self):
        model = FakeModel([valid_payload()])
        bundle = await ReportAIWriter(model, self.settings).generate(self.fact_pack)
        self.assertEqual(model.calls, 1)
        self.assertEqual(bundle.chapter3_action.text, "围绕销量12万制定补量动作。")
        self.assertEqual([item.dimension for item in bundle.chapter8_strategies], list(DIMENSIONS))
        self.assertTrue(bundle.manifest["validated"])
        self.assertEqual(bundle.manifest["repair_calls"], 0)

    async def test_invalid_number_triggers_one_repair(self):
        invalid = valid_payload(number="99")
        model = FakeModel([invalid, valid_payload()])
        bundle = await ReportAIWriter(model, self.settings).generate(self.fact_pack)
        self.assertEqual(model.calls, 2)
        self.assertEqual(bundle.manifest["repair_calls"], 1)
        self.assertIn("12万", bundle.chapter3_action.text)


class AISettingsTest(unittest.TestCase):
    def test_loads_key_from_env_file(self):
        old = os.environ.pop("AI_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as directory:
                Path(directory, ".env").write_text("AI_API_KEY=local-secret\nAI_MODEL=test-model\n", encoding="utf-8")
                settings = AISettings.from_env(Path(directory))
                self.assertEqual(settings.api_key, "local-secret")
                self.assertEqual(settings.model, "test-model")
        finally:
            os.environ.pop("AI_API_KEY", None)
            os.environ.pop("AI_MODEL", None)
            if old is not None:
                os.environ["AI_API_KEY"] = old

