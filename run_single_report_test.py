"""单人完整报告测试入口。

默认测试图片中确认的人员：
    job_id=06427, calmonth=202606

示例：
    python run_single_report_test.py --api-key xxx
    python run_single_report_test.py --job-id 06427 --calmonth 202606 --api-key xxx
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from Data import add_ranking_population_totals, extract_employee_configs, fetch_employee_org_data
from ReportGenerator.full_report_generator import FullReportGenerator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="测试生成单个区域经理的 1-8 章完整报告")
    parser.add_argument("--job-id", default="06427", help="区域经理工号，默认 06427")
    parser.add_argument("--calmonth", default="202606", help="月份，默认 202606")
    parser.add_argument("--report-period", default="", help="报告展示截止月份，默认按 calmonth 的上一个月推导")
    parser.add_argument("--api-key", default=None, help="接口 apikey；也可通过 SKSHU_BI_API_KEY 环境变量提供")
    parser.add_argument("--employee-org-api-url", default=None, help="人员名单接口 URL")
    parser.add_argument("--chapter-api-url", default=None, help="章节数据接口 URL")
    parser.add_argument("--output-root", default=str(BASE_DIR / "Reports" / "full_report_tests"), help="输出根目录")
    parser.add_argument("--timeout", type=int, default=30, help="接口超时秒数")
    parser.add_argument("--verify-ssl", action="store_true", help="开启 SSL 证书校验")
    parser.add_argument("--skip-employee-api", action="store_true", help="跳过人员名单接口，用命令行参数构造测试人员")
    parser.add_argument("--name", default="", help="skip employee api 时使用的姓名")
    return parser


def save_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def load_person_config(args: argparse.Namespace, output_root: Path) -> Dict[str, Any]:
    if args.skip_employee_api:
        return {
            "calmonth": args.calmonth,
            "job_id": args.job_id,
            "sale_name": args.name,
            "sale_class": "",
            "city_operation_department": "",
            "province": "",
            "region": "",
            "business_department": "城市焕新事业部",
        }

    response = await fetch_employee_org_data(
        api_key=args.api_key,
        api_url=args.employee_org_api_url,
        timeout=args.timeout,
        verify_ssl=args.verify_ssl,
    )
    save_json(output_root / args.calmonth / "_employee_org_raw.json", response)
    if "error" in response:
        raise SystemExit(f"人员名单接口请求失败: {response.get('error')} - {response.get('message', '')}")

    configs = extract_employee_configs(response, calmonth=args.calmonth)
    save_json(output_root / args.calmonth / "_employee_org_configs.json", configs)
    person = find_person(configs, args.job_id)
    if person:
        return add_ranking_population_totals(person, configs)

    available = ", ".join(config.get("job_id", "") for config in configs[:10])
    raise SystemExit(f"人员名单中找不到工号 {args.job_id}。前 10 个工号: {available}")


def find_person(configs: List[Dict[str, Any]], job_id: str) -> Optional[Dict[str, Any]]:
    for config in configs:
        if str(config.get("job_id")) == str(job_id):
            return config
    return None


async def run(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root)
    person_config = await load_person_config(args, output_root)
    print(f"测试人员: {person_config.get('job_id')} {person_config.get('sale_name') or ''}")

    generator = FullReportGenerator(
        person_config=person_config,
        calmonth=args.calmonth,
        report_period=args.report_period or None,
        output_root=output_root,
        api_key=args.api_key,
        api_url=args.chapter_api_url,
        timeout=args.timeout,
        verify_ssl=args.verify_ssl,
        ai_required=True,
    )
    result = await generator.run()

    chapter7 = result.diagnostics.get("derived", {}).get("chapter7", {})
    print(f"完整报告目录: {result.report_dir.resolve()}")
    print(f"Markdown: {result.markdown_path.resolve()}")
    print(f"HTML: {result.html_path.resolve()}")
    print(f"PDF: {result.pdf_path.resolve()}")
    print(f"诊断: {result.diagnostics_path.resolve()}")
    print(f"第七章派生状态: {chapter7.get('status', 'unknown')}")
    chapter8 = result.diagnostics.get("chapters", {}).get("8", {})
    print(f"第八章总结来源: {chapter8.get('summary_source', 'unknown')}")
    print(f"第八章 PDF: {chapter8.get('pdf', '')}")
    if chapter7.get("missing_fields"):
        print(f"第七章缺失字段: {', '.join(chapter7['missing_fields'])}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
