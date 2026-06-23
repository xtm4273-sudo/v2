"""第四章行动指南 AI Writer。

本文件只负责第四章「行动指南」中的两条建议，不参与数据清洗、Top3 排序、
价格/结构表格、Markdown 结构或 HTML/PDF 版式生成。
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import inspect
import json
import logging
import re

logger = logging.getLogger(__name__)


ACTION_GUIDE_SYSTEM_PROMPT = """你是三棵树城市焕新事业部区域经理报告的行动指南撰写助手。

只允许基于输入 action_context 中的事实生成第四章行动指南。
只生成两个字段：structure_action 和 price_action。
禁止编造毛利率、客户、项目、费用、成本、利润、目标、同期或接口未提供的数据。
禁止改写价格变动、结构变化、产品排序、数值和报告模板。
输出必须是 JSON 对象，不要带 Markdown，不要提及接口、模型、程序或生成过程。
"""


async def generate_chapter4_actions(
    action_context: Dict[str, Any],
    model: Optional[Any] = None,
    fallback_actions: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """生成第四章行动指南两条建议。

    Args:
        action_context: 由 chapter4_generator.build_chapter4_action_context 生成的事实包。
        model: 支持 LangChain ainvoke/invoke，或 async callable。
        fallback_actions: 模型缺失/失败/空输出时的规则回退文案。

    Returns:
        Dict[str, str]: {"structure_action": "...", "price_action": "..."}
    """
    fallback = fallback_actions or {"structure_action": "", "price_action": ""}
    if model is None:
        return fallback

    user_prompt = _build_user_prompt(action_context)
    try:
        raw_text = await _call_model(model, ACTION_GUIDE_SYSTEM_PROMPT, user_prompt)
        parsed = _parse_action_json(raw_text)
        if not parsed:
            return fallback
        return {
            "structure_action": _sanitize_action(parsed.get("structure_action")) or fallback.get("structure_action", ""),
            "price_action": _sanitize_action(parsed.get("price_action")) or fallback.get("price_action", ""),
        }
    except Exception as e:
        logger.warning(f"第四章行动指南 AI 调用失败，使用规则回退: {e}")
        return fallback


class Chapter4ActionGuideWriter:
    """行动指南 Writer 适配器，供第四章异步生成入口注入。"""

    def __init__(self, model: Optional[Any] = None):
        self.model = model

    async def generate(
        self,
        action_context: Dict[str, Any],
        fallback_actions: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        return await generate_chapter4_actions(
            action_context=action_context,
            model=self.model,
            fallback_actions=fallback_actions,
        )


def _build_user_prompt(action_context: Dict[str, Any]) -> str:
    context_json = json.dumps(action_context, ensure_ascii=False, indent=2)
    return f"""请根据以下 action_context 生成第四章行动指南。

要求：
1. 只输出 JSON：{{"structure_action": "...", "price_action": "..."}}。
2. structure_action 只围绕 structure_top3 中的产品结构事实给建议。
3. price_action 优先围绕 price_down_top3 中收入占比较高且均价下降的产品给稳价建议；如果没有价格下降产品，再围绕 price_up_top3 给建议。
4. 每个字段各 1 句，语气专业、简洁、可执行。
5. 不要新增 action_context 没有的产品名或数值。

action_context:
{context_json}
"""


async def _call_model(model: Any, system_prompt: str, user_prompt: str) -> str:
    if hasattr(model, "ainvoke"):
        response = await model.ainvoke(_langchain_messages(system_prompt, user_prompt))
        return _response_text(response)

    if hasattr(model, "invoke"):
        response = model.invoke(_langchain_messages(system_prompt, user_prompt))
        return _response_text(response)

    if callable(model):
        result = model(system_prompt, user_prompt)
        if inspect.isawaitable(result):
            result = await result
        return _response_text(result)

    raise TypeError("Unsupported action guide model interface.")


def _langchain_messages(system_prompt: str, user_prompt: str) -> list:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    except Exception:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]


def _response_text(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    content = getattr(response, "content", None)
    if content is not None:
        return str(content)
    if isinstance(response, dict):
        return str(response.get("content") or response.get("text") or "")
    return str(response)


def _parse_action_json(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _sanitize_action(text: Any) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    for prefix in ("◇", "产品结构：", "产品结构:", "价格：", "价格:", "行动指南：", "行动指南:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return " ".join(cleaned.split())
