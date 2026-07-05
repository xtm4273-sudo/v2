"""一次调用生成完整报告所需的全部 AI 文案。"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from .fact_pack import SECTION_PREFIX, evidence_ids
from .model import ModelResponse, OpenAICompatibleModel
from .settings import AISettings


DIMENSIONS = ("产品", "项目", "渠道", "客户", "应收", "打样", "风控")


class AIWritingError(RuntimeError):
    """模型调用或输出验证失败。"""


@dataclass(frozen=True)
class NarrativeItem:
    text: str
    evidence_ids: List[str]

    @classmethod
    def from_dict(cls, data: Any, path: str) -> "NarrativeItem":
        if not isinstance(data, dict):
            raise AIWritingError(f"{path} 必须是对象")
        text = str(data.get("text") or "").strip()
        ids = data.get("evidence_ids")
        if not text:
            raise AIWritingError(f"{path}.text 为空")
        if not isinstance(ids, list) or not ids:
            raise AIWritingError(f"{path}.evidence_ids 为空")
        return cls(text=_clean_text(text), evidence_ids=[str(item) for item in ids])

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "evidence_ids": self.evidence_ids}


@dataclass(frozen=True)
class StrategyItem:
    dimension: str
    text: str
    evidence_ids: List[str]

    @classmethod
    def from_dict(cls, data: Any, path: str) -> "StrategyItem":
        if not isinstance(data, dict):
            raise AIWritingError(f"{path} 必须是对象")
        dimension = str(data.get("dimension") or "").strip()
        item = NarrativeItem.from_dict(data, path)
        return cls(dimension=dimension, text=item.text, evidence_ids=item.evidence_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {"dimension": self.dimension, "text": self.text, "evidence_ids": self.evidence_ids}


@dataclass(frozen=True)
class NarrativeBundle:
    chapter3_action: NarrativeItem
    chapter4_structure_action: NarrativeItem
    chapter4_price_action: NarrativeItem
    chapter5_action: NarrativeItem
    chapter7_action: NarrativeItem
    chapter8_advantage: NarrativeItem
    chapter8_weakness: NarrativeItem
    chapter8_strategies: List[StrategyItem]
    manifest: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter3": {"action": self.chapter3_action.to_dict()},
            "chapter4": {
                "structure_action": self.chapter4_structure_action.to_dict(),
                "price_action": self.chapter4_price_action.to_dict(),
            },
            "chapter5": {"action": self.chapter5_action.to_dict()},
            "chapter7": {"action": self.chapter7_action.to_dict()},
            "chapter8": {
                "advantage": self.chapter8_advantage.to_dict(),
                "weakness": self.chapter8_weakness.to_dict(),
                "strategies": [item.to_dict() for item in self.chapter8_strategies],
            },
        }


SYSTEM_PROMPT = """你是三棵树城市焕新事业部月度经营报告的文案撰写助手。

一次性生成第3、4、5、7章行动指南和第8章综合总结。只能使用输入事实，禁止重新计算、猜测原因或补造数字、客户、产品、项目。每段必须给出实际使用的 evidence_ids。缺少数据时应明确建议补充或核查，不得虚构。

要求：
- 第3章只用 chapter3 事实；第4章只用 chapter4；第5章只用 chapter5；第7章只用 chapter7；第8章只用 chapter8。
- 第4章分别输出产品结构建议和价格建议。
- 第4章若事实明确标记方向、当前占比或排名缺失，禁止根据差异值正负推断高增长/下降产品，禁止点名产品，只能给出补数、核查和后续分析建议。
- 第8章优势只用正向事实，短板只用负向事实，策略严格按产品、项目、渠道、客户、应收、打样、风控七个维度。
- 第8章某维度没有具体事实时，只能提出补充数据或通用管理动作，不得从其它章节挪用实体。
- 每项1至2句，专业、简洁、可执行；不输出标题，不提模型、程序、接口或证据编号。
- 输出严格 JSON，不要 Markdown 代码围栏。
"""


class ReportAIWriter:
    """统一的报告 AI 文案深模块。"""

    def __init__(self, model: Any, settings: AISettings):
        self.model = model
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Optional[AISettings] = None) -> "ReportAIWriter":
        resolved = settings or AISettings.from_env()
        return cls(OpenAICompatibleModel(resolved), resolved)

    async def generate(self, fact_pack: Dict[str, List[Dict[str, Any]]]) -> NarrativeBundle:
        prompt = _build_user_prompt(fact_pack)
        primary = await self.model.complete(SYSTEM_PROMPT, prompt)
        data = _parse_json(primary.text)
        try:
            bundle = _bundle_from_data(data, fact_pack)
            repair_calls = 0
            response = primary
        except AIWritingError as first_error:
            repair = await self.model.complete(
                SYSTEM_PROMPT,
                _build_repair_prompt(fact_pack, data, str(first_error)),
            )
            data = _parse_json(repair.text)
            try:
                bundle = _bundle_from_data(data, fact_pack)
            except AIWritingError:
                data = _sanitize_unusable_evidence_ids(data, fact_pack)
                data = _sanitize_unsupported_numbers(data, fact_pack)
                data = _sanitize_false_missing_claims(data, fact_pack)
                bundle = _bundle_from_data(data, fact_pack)
            repair_calls = 1
            response = repair
        manifest = {
            "source": "AI",
            "provider": "openai-compatible",
            "model": self.settings.model,
            "prompt_version": self.settings.prompt_version,
            "validated": True,
            "primary_calls": 1,
            "repair_calls": repair_calls,
            "request_id": response.request_id,
            "latency_ms": primary.latency_ms + (response.latency_ms if repair_calls else 0),
            "usage": response.usage,
            "fact_pack_hash": hashlib.sha256(
                json.dumps(fact_pack, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }
        return NarrativeBundle(**{**bundle.__dict__, "manifest": manifest})


def _build_user_prompt(fact_pack: Dict[str, Any]) -> str:
    schema = {
        "chapter3": {"action": {"text": "", "evidence_ids": ["C3-001"]}},
        "chapter4": {
            "structure_action": {"text": "", "evidence_ids": ["C4-001"]},
            "price_action": {"text": "", "evidence_ids": ["C4-002"]},
        },
        "chapter5": {"action": {"text": "", "evidence_ids": ["C5-001"]}},
        "chapter7": {"action": {"text": "", "evidence_ids": ["C7-001"]}},
        "chapter8": {
            "advantage": {"text": "", "evidence_ids": ["C8-001"]},
            "weakness": {"text": "", "evidence_ids": ["C8-002"]},
            "strategies": [
                {"dimension": name, "text": "", "evidence_ids": ["C8-001"]}
                for name in DIMENSIONS
            ],
        },
    }
    return (
        "请按以下结构生成完整文案包。\n输出结构：\n"
        + json.dumps(schema, ensure_ascii=False, indent=2)
        + "\n事实包：\n"
        + json.dumps(fact_pack, ensure_ascii=False, separators=(",", ":"))
    )


def _build_repair_prompt(fact_pack: Dict[str, Any], invalid: Dict[str, Any], error_message: str) -> str:
    return (
        "上次输出未通过验证。请根据错误修正后重新输出完整 JSON；不得改变已正确字段的事实含义。\n"
        f"验证错误：{error_message}\n"
        f"上次输出：{json.dumps(invalid, ensure_ascii=False)}\n"
        f"事实包：{json.dumps(fact_pack, ensure_ascii=False, separators=(',', ':'))}"
    )


def _parse_json(text: str) -> Dict[str, Any]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIWritingError(f"模型未返回合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIWritingError("模型输出根节点必须是对象")
    return data


def _bundle_from_data(data: Dict[str, Any], fact_pack: Dict[str, Any]) -> NarrativeBundle:
    try:
        c3 = NarrativeItem.from_dict(data["chapter3"]["action"], "chapter3.action")
        c4s = NarrativeItem.from_dict(data["chapter4"]["structure_action"], "chapter4.structure_action")
        c4p = NarrativeItem.from_dict(data["chapter4"]["price_action"], "chapter4.price_action")
        c5 = NarrativeItem.from_dict(data["chapter5"]["action"], "chapter5.action")
        c7 = NarrativeItem.from_dict(data["chapter7"]["action"], "chapter7.action")
        c8a = NarrativeItem.from_dict(data["chapter8"]["advantage"], "chapter8.advantage")
        c8w = NarrativeItem.from_dict(data["chapter8"]["weakness"], "chapter8.weakness")
        raw_strategies = data["chapter8"]["strategies"]
    except (KeyError, TypeError) as exc:
        raise AIWritingError(f"模型输出缺少字段: {exc}") from exc
    if not isinstance(raw_strategies, list):
        raise AIWritingError("chapter8.strategies 必须是数组")
    strategies = [StrategyItem.from_dict(item, f"chapter8.strategies[{i}]") for i, item in enumerate(raw_strategies)]
    if tuple(item.dimension for item in strategies) != DIMENSIONS:
        raise AIWritingError("chapter8.strategies 必须严格包含产品、项目、渠道、客户、应收、打样、风控")

    c3 = _bind_numeric_evidence(c3, "chapter3", fact_pack)
    c4s = _bind_numeric_evidence(c4s, "chapter4", fact_pack)
    c4p = _bind_numeric_evidence(c4p, "chapter4", fact_pack)
    c5 = _bind_numeric_evidence(c5, "chapter5", fact_pack)
    c7 = _bind_numeric_evidence(c7, "chapter7", fact_pack)
    c8a = _bind_numeric_evidence(c8a, "chapter8", fact_pack)
    c8w = _bind_numeric_evidence(c8w, "chapter8", fact_pack)
    strategies = [_bind_strategy_numeric_evidence(item, fact_pack) for item in strategies]

    section_items = {
        "chapter3": [c3],
        "chapter4": [c4s, c4p],
        "chapter5": [c5],
        "chapter7": [c7],
        "chapter8": [c8a, c8w, *strategies],
    }
    _validate_evidence(section_items, fact_pack)
    _validate_numbers(section_items, fact_pack)
    _validate_missing_data_semantics(c4s, c4p, c8a, c8w, strategies, fact_pack)
    return NarrativeBundle(c3, c4s, c4p, c5, c7, c8a, c8w, strategies, manifest={})


def _bind_numeric_evidence(
    item: NarrativeItem,
    section: str,
    fact_pack: Dict[str, Any],
) -> NarrativeItem:
    ids = list(dict.fromkeys(item.evidence_ids))
    facts = [fact for fact in fact_pack.get(section, []) if isinstance(fact, dict)]
    for value in _iter_checkable_numbers(item.text):
        normalized = _normalize_number(value)
        matches = []
        for fact in facts:
            source_numbers = {
                _normalize_number(number)
                for number in re.findall(
                    r"(?<![A-Za-z])\d+(?:\.\d+)?",
                    json.dumps(fact.get("value"), ensure_ascii=False),
                )
            }
            if _number_supported_by_any(normalized, source_numbers):
                matches.append(str(fact.get("id")))
        if not matches:
            raise AIWritingError(f"{section} 文案包含事实包之外的数字 {value}")
        if not any(match in ids for match in matches):
            ids.append(matches[0])
    return NarrativeItem(text=item.text, evidence_ids=ids)


def _sanitize_unsupported_numbers(data: Dict[str, Any], fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = deepcopy(data)
    for section in ("chapter3", "chapter4", "chapter5", "chapter7", "chapter8"):
        for container in _iter_text_containers(sanitized.get(section)):
            text = str(container.get("text") or "")
            container["text"] = _replace_unsupported_numbers(text, section, fact_pack)
    return sanitized


def _sanitize_unusable_evidence_ids(data: Dict[str, Any], fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = deepcopy(data)
    all_valid_ids = evidence_ids(fact_pack)
    for section in ("chapter3", "chapter4", "chapter5", "chapter7", "chapter8"):
        prefix = SECTION_PREFIX[section] + "-"
        section_ids = [
            str(fact.get("id"))
            for fact in fact_pack.get(section, [])
            if isinstance(fact, dict) and str(fact.get("id") or "").startswith(prefix)
        ]
        fallback = section_ids[:1]
        for container in _iter_text_containers(sanitized.get(section)):
            ids = container.get("evidence_ids")
            if not isinstance(ids, list):
                ids = []
            cleaned = [
                str(evidence_id)
                for evidence_id in ids
                if str(evidence_id) in all_valid_ids and str(evidence_id).startswith(prefix)
            ]
            container["evidence_ids"] = list(dict.fromkeys(cleaned)) or fallback
    return sanitized


def _sanitize_false_missing_claims(data: Dict[str, Any], fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = deepcopy(data)
    facts_by_id = {
        str(fact.get("id")): fact
        for fact in fact_pack.get("chapter8", [])
        if isinstance(fact, dict)
    }
    for container in _iter_text_containers(sanitized.get("chapter8")):
        if not _claims_missing_data(str(container.get("text") or "")):
            continue
        cited = [
            facts_by_id[str(evidence_id)]
            for evidence_id in container.get("evidence_ids", [])
            if str(evidence_id) in facts_by_id
        ]
        if _has_concrete_cited_fact_for_text(str(container.get("text") or ""), cited):
            container["text"] = _replace_false_missing_claim(str(container.get("text") or ""))
    return sanitized


def _iter_text_containers(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        if "text" in value:
            yield value
        for child in value.values():
            yield from _iter_text_containers(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_text_containers(child)


def _replace_unsupported_numbers(text: str, section: str, fact_pack: Dict[str, Any]) -> str:
    facts = [fact for fact in fact_pack.get(section, []) if isinstance(fact, dict)]
    source_numbers = set()
    for fact in facts:
        source_numbers.update(
            _normalize_number(number)
            for number in re.findall(
                r"(?<![A-Za-z])\d+(?:\.\d+)?",
                json.dumps(fact.get("value"), ensure_ascii=False),
            )
        )

    def replace(match: re.Match[str]) -> str:
        number = match.group("number")
        if _is_period_label_number(text, match):
            return match.group(0)
        if _number_supported_by_any(_normalize_number(number), source_numbers):
            return match.group(0)
        return "相关数值"

    return re.sub(
        r"(?<![A-Za-z])(?P<number>\d+(?:\.\d+)?)(?:%|万元|万|元|个|家|人|项|次|分|天|KG|pp)?",
        replace,
        text,
    )


def _bind_strategy_numeric_evidence(item: StrategyItem, fact_pack: Dict[str, Any]) -> StrategyItem:
    bound = _bind_numeric_evidence(
        NarrativeItem(text=item.text, evidence_ids=item.evidence_ids),
        "chapter8",
        fact_pack,
    )
    ids = list(bound.evidence_ids)
    dimension_marker = f"dimension_summary.{item.dimension}"
    for fact in fact_pack.get("chapter8", []):
        if not isinstance(fact, dict) or dimension_marker not in str(fact.get("path") or ""):
            continue
        evidence_id = str(fact.get("id") or "")
        if evidence_id and evidence_id not in ids:
            ids.append(evidence_id)
        if len(ids) >= 4:
            break
    return StrategyItem(dimension=item.dimension, text=bound.text, evidence_ids=ids)


def _validate_evidence(section_items: Dict[str, Iterable[Any]], fact_pack: Dict[str, Any]) -> None:
    valid_ids = evidence_ids(fact_pack)
    for section, items in section_items.items():
        prefix = SECTION_PREFIX[section] + "-"
        for item in items:
            for evidence_id in item.evidence_ids:
                if evidence_id not in valid_ids:
                    raise AIWritingError(f"{section} 引用了不存在的证据 {evidence_id}")
                if not evidence_id.startswith(prefix):
                    raise AIWritingError(f"{section} 跨章节引用了证据 {evidence_id}")


def _validate_numbers(section_items: Dict[str, Iterable[Any]], fact_pack: Dict[str, Any]) -> None:
    for section, items in section_items.items():
        facts_by_id = {
            str(fact.get("id")): fact
            for fact in fact_pack.get(section, [])
            if isinstance(fact, dict)
        }
        for item in items:
            cited_source = json.dumps(
                [facts_by_id[evidence_id] for evidence_id in item.evidence_ids if evidence_id in facts_by_id],
                ensure_ascii=False,
            )
            allowed = {
                _normalize_number(value)
                for value in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", cited_source)
            }
            for value in _iter_checkable_numbers(item.text):
                if not _number_supported_by_any(_normalize_number(value), allowed):
                    raise AIWritingError(f"{section} 文案数字 {value} 未被所引用证据支持")


def _validate_missing_data_semantics(
    chapter4_structure: NarrativeItem,
    chapter4_price: NarrativeItem,
    chapter8_advantage: NarrativeItem,
    chapter8_weakness: NarrativeItem,
    strategies: List[StrategyItem],
    fact_pack: Dict[str, Any],
) -> None:
    chapter4_source = json.dumps(fact_pack.get("chapter4", []), ensure_ascii=False)
    if any(term in chapter4_source for term in ("明确方向字段", "收入占比排名", "当前产品收入占比")):
        combined = chapter4_structure.text + chapter4_price.text
        forbidden = ("高增长产品", "下降产品", "上升产品", "排名前三产品")
        if any(term in combined for term in forbidden):
            raise AIWritingError("chapter4 缺少方向/排名字段，禁止推断或点名增长、下降产品")

    product_strategy = next((item for item in strategies if item.dimension == "产品"), None)
    chapter8_source = json.dumps(fact_pack.get("chapter8", []), ensure_ascii=False)
    no_product_facts = (
        "top_growing" in chapter8_source
        and "top_declining" in chapter8_source
        and '"value": "无"' in chapter8_source
    )
    if no_product_facts and product_strategy is not None:
        if not any(term in product_strategy.text for term in ("补充", "核查", "数据")):
            raise AIWritingError("chapter8 产品维度缺少具体事实，只能提出补数或核查建议")

    chapter8_facts_by_id = {
        str(fact.get("id")): fact
        for fact in fact_pack.get("chapter8", [])
        if isinstance(fact, dict)
    }
    for item in (chapter8_advantage, chapter8_weakness, *strategies):
        if not _claims_missing_data(item.text):
            continue
        cited = [
            chapter8_facts_by_id[evidence_id]
            for evidence_id in item.evidence_ids
            if evidence_id in chapter8_facts_by_id
        ]
        if _has_concrete_cited_fact_for_text(item.text, cited):
            raise AIWritingError("chapter8 已引用具体事实，禁止写成数据待补充")


def _claims_missing_data(text: str) -> bool:
    return any(term in text for term in ("数据待补充", "待补充", "缺少数据", "缺少可比"))


def _has_concrete_cited_fact_for_text(text: str, cited_facts: Iterable[Dict[str, Any]]) -> bool:
    terms = _business_terms(text)
    for fact in cited_facts:
        value = fact.get("value")
        if not _is_concrete_fact_value(value):
            continue
        path = str(fact.get("path") or "")
        source = path + json.dumps(value, ensure_ascii=False)
        if not terms or any(term in source for term in terms):
            return True
    return False


def _business_terms(text: str) -> List[str]:
    candidates = ("逾期", "应收", "打样", "样板", "样漆", "同期", "费用", "客户", "产品", "项目", "渠道", "风控")
    return [term for term in candidates if term in text]


def _is_concrete_fact_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text or text in {"待补充", "数据待补充", "无", "unknown"}:
        return False
    return True


def _replace_false_missing_claim(text: str) -> str:
    replacements = {
        "逾期应收数据待补充": "逾期应收按现有数据纳入跟踪",
        "应收数据待补充": "应收按现有数据纳入跟踪",
        "同期数据待补充": "同期数据按现有口径核查",
        "数据待补充": "按现有数据持续跟踪",
        "待补充": "按现有数据持续跟踪",
    }
    output = text
    for before, after in replacements.items():
        output = output.replace(before, after)
    return output


def _normalize_number(value: str) -> str:
    try:
        return str(float(value)).rstrip("0").rstrip(".")
    except ValueError:
        return value


def _number_supported_by_any(value: str, allowed: Iterable[str]) -> bool:
    if value in allowed:
        return True
    try:
        target = float(value)
    except ValueError:
        return False
    for candidate in allowed:
        try:
            source = float(candidate)
        except ValueError:
            continue
        if round(target) == round(source):
            return True
    return False


def _iter_checkable_numbers(text: str) -> List[str]:
    """Return business numbers, excluding period labels and structural ordinals."""
    values: List[str] = []
    for match in re.finditer(r"(?<![A-Za-z])\d+(?:\.\d+)?", text):
        if _is_period_label_number(text, match):
            continue
        values.append(match.group(0))
    return values


def _is_period_label_number(text: str, match: re.Match[str]) -> bool:
    start, end = match.span()
    prev_char = text[start - 1] if start > 0 else ""
    next_char = text[end] if end < len(text) else ""
    if prev_char == "第" and next_char in {"章", "节", "项", "条"}:
        return True
    if next_char in {"年", "月"} or prev_char in {"年"}:
        return True
    if next_char in {"-", "－", "~", "至", "到", "/"} and "月" in text[end : min(len(text), end + 6)]:
        return True
    if prev_char in {"-", "－", "~", "至", "到", "/"} and next_char == "月":
        return True
    return False


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"^\s*(?:行动指南|优势|短板|核心策略)\s*[：:]\s*", "", text.strip())
    return cleaned.replace("```", "").strip()
