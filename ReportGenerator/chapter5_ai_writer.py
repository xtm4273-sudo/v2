"""第五章行动指南 AI Writer 预留接口。

本文件只负责第五章「行动指南」段落，不参与应收树、公式、表格、
排序、省略规则或 PDF/HTML 版式生成。默认未传入模型时返回 fallback。
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import inspect
import json
import logging

logger = logging.getLogger(__name__)


ACTION_GUIDE_SYSTEM_PROMPT = """你是三棵树城市焕新事业部区域经理报告的应收行动指南撰写助手。

只允许基于输入 action_context 中的事实生成一段行动指南。
禁止编造客户名、金额、账龄、逾期、减值损失、财务费用或接口未提供的数据。
禁止改写第五章的标题、公式、表格、客户排序和数据口径。
输出必须是一段中文行动建议，不要带标题，不要提及接口、模型、程序或生成过程。
"""


async def generate_chapter5_action_guide(
    action_context: Dict[str, Any],
    model: Optional[Any] = None,
    fallback_text: str = "",
) -> str:
    """生成第五章行动指南。

    Args:
        action_context: 由 chapter5_generator.build_chapter5_action_context 生成的事实包。
        model: 预留模型对象。支持 LangChain 风格 ainvoke/invoke，或 async callable。
        fallback_text: 模型缺失/失败/空输出时的规则回退文案。

    Returns:
        str: 可直接拼入「行动指南：」后的文本。
    """
    if model is None:
        return fallback_text

    user_prompt = _build_user_prompt(action_context)
    try:
        raw_text = await _call_model(model, ACTION_GUIDE_SYSTEM_PROMPT, user_prompt)
        return _sanitize_action_guide(raw_text) or fallback_text
    except Exception as e:
        logger.warning(f"第五章行动指南 AI 调用失败，使用规则回退: {e}")
        return fallback_text


class Chapter5ActionGuideWriter:
    """行动指南 Writer 适配器，供第五章异步生成入口注入。"""

    def __init__(self, model: Optional[Any] = None):
        self.model = model

    async def generate(self, action_context: Dict[str, Any], fallback_text: str = "") -> str:
        return await generate_chapter5_action_guide(
            action_context=action_context,
            model=self.model,
            fallback_text=fallback_text,
        )


def _build_user_prompt(action_context: Dict[str, Any]) -> str:
    context_json = json.dumps(action_context, ensure_ascii=False, indent=2)
    return f"""请根据以下 action_context 生成 1 段第五章应收行动指南。

要求：
1. 只使用 action_context 里的事实。
2. 优先围绕逾期客户、次月到期款、减值损失、预计跳账龄和财务费用给出清收建议。
3. 如客户明细或金额缺失，只能提示结合销售日报或应收明细进一步核查，不得猜原因。
4. 建议控制在 1 到 2 句，语气专业、简洁、可执行。

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


def _sanitize_action_guide(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    for prefix in ("行动指南：", "行动指南:", "* 行动指南：", "* 行动指南:", "◇ "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return " ".join(cleaned.split())
