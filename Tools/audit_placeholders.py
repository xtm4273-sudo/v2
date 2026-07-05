#!/usr/bin/env python3
"""Audit generated reports for unresolved placeholders.

The script reads generated markdown reports from the local_deepseek batches and
writes a CSV detail file plus a customer-facing markdown summary.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "Reports"
OUTPUT_DIR = REPORTS / "placeholder_audit_202606_full"
FORMAL_BATCHES = [
    "local_deepseek_10",
    "local_deepseek_50",
    "local_deepseek_100_offset50",
    "local_deepseek_200_offset150",
    "local_deepseek_200_offset350",
    "local_deepseek_200_offset550",
    "local_deepseek_rest_offset750",
]
PLACEHOLDER_PATTERN = re.compile(r"待补充|建议补充|相关数值")
CHAPTER_HEADING = re.compile(r"^# ([一二三四五六七八])、")
PERSON_DIR = re.compile(r"^(?P<job_id>[^_]+)_(?P<name>.+)$")


@dataclass(frozen=True)
class Finding:
    category: str
    severity: str
    chapter: str
    person: str
    job_id: str
    field: str
    evidence: str
    report_path: str
    source_path: str
    customer_action: str
    internal_action: str


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_report_dirs() -> list[Path]:
    dirs: list[Path] = []
    for batch in FORMAL_BATCHES:
        batch_dir = REPORTS / batch
        dirs.extend(sorted(p.parent.parent for p in batch_dir.glob("202606/*/markdown/full_report.md")))
    return dirs


def parse_person(report_dir: Path) -> tuple[str, str, str]:
    match = PERSON_DIR.match(report_dir.name)
    if not match:
        return report_dir.name, "", report_dir.name
    job_id = match.group("job_id")
    name = match.group("name")
    return f"{job_id}_{name}", job_id, name


def chapter_for_lines(lines: list[str], index: int) -> str:
    chapter = ""
    for line in lines[: index + 1]:
        match = CHAPTER_HEADING.match(line.strip())
        if match:
            chapter = f"第{match.group(1)}章"
    return chapter or "未知章节"


def source_for(chapter: str, report_dir: Path) -> str:
    chapter_num = {
        "第一章": "1",
        "第二章": "2",
        "第三章": "3",
        "第四章": "4",
        "第五章": "5",
        "第六章": "6",
        "第七章": "7",
        "第八章": "8",
    }.get(chapter)
    if not chapter_num:
        return ""
    cleaned = report_dir / "cleaned" / f"chapter{chapter_num}_cleaned.json"
    source = report_dir / "cleaned" / "chapter8_source.json"
    raw = report_dir / "raw" / f"module_{chapter_num}.json"
    if chapter_num == "8" and source.exists():
        return rel(source)
    if cleaned.exists():
        return rel(cleaned)
    if raw.exists():
        return rel(raw)
    return ""


def trim_evidence(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())[:500]


def classify(line: str, chapter: str) -> tuple[str, str, str, str, str, str]:
    text = trim_evidence(line)

    if chapter == "第一章" and "月平均得分待补充" in text:
        return (
            "接口需确认",
            "P1",
            "未达百绩效项目/月平均得分",
            "请确认 MODULE=1 是否能在未达百绩效项目中返回每个项目的月平均得分，或提供可按项目名称/编码关联的分项目月平均得分。",
            "",
            "第1章已能拿到项目名称、扣分和权重，但部分 underperforming_items.monthly_score 为 null。",
        )

    if chapter == "第三章" and re.search(r"\|\s*\|\s*增长率\s*\|", text):
        return (
            "业务口径需确认",
            "P1",
            "过程指标同比增长率/同期为0或缺失",
            "请确认过程指标的同比增长率在去年同期为0、今年不为0，或去年同期和今年均为0时，应展示为“不适用/新增N个/100%/0%”中的哪种口径。",
            "",
            "当前生成侧用“待补充”兜底，最终应按客户确认口径改为明确表达。",
        )

    if chapter == "第三章" and re.search(r"\|\s*(目标|实际|达成率|达成差额|同比增长率|同比差额)\s*\|\s*待补充\s*\|", text):
        return (
            "接口需确认",
            "P1",
            "销量概况/本月目标实际同比数据",
            "请确认 MODULE=3 的销量概况是否应返回本月维度的目标、实际、达成率、达成差额、同比增长率、同比差额；如本月无数据，请确认是否应展示为0或“不适用”。",
            "",
            "季度累计和累计列有值，但本月列缺失，报告表格显示待补充。",
        )

    if chapter == "第三章" and ("产销客户数同比增长待补充" in text or "产销项目数同比增长待补充" in text):
        dimension = "产销客户数同比增长率" if "客户" in text else "产销项目数同比增长率"
        return (
            "业务口径需确认",
            "P1",
            f"{dimension}/同期为0或缺失",
            "请确认产销客户数/产销项目数同比增长率在去年同期为0或缺少同期基数时的展示口径，是否只展示“增加N个”，不展示百分比。",
            "",
            "当前已有增加个数，但百分比无法按常规同比公式计算或未取到同期基数。",
        )

    if chapter == "第三章" and "销量下降金额前三的客户包含：待补充" in text:
        return (
            "接口需确认",
            "P1",
            "客户销量下降金额前三明细",
            "请确认 MODULE=3 是否能返回“销量下降金额前三客户”的客户名称/编码和下降金额；如果没有下降客户，请明确返回空列表，报告展示“无明显下降客户”。",
            "",
            "客均销量下降已触发风险段，但客户下降金额前三明细为空。",
        )

    if chapter == "第三章" and ("**产品：**待补充" in text or "**行业：**待补充" in text):
        return (
            "生成侧需修正",
            "P2",
            "风险/正向产品或行业为空",
            "一般无需客户补接口；除非业务要求必须输出下降/上升维度，请确认空列表时是否展示“无明显变化/无明显下降”。",
            "当没有符合阈值的产品或行业时，生成侧应输出明确的“无明显变化/无明显下降”，不能保留“待补充”。",
            "数据为空列表或无触发项时的文案兜底问题。",
        )

    if chapter == "第五章" and "| 待补充 |" in text:
        return (
            "接口需确认",
            "P1",
            "减值损失影响金额TOP5/截止月末应收金额",
            "请确认 MODULE=5 的“减值损失影响金额 TOP5 客户”是否应为每个客户同时返回截止月末应收金额/应收金额；如果无法返回，请确认该列是否可删除或改为“未提供”。",
            "",
            "减值损失 TOP 客户有减值金额，但 receivable_amount 缺失，表格单元格显示待补充。",
        )

    if chapter == "第六章" and "平均每天花费待补充" in text:
        return (
            "生成侧需修正",
            "P1",
            "出差效率/出差天数为0",
            "无需客户补接口。",
            "出差天数为0时应展示“不适用/0天无日均费用”，不能用“待补充”。",
            "除数为0导致日均费用无法计算，属于生成规则兜底问题。",
        )

    if chapter == "第六章" and "费用排名前三的产品为待补充" in text:
        return (
            "接口需确认",
            "P2",
            "样板样漆费用/产品TOP明细",
            "请确认 MODULE=6 是否能返回样板样漆费用排名前三的产品名称及费用金额；如果没有产品明细，请确认报告是否只展示费用总额和同比，不展示产品TOP。",
            "",
            "样板样漆费用有本月金额，但产品TOP明细为空，报告句子显示待补充。",
        )

    if chapter == "第六章" and text == "待补充":
        return (
            "生成侧需修正",
            "P1",
            "费用分析行动指南",
            "无需客户补接口。",
            "第6章行动指南无触发规则时，应输出明确建议或“本月费用无明显异常，持续关注费用投入产出”。",
            "行动指南模板未命中规则时留下待补充。",
        )

    if chapter == "第七章" and ("相关数值" in text or "待补充" in text):
        return (
            "生成侧需复核",
            "P1",
            "行销行为行动指南兜底话术",
            "先不要反馈客户；需先修正第7章行动指南规则或AI约束。只有确认拜访数据源缺字段后，再转为接口问题。",
            "第7章行动指南应基于已计算的拜访频次、项目/客户拜访占比、达成率生成明确建议，不能输出“相关数值”。",
            "行动指南文案没有完全绑定结构化事实或缺少目标阈值兜底。",
        )

    if chapter == "第八章":
        return (
            "生成侧需复核",
            "P1",
            "AI综合总结兜底话术",
            "先不要反馈客户；需先修正 AI 总结约束后复核。只有确认源数据真实缺字段后，再转为接口问题。",
            "第8章应严格沿用 chapter8_source 的事实，禁止输出“待补充/建议补充/相关数值”等兜底话术。",
            "AI 汇总没有完全受事实源约束，或把0值/空值写成待补充式表达。",
        )

    if chapter == "第五章" and ("相关数值" in text or "待补充" in text):
        return (
            "生成侧需复核",
            "P1",
            "应收行动指南兜底话术",
            "先不要反馈客户；需先核对第5章结构化数据和行动指南生成规则。只有确认源数据真实缺字段后，再转为接口问题。",
            "第5章行动指南应使用已结构化的应收总额、逾期金额、次月到期款等事实，不能输出“相关数值/待补充”。",
            "行动指南文案没有完全绑定结构化事实或缺少空值兜底。",
        )

    return (
        "待人工复核",
        "P2",
        "未归类占位符",
        "请结合明细确认是否需要补接口或调整生成口径。",
        "补充分类规则后复跑审计。",
        "暂未匹配到已知规则。",
    )


def find_chapter5_customer(line: str) -> str:
    if not line.startswith("|") or "待补充" not in line:
        return ""
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    return cells[0] if cells else ""


def enrich_finding(report_dir: Path, finding: Finding, line: str) -> Finding:
    if finding.chapter != "第五章" or finding.field != "减值损失影响金额TOP5/截止月末应收金额":
        return finding
    customer = find_chapter5_customer(line)
    if not customer:
        return finding
    details = ""
    if line.startswith("|"):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 3:
            details = f"{customer} 有当年增加减值损失 {cells[2]}，但截止月末应收金额缺失；"
    evidence = f"{details}{finding.evidence}" if details else finding.evidence
    return Finding(
        finding.category,
        finding.severity,
        finding.chapter,
        finding.person,
        finding.job_id,
        finding.field,
        evidence,
        finding.report_path,
        finding.source_path,
        finding.customer_action,
        finding.internal_action,
    )


def collect_findings(report_dirs: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for report_dir in report_dirs:
        report_path = report_dir / "markdown" / "full_report.md"
        if not report_path.exists():
            continue
        lines = report_path.read_text(encoding="utf-8").splitlines()
        person, job_id, _ = parse_person(report_dir)
        for idx, line in enumerate(lines):
            if not PLACEHOLDER_PATTERN.search(line):
                continue
            chapter = chapter_for_lines(lines, idx)
            category, severity, field, customer_action, internal_action, root_cause = classify(line, chapter)
            evidence = trim_evidence(line)
            if root_cause:
                evidence = f"{evidence}；判断：{root_cause}"
            finding = Finding(
                category=category,
                severity=severity,
                chapter=chapter,
                person=person,
                job_id=job_id,
                field=field,
                evidence=evidence,
                report_path=rel(report_path),
                source_path=source_for(chapter, report_dir),
                customer_action=customer_action,
                internal_action=internal_action,
            )
            findings.append(enrich_finding(report_dir, finding, line))
    return findings


def collect_batch_status() -> dict[str, int]:
    totals = Counter()
    for summary in REPORTS.glob("local_deepseek_*_summary/batch_summary.json"):
        data = load_json(summary)
        if isinstance(data, list):
            totals["total"] += len(data)
            for item in data:
                if isinstance(item, dict):
                    totals[str(item.get("status") or "unknown")] += 1
                    if item.get("complete") is True:
                        totals["complete"] += 1
            continue
        if isinstance(data, dict):
            for key in ("total", "completed", "skipped_completed", "raw_failed", "failed", "incomplete"):
                value = data.get(key)
                if isinstance(value, int):
                    totals[key] += value
    return dict(totals)


def write_csv(findings: list[Finding], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Finding.__dataclass_fields__.keys()))
        writer.writeheader()
        for item in findings:
            writer.writerow(item.__dict__)


def examples(findings: list[Finding], limit: int = 5) -> list[Finding]:
    seen: set[str] = set()
    result: list[Finding] = []
    for item in findings:
        key = item.person
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def write_markdown(findings: list[Finding], report_dirs: list[Path], path: Path) -> None:
    by_key: dict[tuple[str, str, str], list[Finding]] = defaultdict(list)
    for item in findings:
        by_key[(item.category, item.chapter, item.field)].append(item)

    category_counts = Counter(item.category for item in findings)
    affected_people = len({item.person for item in findings})
    status = collect_batch_status()

    customer_keys = [
        key
        for key in by_key
        if key[0] in {"接口需确认", "业务口径需确认"}
    ]
    internal_keys = [
        key
        for key in by_key
        if key[0] not in {"接口需确认", "业务口径需确认"}
    ]
    customer_findings = [item for key in customer_keys for item in by_key[key]]
    internal_findings = [item for key in internal_keys for item in by_key[key]]

    lines: list[str] = []
    lines.append("# 202606 批量报告待补充问题归类")
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(f"- 本次审计正式批次报告 {len(report_dirs)} 份。")
    if status:
        lines.append(
            f"- 批量运行汇总：total={status.get('total', 0)}，completed={status.get('completed', 0)}，"
            f"skipped_completed={status.get('skipped_completed', 0)}，raw_failed={status.get('raw_failed', 0)}。"
        )
    lines.append(f"- 命中“待补充/建议补充/相关数值”的明细 {len(findings)} 条，涉及 {affected_people} 人。")
    lines.append(
        f"- 建议反馈客户确认的接口或业务口径问题 {len(customer_findings)} 条；"
        f"内部生成侧修正/复核项 {len(internal_findings)} 条。"
    )
    lines.append("")
    lines.append("## 需要反馈客户确认的问题")
    lines.append("")
    for key in sorted(customer_keys):
        category, chapter, field = key
        items = by_key[key]
        people = len({item.person for item in items})
        lines.append(f"### {chapter}：{field}")
        lines.append("")
        lines.append(f"- 类型：{category}")
        lines.append(f"- 影响：{len(items)} 条，涉及 {people} 人。")
        lines.append(f"- 需要客户确认：{items[0].customer_action}")
        lines.append("- 样例：")
        for item in examples(items):
            lines.append(f"  - {item.person}：{item.evidence}")
        if len(items) > 5:
            lines.append(f"  - 其余 {len(items) - 5} 条见 CSV 明细。")
        lines.append("")

    lines.append("## 暂不建议先反馈客户的问题")
    lines.append("")
    if internal_keys:
        for key in sorted(internal_keys):
            category, chapter, field = key
            items = by_key[key]
            people = len({item.person for item in items})
            lines.append(f"### {chapter}：{field}")
            lines.append("")
            lines.append(f"- 类型：{category}")
            lines.append(f"- 影响：{len(items)} 条，涉及 {people} 人。")
            lines.append(f"- 内部处理：{items[0].internal_action or '需人工复核后确定处理方式。'}")
            lines.append("- 样例：")
            for item in examples(items, limit=3):
                lines.append(f"  - {item.person}：{item.evidence}")
            if len(items) > 3:
                lines.append(f"  - 其余 {len(items) - 3} 条见 CSV 明细。")
            lines.append("")
    else:
        lines.append("- 无。")
        lines.append("")

    lines.append("## 客户沟通建议")
    lines.append("")
    lines.append("1. 先请客户确认第1章、第5章是否补接口字段；这两类是最像真实缺字段的问题。")
    lines.append("2. 第3章不要简单说接口有问题，应表述为“同比口径需确认”：去年同期为0或缺同期基数时，百分比应如何展示。")
    lines.append("3. 第6章、第8章先由生成侧修正，原则上不要把这些作为客户补数问题抛出去。")
    lines.append("4. 客户确认后，最终报告里不能出现“待补充/建议补充/相关数值”，要替换为明确数值、明确口径文案，或删除不适用列。")
    lines.append("")
    lines.append("## 明细文件")
    lines.append("")
    lines.append(f"- CSV 明细：{path.parent / 'placeholder_audit_full.csv'}")
    lines.append("")
    lines.append("## 分类统计")
    lines.append("")
    for category, count in sorted(category_counts.items()):
        lines.append(f"- {category}：{count} 条")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report_dirs = find_report_dirs()
    findings = collect_findings(report_dirs)
    write_csv(findings, OUTPUT_DIR / "placeholder_audit_full.csv")
    write_markdown(findings, report_dirs, OUTPUT_DIR / "customer_confirmation_summary.md")
    print(f"reports={len(report_dirs)}")
    print(f"findings={len(findings)}")
    print(f"affected_people={len({item.person for item in findings})}")
    print(f"output={OUTPUT_DIR}")


if __name__ == "__main__":
    main()
