"""
第二章生成器 - 利润概况
读取 API 模块2 数据，格式化利润瀑布表，调用 LLM 生成报告
"""
from AnaModel import AnaModel
from langchain_core.messages import SystemMessage, HumanMessage
from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


def format_chapter2_data(
    raw_chapter_data: List[Dict[str, Any]],
    month_label: str = "当月",
    ytd_label: str = "1-5月累计",
) -> Tuple[str, Dict[str, int]]:
    """
    将 API 返回的章节数据清洗成利润瀑布表

    API 返回格式:
      [{"指标名称": "营业收入（不含税）", "指标数据": {"日期类型": "年", "实际值": "6.826", ...}}, ...]

    输出格式（Markdown 表格）:
      | 科目 | 当月/5月 | 本季度累计 | 1-5月累计 |
    """
    # 按（指标名, 日期类型）建索引
    data_map: Dict[str, Dict[str, str]] = {}
    for item in raw_chapter_data:
        name = item.get("指标名称", "")
        d = item.get("指标数据", {})
        date_type = d.get("日期类型", "")
        actual = d.get("实际值", "")
        target = d.get("目标值", 0)
        yoy = d.get("同期数", 0)
        unit = d.get("单位", "")

        if name not in data_map:
            data_map[name] = {}
        data_map[name][date_type] = {
            "实际值": actual,
            "目标值": str(target),
            "同期数": str(yoy),
            "单位": unit,
        }

    # 模板科目顺序
    subjects = [
        "营业收入（不含税）",
        "毛利率",
        "毛利额",
        "个人人工费用",
        "其中：基本薪酬+提成奖金+年终奖",
        "差旅费",
        "减值损失",
        "财务费用",
        "样板物料",
        "其他各类费用",
        "分摊前利润",
    ]

    lines = [
        f"| 科目 | {month_label} | 本季度累计 | {ytd_label} |",
        "| --- | --- | --- | --- |",
    ]

    stats = {"有数据": 0, "缺数据": 0}
    for subject in subjects:
        cells = [subject]
        for dim_key in ["月", "季", "年"]:
            entry = data_map.get(subject, {}).get(dim_key)
            if entry and entry["实际值"] and entry["实际值"] != "0.000":
                val = float(entry["实际值"])
                unit = entry["单位"]
                cells.append(f"{val:.2f}{unit}")
                stats["有数据"] += 1
            elif entry:
                cells.append("0")
                stats["有数据"] += 1
            else:
                cells.append("—")
                stats["缺数据"] += 1
        lines.append(f"| {' | '.join(cells)} |")

    return "\n".join(lines), stats


class Chapter2Generator:
    """
    第二章「利润概况」生成器

    流程: 接收 API 数据 → 格式化为利润表 → LLM 生成 Markdown 报告
    """

    def __init__(
        self,
        llm: AnaModel,
        data: List[Dict[str, Any]],
        guideline: str,
        sale_id: Optional[str] = None,
        sale_name: Optional[str] = None,
    ):
        self.llm = llm
        self.raw_data = data
        self.guideline = guideline
        self.sale_id = sale_id
        self.sale_name = sale_name

    def format_data(self) -> Tuple[str, Dict[str, int]]:
        """将原始数据格式化为 LLM 可读的表格文本"""
        table, stats = format_chapter2_data(self.raw_data)
        return table, stats

    async def run_async(self) -> str:
        """执行章节生成"""
        try:
            table, stats = self.format_data()

            system_prompt = f"""你是财务经营数据分析师，必须严格基于数据生成报告。\n
# 数据分析指南:\n
{self.guideline}\n
# 重要规则:\n
- 只使用数据中实际存在的数值，如果标注为「—」表示该数据缺失，报告中不要编造
- 保留1位小数
- 数据缺失的指标直接跳过不写
"""

            user_prompt = f"""请基于以下利润瀑布表生成第二章报告内容：

# 利润瀑布数据:
{table}

# 数据完整性: 有数据 {stats['有数据']} 项，缺失 {stats['缺数据']} 项
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            response = await self.llm.ainvoke(messages)
            return response.content

        except Exception as e:
            logger.error(f"第二章生成失败: {e}")
            return f"第二章生成失败: {e}"
