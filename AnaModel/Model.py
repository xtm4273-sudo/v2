"""
二期模型配置 - DeepSeek API
"""
from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from ReportAI.settings import AISettings

AnaModel = ChatOpenAI

def create_model(temperature: float = 0.1) -> ChatOpenAI:
    settings = AISettings.from_env()
    return ChatOpenAI(
        model=settings.model,
        temperature=temperature,
        api_key=SecretStr(settings.api_key),
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


DeepSeek_model = create_model()
