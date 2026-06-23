"""第八章总结 AI Writer。

本文件负责第八章「优势」「短板」「核心策略」三段落的 AI 生成。
三段内容一次调用生成，减少 token 消耗。默认未传入模型时返回 fallback。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import inspect
import json
import logging
import re
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = """你是三棵树城市焕新事业部区域经理月度经营报告的总结撰写助手。

你的任务是基于提供的事实数据，生成第八章「总结」的三个段落：
1. 优势（1-2 句，提炼突出的正向指标）
2. 短板（1-2 句，提炼关键负向/风险指标）
3. 核心策略（6 个维度各 1 句行动建议）

# 6 维度顺序（批注[32]）
产品、项目、渠道、客户、应收、打样

# 规则
- 只基于输入 action_context 中的事实生成，不编造数据或原因。
- 你只负责归纳和表达，不重新计算数据；数字、单位保持输入原样。
- 应收总额、逾期应收、减值和资金费用必须严格区分。
- 优势只使用 positive_signals；短板只使用 negative_signals。
- 优势为空时写“本期暂无特别突出的正向指标。”，不得虚构优势。
- 每个策略应包含当前问题或机会和明确行动方向；数据缺失时使用不带数字的稳健建议。
- 优势用中文顿号/逗号连接各点，句末句号。
- 短板用中文顿号/逗号连接各点，句末句号。
- 核心策略每条「维度名：策略内容」，用分号分隔。
- 不要输出标题、不要提及接口/模型/程序/生成过程。
- 不要输出「优势：」「短板：」「核心策略：」前缀，只输出内容本身。
- 输出 JSON 格式，advantage、weakness 为字符串，strategies 为字符串数组。

# 输出格式
```json
{
  "advantage": "高增长（销量+58%）、产品结构维稳、绩效优秀（108分）。",
  "weakness": "毛利率侵蚀、应收账款积压、招商停滞。",
  "strategies": [
    "产品：主推真石漆、多彩漆，关注外墙腻子下滑趋势",
    "项目：推进32个出货项目落地，提升单项目销量",
    "渠道：当前8个渠道，拓展至10个以上",
    "客户：维护18个产销客户，提升客均销量至35万",
    "应收：逾期28万需加大清收力度，控制新增减值",
    "打样：费用同比增加，需评估转化效率"
  ]
}
```
"""


async def generate_chapter8_summary(
    action_context: Dict[str, Any],
    model: Optional[Any] = None,
    fallback_advantage: str = "",
    fallback_weakness: str = "",
    fallback_strategies: Optional[List[str]] = None,
) -> Dict[str, str]:
    """一次调用生成优势、短板、核心策略。

    Returns:
        {"advantage": str, "weakness": str, "strategies": List[str]}
    """
    if model is None:
        return {
            "advantage": fallback_advantage,
            "weakness": fallback_weakness,
            "strategies": fallback_strategies or [],
        }

    user_prompt = _build_user_prompt(action_context)
    try:
        raw_text = await _call_model(model, SUMMARY_SYSTEM_PROMPT, user_prompt)
        parsed = _parse_summary_response(raw_text)
        if _contains_unprovided_number(parsed, action_context):
            logger.warning("第八章 AI 输出包含事实包之外的数字，使用规则回退。")
            return {
                "advantage": fallback_advantage,
                "weakness": fallback_weakness,
                "strategies": fallback_strategies or [],
            }
        return {
            "advantage": parsed.get("advantage") or fallback_advantage,
            "weakness": parsed.get("weakness") or fallback_weakness,
            "strategies": parsed.get("strategies") or fallback_strategies or [],
        }
    except Exception as e:
        logger.warning(f"第八章总结 AI 调用失败，使用规则回退: {e}")
        return {
            "advantage": fallback_advantage,
            "weakness": fallback_weakness,
            "strategies": fallback_strategies or [],
        }


class Chapter8SummaryWriter:
    """第八章总结 AI Writer 封装类。"""

    def __init__(self, model: Optional[Any] = None):
        self.model = model

    async def generate(
        self,
        action_context: Dict[str, Any],
        fallback_advantage: str = "",
        fallback_weakness: str = "",
        fallback_strategies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await generate_chapter8_summary(
            action_context=action_context,
            model=self.model,
            fallback_advantage=fallback_advantage,
            fallback_weakness=fallback_weakness,
            fallback_strategies=fallback_strategies,
        )


def _build_user_prompt(action_context: Dict[str, Any]) -> str:
    return f"""请基于以下事实生成第八章总结：

```json
{json.dumps(action_context, ensure_ascii=False, indent=2)}
```

要求：
- 优势提炼 performance 和 positive_signals 中的突出亮点。
- 短板提炼 negative_signals 中的关键问题。
- 核心策略逐维度（产品、项目、渠道、客户、应收、打样）输出 1 句行动建议。
- 只输出 JSON，不要输出其他内容。
"""


def _contains_unprovided_number(result: Dict[str, Any], action_context: Dict[str, Any]) -> bool:
    """模型文案中的每个数字都必须能在事实包中原样找到。"""
    if not result:
        return False
    allowed = set(_number_tokens(json.dumps(action_context, ensure_ascii=False)))
    output = json.dumps(result, ensure_ascii=False)
    return any(token not in allowed for token in _number_tokens(output))


def _number_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    for token in re.findall(r"[-+]?\d+(?:\.\d+)?", str(text or "")):
        try:
            normalized = format(Decimal(token).normalize(), "f")
        except InvalidOperation:
            normalized = token.lstrip("+")
        tokens.append(normalized)
    return tokens


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


def _parse_summary_response(text: str) -> Dict[str, Any]:
    """从 AI 响应中解析 JSON，带多层回退。"""
    text = str(text or "").strip()
    if not text:
        return {}

    # 去掉 markdown 代码块包裹
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 尝试直接解析 JSON
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return _validate_result(result)
    except (json.JSONDecodeError, TypeError):
        pass

    # 尝试从文本中提取 JSON 块
    json_match = re.search(r'\{[^{}]*"advantage"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group())
            if isinstance(result, dict):
                return _validate_result(result)
        except (json.JSONDecodeError, TypeError):
            pass

    # 尝试提取更大的 JSON 块
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group())
            if isinstance(result, dict):
                return _validate_result(result)
        except (json.JSONDecodeError, TypeError):
            pass

    logger.warning(f"第八章 AI 响应无法解析为 JSON，使用 fallback。原始文本前 200 字符: {text[:200]}")
    return {}


def _validate_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """校验并标准化解析结果。"""
    validated: Dict[str, Any] = {}

    advantage = result.get("advantage")
    if isinstance(advantage, str) and advantage.strip():
        validated["advantage"] = advantage.strip()

    weakness = result.get("weakness")
    if isinstance(weakness, str) and weakness.strip():
        validated["weakness"] = weakness.strip()

    strategies = result.get("strategies")
    if isinstance(strategies, list):
        validated["strategies"] = [s.strip() for s in strategies if isinstance(s, str) and s.strip()]
    elif isinstance(strategies, str) and strategies.strip():
        # 可能是分号分隔的字符串
        validated["strategies"] = [s.strip() for s in strategies.split("；") if s.strip()]

    return validated
