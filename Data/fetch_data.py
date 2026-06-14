"""
二期数据拉取 - 城市焕新事业部 API
API: getEmployeeIndexAiCcq
"""
import aiohttp
import asyncio
from typing import Dict, Any, List, Optional
from aiohttp import ClientTimeout, ClientSession

API_BASE_URL = "https://apidev.skshu.com/test/skshu-bi-api/biapitoxt/getEmployeeIndexAiCcq"
API_KEY = "05b65dfd5ee44f2a21f2312372b76f75"


async def fetch_chapter_data(
    job_id: str,
    time: str,
    module: int,
    session: Optional[ClientSession] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    拉取单个模块的章节数据

    :param job_id: 区域经理工号
    :param time: 月份，格式 YYYYMM
    :param module: 模块标识（1-5）
    :param session: 复用的 aiohttp session
    :param timeout: 超时秒数
    :return: API 响应 JSON
    """
    url = f"{API_BASE_URL}?apikey={API_KEY}"
    body = {
        "ZEMPLOYEE": job_id,
        "CALMONTH": time,
        "MOUDLE": str(module)
    }
    headers = {"Content-Type": "application/json"}

    should_close = session is None
    if session is None:
        session = ClientSession()

    try:
        async with session.post(
            url, json=body, headers=headers,
            timeout=ClientTimeout(total=timeout), ssl=False
        ) as resp:
            return await resp.json()
    except Exception as e:
        return {"error": type(e).__name__, "message": str(e)}
    finally:
        if should_close:
            await session.close()


async def fetch_chapter_data_batch(
    requests: List[Dict[str, Any]],
    concurrent_limit: int = 3
) -> Dict[int, Dict[str, Any]]:
    """
    批量拉取多个模块数据（并发）

    :param requests: [{"job_id": "...", "time": "...", "module": 1}, ...]
    :param concurrent_limit: 并发数
    :return: {module: api_response, ...}
    """
    semaphore = asyncio.Semaphore(concurrent_limit)

    async def _fetch_one(req, session):
        async with semaphore:
            return req["module"], await fetch_chapter_data(
                job_id=req["job_id"],
                time=req["time"],
                module=req["module"],
                session=session
            )

    async with ClientSession() as session:
        tasks = [_fetch_one(req, session) for req in requests]
        results = await asyncio.gather(*tasks)
        return {module: data for module, data in results}
