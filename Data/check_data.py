"""二期接口响应校验与章节数据提取。"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple


EMPTY_DATA_MESSAGE = "未读取到有效数据，请确认数据已上传或数据源配置正常后重试。"


class ChapterDataError(ValueError):
    """接口响应无法转换为章节生成数据时抛出。"""


def _empty_data_error(module_label: str, reason: str) -> Tuple[bool, str]:
    return True, f"{module_label}数据异常: {reason}。{EMPTY_DATA_MESSAGE}"


def check_chapter_response(
    response: Dict[str, Any],
    module: Optional[int] = None,
    expected_chapter_keywords: Optional[Iterable[str]] = None,
    required_metric_data_keys: Optional[Iterable[str]] = None,
) -> Tuple[bool, str]:
    """
    校验接口响应是否包含可用的章节数据。

    Returns:
        Tuple[bool, str]: (是否异常, 消息)
    """
    module_label = f"第{module}章" if module is not None else "章节"

    if response is None:
        return _empty_data_error(module_label, "原始响应为 null")

    if not isinstance(response, dict):
        return _empty_data_error(module_label, "原始响应不是字典类型")

    if not response:
        return _empty_data_error(module_label, "原始响应为空对象")

    if "error" in response:
        return True, f"{module_label}接口请求失败: {response.get('error')} - {response.get('message', '')}"

    if response.get("code") not in (None, 1, "1"):
        return True, f"{module_label}接口返回失败: code={response.get('code')}, message={response.get('message')}"

    data = response.get("data")
    if data is None:
        return _empty_data_error(module_label, "缺少 data 字段或 data 为 null")

    if not isinstance(data, dict):
        return _empty_data_error(module_label, "data 字段不是字典类型")

    if not data:
        return _empty_data_error(module_label, "data 字段为空对象")

    chapter_data = data.get("章节数据")
    if chapter_data is None:
        return _empty_data_error(module_label, "缺少章节数据或章节数据为 null")

    if not isinstance(chapter_data, list):
        return _empty_data_error(module_label, "章节数据不是列表")

    if not chapter_data:
        return _empty_data_error(module_label, "章节数据为空数组")

    chapter_name = str(data.get("章节名称", ""))
    if expected_chapter_keywords:
        if not any(keyword in chapter_name for keyword in expected_chapter_keywords):
            expected = " / ".join(expected_chapter_keywords)
            return True, f"{module_label}数据异常: 章节名称为「{chapter_name}」，不匹配「{expected}」。"

    required_metric_keys = list(required_metric_data_keys or [])
    valid_metric_count = 0
    for index, item in enumerate(chapter_data, 1):
        if not isinstance(item, dict):
            return True, f"{module_label}数据异常: 第{index}条指标不是字典。"
        if not item:
            return _empty_data_error(module_label, f"第{index}条指标为空对象")
        if not item.get("指标名称") and not item.get("指标路径"):
            return True, f"{module_label}数据异常: 第{index}条指标缺少指标名称和指标路径。"
        metric_data = item.get("指标数据")
        if metric_data is None:
            return _empty_data_error(module_label, f"第{index}条指标缺少指标数据或指标数据为 null")
        if not isinstance(metric_data, dict):
            return _empty_data_error(module_label, f"第{index}条指标数据不是字典类型")
        if not metric_data:
            return _empty_data_error(module_label, f"第{index}条指标数据为空对象")
        missing_keys = [key for key in required_metric_keys if key not in metric_data]
        if missing_keys:
            return True, f"{module_label}数据异常: 第{index}条指标数据缺少字段 {missing_keys}。"
        valid_metric_count += 1

    if valid_metric_count == 0:
        return _empty_data_error(module_label, "清洗前未发现有效指标数据")

    return False, "数据正常"


def extract_chapter_data(
    response: Dict[str, Any],
    module: Optional[int] = None,
    expected_chapter_keywords: Optional[Iterable[str]] = None,
    required_metric_data_keys: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """校验响应并提取 data.章节数据。"""
    has_error, message = check_chapter_response(
        response=response,
        module=module,
        expected_chapter_keywords=expected_chapter_keywords,
        required_metric_data_keys=required_metric_data_keys,
    )
    if has_error:
        raise ChapterDataError(message)
    return response["data"]["章节数据"]
