"""
测试第二章生成器 - 使用 2023.md 中的模块2示例数据
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from AnaModel import DeepSeek_model
from ReportGenerator.chapter2_generator import Chapter2Generator, format_chapter2_data
from ReportGenerator.chapter2_renderer import (
    build_final_markdown,
    save_final_html,
    save_final_pdf,
)

# 2023.md 中的模块2示例数据（已清洗）
SAMPLE_DATA = [
    {"指标名称": "营业收入（不含税）", "指标数据": {"实际值": "6.826", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "个人人工费用", "指标数据": {"实际值": "11.505", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "差旅费", "指标数据": {"实际值": "7.684", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "减值损失", "指标数据": {"实际值": "0.000", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "财务费用", "指标数据": {"实际值": "0.000", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "样板物料", "指标数据": {"实际值": "0.029", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "其他各类费用", "指标数据": {"实际值": "47.362", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "分摊前利润", "指标数据": {"实际值": "-56.849", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "其中：基本薪酬+提成奖金+年终奖", "指标数据": {"实际值": "3.821", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "年"}},
    {"指标名称": "营业收入（不含税）", "指标数据": {"实际值": "0.784", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "月"}},
    {"指标名称": "营业收入（不含税）", "指标数据": {"实际值": "0.784", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "季"}},
    {"指标名称": "个人人工费用", "指标数据": {"实际值": "2.491", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "季"}},
    {"指标名称": "其中：基本薪酬+提成奖金+年终奖", "指标数据": {"实际值": "0.969", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "月"}},
    {"指标名称": "其中：基本薪酬+提成奖金+年终奖", "指标数据": {"实际值": "0.969", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "季"}},
    {"指标名称": "差旅费", "指标数据": {"实际值": "1.522", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "月"}},
    {"指标名称": "差旅费", "指标数据": {"实际值": "1.522", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "季"}},
    {"指标名称": "减值损失", "指标数据": {"实际值": "0.000", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "月"}},
    {"指标名称": "减值损失", "指标数据": {"实际值": "0.000", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "季"}},
    {"指标名称": "财务费用", "指标数据": {"实际值": "0.000", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "月"}},
    {"指标名称": "财务费用", "指标数据": {"实际值": "0.000", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "季"}},
    {"指标名称": "样板物料", "指标数据": {"实际值": "0.000", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "月"}},
    {"指标名称": "样板物料", "指标数据": {"实际值": "0.000", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "季"}},
    {"指标名称": "分摊前利润", "指标数据": {"实际值": "-26.284", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "月"}},
    {"指标名称": "分摊前利润", "指标数据": {"实际值": "-26.284", "目标值": 0, "同期数": 0, "单位": "万元", "日期类型": "季"}},
]


async def main():
    # 1. 先看数据格式化的结果
    print("=" * 60)
    print("步骤1: 数据格式化 → 利润瀑布表")
    print("=" * 60)
    table, stats = format_chapter2_data(SAMPLE_DATA)
    print(table)
    print(f"\n数据完整性: 有数据 {stats['有数据']} 项, 缺失 {stats['缺数据']} 项")

    # 2. 加载指南
    guideline = Path("guidelines/chapter2_guideline.md").read_text(encoding="utf-8")

    # 3. 运行生成器
    print("\n" + "=" * 60)
    print("步骤2: LLM 生成报告")
    print("=" * 60)
    generator = Chapter2Generator(
        llm=DeepSeek_model,
        data=SAMPLE_DATA,
        guideline=guideline,
        sale_id="86002542",
        sale_name="李泽豪",
    )
    result = await generator.run_async()
    print(result)

    # 4. 保存结果
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "chapter2_test_output.md"
    output_file.write_text(result, encoding="utf-8")
    print(f"\n结果已保存到: {output_file}")

    # 5. 输出客户查看版 HTML/PDF
    final_dir = Path("Reports") / "chapter2_final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_markdown = build_final_markdown(SAMPLE_DATA, period="202605")

    final_md_file = final_dir / "chapter2_final_report.md"
    final_html_file = final_dir / "chapter2_final_report.html"
    final_pdf_file = final_dir / "chapter2_final_report.pdf"

    final_md_file.write_text(final_markdown, encoding="utf-8")
    save_final_html(final_markdown, final_html_file)
    save_final_pdf(final_markdown, final_pdf_file)

    print("\n" + "=" * 60)
    print("步骤3: 生成客户查看版 HTML/PDF")
    print("=" * 60)
    print(final_markdown)
    print(f"HTML 已保存到: {final_html_file}")
    print(f"PDF 已保存到: {final_pdf_file}")


if __name__ == "__main__":
    asyncio.run(main())
