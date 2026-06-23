"""把各章确定性结果压缩为带证据编号的 AI 事实包。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


SECTION_PREFIX = {
    "chapter3": "C3",
    "chapter4": "C4",
    "chapter5": "C5",
    "chapter7": "C7",
    "chapter8": "C8",
}


@dataclass(frozen=True)
class Evidence:
    id: str
    path: str
    value: Any

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "path": self.path, "value": self.value}


def build_fact_pack(section_contexts: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """生成紧凑事实列表；姓名和工号等元数据不发送给外部模型。"""
    output: Dict[str, List[Dict[str, Any]]] = {}
    for section, prefix in SECTION_PREFIX.items():
        flattened: List[tuple[str, Any]] = []
        _flatten(section_contexts.get(section, {}), "", flattened)
        output[section] = [
            Evidence(f"{prefix}-{index:03d}", path, value).to_dict()
            for index, (path, value) in enumerate(flattened, 1)
        ]
    return output


def _flatten(value: Any, path: str, output: List[tuple[str, Any]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text in {"区域经理工号", "区域经理姓名", "employee_id", "manager_name"}:
                continue
            _flatten(child, f"{path}.{key_text}".strip("."), output)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _flatten(child, f"{path}[{index}]", output)
        if not value:
            output.append((path, "无"))
        return
    output.append((path or "value", "待补充" if value is None or value == "" else value))


def evidence_ids(fact_pack: Dict[str, Iterable[Dict[str, Any]]]) -> set[str]:
    return {
        str(item.get("id"))
        for items in fact_pack.values()
        for item in items
        if isinstance(item, dict) and item.get("id")
    }
