"""
二期模型配置 - DeepSeek API
"""
from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from typing import Union

AnaModel = ChatOpenAI

DEEPSEEK_MODEL_NAME = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_API_KEY = "sk-8cb6a7e7b2c647a8ada1d53368e64a32"


def create_model(temperature: float = 0.1) -> ChatOpenAI:
    return ChatOpenAI(
        model=DEEPSEEK_MODEL_NAME,
        temperature=temperature,
        api_key=SecretStr(DEEPSEEK_API_KEY),
        base_url=DEEPSEEK_BASE_URL,
        timeout=600,
        max_retries=2,
    )


DeepSeek_model = create_model()
