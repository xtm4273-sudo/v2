"""第七章行动指南 AI Writer。

本文件只负责第七章「行动指南」段落，不参与拜访量、时间分配
或 HTML/PDF 版式生成。默认未传入模型时返回 fallback。
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import inspect
import json
import logging

logger = logging.getLogger(__name__)


ACTION_GUIDE_SYSTEM_PROMPT = """你是三棵树城市焕新事业部区域经理报告的行销行为行动指南撰写助手。

只允许基于输入 action_context 中的事实生成行动指南。
禁止编造拜访次数、达成率、扣分、客户名或接口未提供的数据。
禁止改写第七章的标题、拜访量数据、时间分配数据。
输出必须是一段或多段中文行动建议，不要带标题，不要提及接口、模型、程序或生成过程。

行动指南基础要求：
- 日均拜访量不低于3次，月度达标60次。
- 结合当前拜访频次缺口，给出针对性建议。
"""


async def generate_chapter7_action_guide(
    action_context: Dict[str, Any],
    model: Optional[Any] = None,
    fallback_text: str = "",
) -> str:
    if model is None:
        return fallback_text

    user_prompt = _build_user_prompt(action_context)
    try:
        raw_text = await _call_model(model, ACTION_GUIDE_SYSTEM_PROMPT, user_prompt)
        return _sanitize_action_guide(raw_text) or fallback_text
    except Exception as e:
        logger.warning(f"第七章行动指南 AI 调用失败，使用规则回退: {e}")
        return fallback_text


class Chapter7ActionGuideWriter:
    def __init__(self, model: Optional[Any] = None):
        self.model = model

    async def generate(self, action_context: Dict[str, Any], fallback_text: str = "") -> str:
        return await generate_chapter7_action_guide(
            action_context=action_context,
            model=self.model,
            fallback_text=fallback_text,
        )


def _build_user_prompt(action_context: Dict[str, Any]) -> str:
    return f"""请基于以下事实生成第七章行动指南：

```json
{json.dumps(action_context, ensure_ascii=False, indent=2)}
```

要求：
- 日均拜访量不低于3次，月度达标60次。
- 若当前拜访频次有缺口，建议补齐。
- 不要编造任何不存在于 action_context 中的数据。
"""


async def _call_model(model: Any, system_prompt: str, user_prompt: str) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if hasattr(model, "ainvoke"):
        response = await model.ainvoke(messages)
        if hasattr(response, "content"):
            return response.content
        return str(response)
    if inspect.iscoroutinefunction(model):
        return await model(messages)
    if callable(model):
        return model(messages)
    raise ValueError(f"不支持的模型类型: {type(model)}")


def _sanitize_action_guide(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                guide = parsed.get("action_guide") or parsed.get("guide") or ""
                if guide:
                    return guide.strip()
        except (json.JSONDecodeError, TypeError):
            pass
    for prefix in ("行动指南：", "行动指南:", "◇ "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text
