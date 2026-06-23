"""报告 AI 配置。

真实密钥只从进程环境或项目根目录的 .env 读取，禁止写入源码。
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


class AIConfigurationError(RuntimeError):
    """AI 配置缺失或非法。"""


def load_env_file(path: Path) -> None:
    """加载简单 KEY=VALUE 配置，不覆盖进程已注入的环境变量。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class AISettings:
    api_key: str
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    timeout_seconds: int = 120
    max_retries: int = 2
    temperature: float = 0.1
    prompt_version: str = "report-narrative-bundle-v1"
    required: bool = True

    @classmethod
    def from_env(cls, project_dir: Optional[Path] = None) -> "AISettings":
        base_dir = project_dir or Path(__file__).resolve().parents[1]
        load_env_file(base_dir / ".env")
        api_key = (os.getenv("AI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "").strip()
        if not api_key:
            raise AIConfigurationError(
                f"缺少 AI_API_KEY。请在 {base_dir / '.env'} 中配置，或通过服务器 Secret 注入。"
            )
        return cls(
            api_key=api_key,
            base_url=os.getenv("AI_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("AI_MODEL", cls.model),
            timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", str(cls.timeout_seconds))),
            max_retries=int(os.getenv("AI_MAX_RETRIES", str(cls.max_retries))),
            temperature=float(os.getenv("AI_TEMPERATURE", str(cls.temperature))),
            prompt_version=os.getenv("AI_PROMPT_VERSION", cls.prompt_version),
            required=os.getenv("AI_REQUIRED", "true").lower() not in {"0", "false", "no"},
        )
