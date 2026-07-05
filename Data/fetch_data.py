"""
二期数据拉取 - 城市焕新事业部 API
API: getEmployeeIndexAiCcq
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
from urllib import error, parse, request
from typing import Dict, Any, List, Optional

DEFAULT_API_BASE_URL = "https://apidev.skshu.com/test/skshu-bi-api/biapitoxt/getEmployeeIndexAiCcq"
DEFAULT_EMPLOYEE_ORG_API_BASE_URL = "https://apidev.skshu.com/test/skshu-bi-api/biapitoxt/getAiEmployeeOrgGcq"


def _limit_text(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"


def _api_error_response(
    error_code: str,
    message: str,
    failure_type: str,
    failure_stage: str,
    **details: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": error_code,
        "message": message,
        "failure_type": failure_type,
        "failure_stage": failure_stage,
    }
    payload.update({key: value for key, value in details.items() if value not in (None, "")})
    return payload


def _http_error_body(exc: error.HTTPError) -> str:
    try:
        return _limit_text(exc.read().decode("utf-8", errors="replace"))
    except Exception:
        return ""


def resolve_api_key(api_key: Optional[str] = None) -> Optional[str]:
    """优先使用入参，其次使用环境变量，避免在业务代码里硬编码 key。"""
    return api_key or os.getenv("SKSHU_BI_API_KEY")


def resolve_api_url(api_url: Optional[str] = None) -> str:
    """优先使用入参，其次使用环境变量，最后回退到开发环境接口。"""
    return api_url or os.getenv("SKSHU_EMPLOYEE_INDEX_CCQ_API_URL") or DEFAULT_API_BASE_URL


def resolve_employee_org_api_url(api_url: Optional[str] = None) -> str:
    """优先使用入参，其次使用环境变量，最后回退到人员名单开发环境接口。"""
    return api_url or os.getenv("SKSHU_EMPLOYEE_ORG_GCQ_API_URL") or DEFAULT_EMPLOYEE_ORG_API_BASE_URL


def _post_json(url: str, payload: Dict[str, Any], timeout: int, verify_ssl: bool) -> Dict[str, Any]:
    """使用标准库请求 JSON，减少二期接口脚本的额外依赖。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )

    context = None
    if not verify_ssl:
        import ssl

        context = ssl._create_unverified_context()

    with request.urlopen(req, timeout=timeout, context=context) as resp:
        raw_text = resp.read().decode("utf-8")
    return json.loads(raw_text)


async def fetch_chapter_data(
    job_id: str,
    time: str,
    module: int,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    session: Optional[Any] = None,
    timeout: int = 30,
    verify_ssl: bool = False,
) -> Dict[str, Any]:
    """
    拉取单个模块的章节数据

    :param job_id: 区域经理工号
    :param time: 月份，格式 YYYYMM
    :param module: 模块标识（1-8）
    :param api_key: 接口 apikey；也可通过 SKSHU_BI_API_KEY 提供
    :param api_url: 接口地址；也可通过 SKSHU_EMPLOYEE_INDEX_CCQ_API_URL 提供
    :param session: 兼容旧调用的保留参数；标准库请求中不使用
    :param timeout: 超时秒数
    :param verify_ssl: 是否校验证书；开发环境默认为 False，生产环境建议 True
    :return: API 响应 JSON
    """
    resolved_api_key = resolve_api_key(api_key)
    failure_stage = "fetch_chapter_api"
    if not resolved_api_key:
        return _api_error_response(
            "missing_api_key",
            "Missing API key. Pass api_key or set SKSHU_BI_API_KEY.",
            "configuration_error",
            failure_stage,
            job_id=job_id,
            calmonth=time,
            module=module,
        )

    query = parse.urlencode({"apikey": resolved_api_key})
    base_url = resolve_api_url(api_url)
    url = f"{base_url}?{query}"
    body = {
        "ZEMPLOYEE": job_id,
        "CALMONTH": time,
        "MOUDLE": str(module)
    }

    try:
        return await asyncio.to_thread(_post_json, url, body, timeout, verify_ssl)
    except error.HTTPError as e:
        return _api_error_response(
            "http_error",
            f"HTTP {e.code}: {e.reason}",
            "interface_error",
            failure_stage,
            status_code=e.code,
            reason=str(e.reason),
            response_text=_http_error_body(e),
            api_url=base_url,
            job_id=job_id,
            calmonth=time,
            module=module,
        )
    except error.URLError as e:
        reason = getattr(e, "reason", e)
        return _api_error_response(
            "connection_error",
            str(reason),
            "interface_error",
            failure_stage,
            api_url=base_url,
            job_id=job_id,
            calmonth=time,
            module=module,
        )
    except (TimeoutError, socket.timeout) as e:
        return _api_error_response(
            "timeout",
            f"Request timed out after {timeout}s: {e}",
            "interface_error",
            failure_stage,
            api_url=base_url,
            job_id=job_id,
            calmonth=time,
            module=module,
            timeout=timeout,
        )
    except json.JSONDecodeError as e:
        return _api_error_response(
            "json_decode_error",
            f"Invalid JSON response: {e}",
            "interface_error",
            failure_stage,
            api_url=base_url,
            job_id=job_id,
            calmonth=time,
            module=module,
        )
    except Exception as e:
        return _api_error_response(
            type(e).__name__,
            str(e),
            "program_error",
            failure_stage,
            exception_type=type(e).__name__,
            api_url=base_url,
            job_id=job_id,
            calmonth=time,
            module=module,
        )


async def fetch_chapter_data_batch(
    requests: List[Dict[str, Any]],
    concurrent_limit: int = 3,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    timeout: int = 30,
    verify_ssl: bool = False,
) -> Dict[int, Dict[str, Any]]:
    """
    批量拉取多个模块数据（并发）

    :param requests: [{"job_id": "...", "time": "...", "module": 1}, ...]
    :param concurrent_limit: 并发数
    :param api_key: 接口 apikey；也可在单个 request 中提供
    :param api_url: 接口地址；也可在单个 request 中提供
    :param timeout: 超时秒数
    :param verify_ssl: 是否校验证书
    :return: {module: api_response, ...}
    """
    semaphore = asyncio.Semaphore(concurrent_limit)

    async def _fetch_one(req):
        async with semaphore:
            return req["module"], await fetch_chapter_data(
                job_id=req["job_id"],
                time=req["time"],
                module=req["module"],
                api_key=req.get("api_key", api_key),
                api_url=req.get("api_url", api_url),
                timeout=req.get("timeout", timeout),
                verify_ssl=req.get("verify_ssl", verify_ssl),
            )

    tasks = [_fetch_one(req) for req in requests]
    results = await asyncio.gather(*tasks)
    return {module: data for module, data in results}


async def fetch_employee_org_data(
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    timeout: int = 30,
    verify_ssl: bool = False,
) -> Dict[str, Any]:
    """
    拉取城市焕新事业部人员名单。

    :param api_key: 接口 apikey；也可通过 SKSHU_BI_API_KEY 提供
    :param api_url: 接口地址；也可通过 SKSHU_EMPLOYEE_ORG_GCQ_API_URL 提供
    :param timeout: 超时秒数
    :param verify_ssl: 是否校验证书
    :return: API 响应 JSON
    """
    resolved_api_key = resolve_api_key(api_key)
    failure_stage = "fetch_employee_org_api"
    if not resolved_api_key:
        return _api_error_response(
            "missing_api_key",
            "Missing API key. Pass api_key or set SKSHU_BI_API_KEY.",
            "configuration_error",
            failure_stage,
        )

    query = parse.urlencode({"apikey": resolved_api_key})
    base_url = resolve_employee_org_api_url(api_url)
    url = f"{base_url}?{query}"

    try:
        return await asyncio.to_thread(_post_json, url, {}, timeout, verify_ssl)
    except error.HTTPError as e:
        return _api_error_response(
            "http_error",
            f"HTTP {e.code}: {e.reason}",
            "interface_error",
            failure_stage,
            status_code=e.code,
            reason=str(e.reason),
            response_text=_http_error_body(e),
            api_url=base_url,
        )
    except error.URLError as e:
        reason = getattr(e, "reason", e)
        return _api_error_response(
            "connection_error",
            str(reason),
            "interface_error",
            failure_stage,
            api_url=base_url,
        )
    except (TimeoutError, socket.timeout) as e:
        return _api_error_response(
            "timeout",
            f"Request timed out after {timeout}s: {e}",
            "interface_error",
            failure_stage,
            api_url=base_url,
            timeout=timeout,
        )
    except json.JSONDecodeError as e:
        return _api_error_response(
            "json_decode_error",
            f"Invalid JSON response: {e}",
            "interface_error",
            failure_stage,
            api_url=base_url,
        )
    except Exception as e:
        return _api_error_response(
            type(e).__name__,
            str(e),
            "program_error",
            failure_stage,
            exception_type=type(e).__name__,
            api_url=base_url,
        )


def transform_employee_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """将人员名单接口字段转换成报告生成内部字段。"""
    return {
        "calmonth": str(record.get("CALMONTH") or ""),
        "job_id": str(record.get("ZEMPLOYEE") or ""),
        "sale_name": str(record.get("ZEMP_CD") or ""),
        "sale_class": str(record.get("ZGWMC") or record.get("岗位名称") or ""),
        "city_operation_department": str(record.get("ZORGWB6") or ""),
        "province": str(record.get("ZORGWB5") or ""),
        "region": str(record.get("ZORGWB4") or ""),
        "business_department": str(record.get("ZORGWB3") or ""),
    }


def extract_employee_configs(response: Dict[str, Any], calmonth: Optional[str] = None) -> List[Dict[str, Any]]:
    """从人员名单响应中提取并过滤内部人员配置。"""
    if not isinstance(response, dict):
        return []
    rows = response.get("data")
    if not isinstance(rows, list):
        return []

    configs = [transform_employee_record(row) for row in rows if isinstance(row, dict)]
    configs = [config for config in configs if config.get("job_id")]
    if calmonth:
        configs = [config for config in configs if config.get("calmonth") in ("", calmonth)]
    return configs


def add_ranking_population_totals(
    person: Dict[str, Any],
    employee_configs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """按工号去重，补充省区和事业部排名分母。"""
    result = dict(person)
    province = str(result.get("province") or "").strip()
    business_department = str(result.get("business_department") or "").strip()

    unique_people: Dict[str, Dict[str, Any]] = {}
    for config in employee_configs:
        job_id = str(config.get("job_id") or "").strip()
        if job_id:
            unique_people[job_id] = config

    if province:
        result["province_ranking_total"] = sum(
            1 for config in unique_people.values()
            if str(config.get("province") or "").strip() == province
        ) or None
    if business_department:
        result["business_ranking_total"] = sum(
            1 for config in unique_people.values()
            if str(config.get("business_department") or "").strip() == business_department
        ) or None
    return result
