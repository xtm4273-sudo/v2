"""OpenAI-compatible HTTP 模型 Adapter。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import time
from typing import Any, Dict
from urllib import error, request

from .settings import AISettings


@dataclass(frozen=True)
class ModelResponse:
    text: str
    request_id: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0


class OpenAICompatibleModel:
    """只暴露一次结构化文本生成所需的最小接口。"""

    def __init__(self, settings: AISettings):
        self.settings = settings

    async def complete(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        return await asyncio.to_thread(self._complete_sync, system_prompt, user_prompt)

    def _complete_sync(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            started = time.monotonic()
            req = request.Request(
                f"{self.settings.base_url}/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {self.settings.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                    parsed = json.loads(response.read().decode("utf-8"))
                    text = parsed["choices"][0]["message"]["content"]
                    return ModelResponse(
                        text=str(text),
                        request_id=str(parsed.get("id") or response.headers.get("x-request-id") or ""),
                        usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {},
                        latency_ms=int((time.monotonic() - started) * 1000),
                    )
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = RuntimeError(f"模型 HTTP {exc.code}: {detail}")
                if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    break
            except (error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < self.settings.max_retries:
                time.sleep(min(2 ** attempt, 4))
        raise RuntimeError(f"大模型调用失败: {last_error}")
