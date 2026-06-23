"""二期单人完整报告生成器。

当前阶段先支持单人测试闭环：
- 从统一章节接口并发拉取 1-6 章；
- 保存 raw / cleaned / markdown；
- 从 1-6 章尝试派生第 7 章；
- 从已清洗结果派生第 8 章；
- 输出完整 Markdown、HTML、PDF 和 diagnostics。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from Data import ChapterDataError, check_chapter_response, fetch_chapter_data_batch


CHAPTER_KEYWORDS = {
    1: ("绩效得分与预警", "薪资绩效分析"),
    2: ("利润概况",),
    3: ("销量分析",),
    4: ("毛利率与产品结构",),
    5: ("应收分析", "行销行为"),
    6: ("费用分析",),
}


@dataclass
class FullReportResult:
    report_dir: Path
    markdown_path: Path
    html_path: Path
    pdf_path: Path
    diagnostics_path: Path
    diagnostics: Dict[str, Any]


class FullReportGenerator:
    """生成单个区域经理完整报告。"""

    def __init__(
        self,
        person_config: Dict[str, Any],
        calmonth: str,
        output_root: Path,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: bool = False,
        chapter_concurrent_limit: int = 6,
        report_ai_writer: Optional[Any] = None,
        ai_required: bool = True,
    ) -> None:
        self.person_config = person_config
        self.calmonth = calmonth
        self.output_root = output_root
        self.api_key = api_key
        self.api_url = api_url
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.chapter_concurrent_limit = chapter_concurrent_limit
        self.report_ai_writer = report_ai_writer
        self.ai_required = ai_required
        self.job_id = str(person_config.get("job_id") or "")
        self.sale_name = str(person_config.get("sale_name") or "")

    async def run(self) -> FullReportResult:
        report_dir = self._report_dir()
        raw_dir = report_dir / "raw"
        cleaned_dir = report_dir / "cleaned"
        markdown_dir = report_dir / "markdown"
        html_dir = report_dir / "html"
        pdf_dir = report_dir / "pdf"
        for path in (raw_dir, cleaned_dir, markdown_dir, html_dir, pdf_dir):
            path.mkdir(parents=True, exist_ok=True)

        diagnostics: Dict[str, Any] = {
            "person": self.person_config,
            "calmonth": self.calmonth,
            "chapters": {},
            "derived": {},
            "status": "running",
        }

        raw_responses = await self._fetch_raw_chapters()
        self._save_json(raw_dir / "all_raw_chapters.json", raw_responses)
        for module, response in raw_responses.items():
            self._save_json(raw_dir / f"module_{module}.json", response)

        chapter_markdowns, cleaned_by_chapter = self._build_base_chapters(raw_responses, cleaned_dir, markdown_dir, diagnostics)

        chapter7_source, chapter7_diagnostics = derive_chapter7_source(
            raw_responses=raw_responses,
            person_config=self.person_config,
            calmonth=self.calmonth,
        )
        diagnostics["derived"]["chapter7"] = chapter7_diagnostics
        self._save_json(cleaned_dir / "chapter7_source.json", chapter7_source)

        try:
            from ReportGenerator.chapter7_generator import format_chapter7_data

            chapter7_markdown, chapter7_stats = format_chapter7_data(chapter7_source, period=self.calmonth)
            chapter_markdowns[7] = chapter7_markdown
            cleaned_by_chapter[7] = chapter7_stats.get("cleaned_data", {})
            self._save_json(cleaned_dir / "chapter7_derived.json", cleaned_by_chapter[7])
            (markdown_dir / "chapter7.md").write_text(chapter7_markdown, encoding="utf-8")
            diagnostics["chapters"]["7"] = {"status": "ok", "source": "derived", "warnings": chapter7_stats.get("warnings", [])}
        except Exception as e:
            chapter_markdowns[7] = _fallback_chapter_markdown("七、行销行为", f"第七章派生失败: {e}")
            diagnostics["chapters"]["7"] = {"status": "failed", "source": "derived", "error": str(e)}
            (markdown_dir / "chapter7.md").write_text(chapter_markdowns[7], encoding="utf-8")

        from ReportGenerator.chapter8_source_builder import build_chapter8_source

        chapter8_source = build_chapter8_source(
            cleaned_by_chapter=cleaned_by_chapter,
            person_config=self.person_config,
            calmonth=self.calmonth,
        )
        self._save_json(cleaned_dir / "chapter8_source.json", chapter8_source)

        try:
            from ReportGenerator.chapter8_generator import format_chapter8_data

            chapter8_markdown, chapter8_stats = format_chapter8_data(chapter8_source, period=self.calmonth)
            chapter_markdowns[8] = chapter8_markdown
            cleaned_by_chapter[8] = chapter8_stats.get("cleaned_data", {})
            self._save_json(cleaned_dir / "chapter8_derived.json", cleaned_by_chapter[8])
            (markdown_dir / "chapter8.md").write_text(chapter8_markdown, encoding="utf-8")
            from ReportGenerator.chapter8_renderer import save_final_html as save_chapter8_html
            from ReportGenerator.chapter8_renderer import save_final_pdf as save_chapter8_pdf

            chapter8_html_path = save_chapter8_html(chapter8_markdown, html_dir / "chapter8.html")
            chapter8_pdf_path = save_chapter8_pdf(chapter8_markdown, pdf_dir / "chapter8.pdf")
            diagnostics["chapters"]["8"] = {
                "status": "ok",
                "source": "derived_from_chapters_1_to_7",
                "summary_source": chapter8_stats.get("行动指南来源", "规则"),
                "warnings": chapter8_stats.get("warnings", []),
                "html": str(chapter8_html_path.resolve()),
                "pdf": str(chapter8_pdf_path.resolve()),
            }
            diagnostics["derived"]["chapter8"] = {"status": "ok"}
        except Exception as e:
            chapter_markdowns[8] = _fallback_chapter_markdown("八、总结", f"第八章派生失败: {e}")
            diagnostics["chapters"]["8"] = {"status": "failed", "source": "derived", "error": str(e)}
            diagnostics["derived"]["chapter8"] = {"status": "failed", "error": str(e)}
            (markdown_dir / "chapter8.md").write_text(chapter_markdowns[8], encoding="utf-8")

        try:
            await self._apply_ai_narratives(
                raw_responses=raw_responses,
                chapter7_source=chapter7_source,
                chapter8_source=chapter8_source,
                chapter_markdowns=chapter_markdowns,
                cleaned_by_chapter=cleaned_by_chapter,
                report_dir=report_dir,
                diagnostics=diagnostics,
            )
        except Exception as e:
            diagnostics["status"] = "ai_failed"
            diagnostics["ai"] = {"status": "failed", "error": str(e)}
            diagnostics_path = report_dir / "diagnostics.json"
            self._save_json(diagnostics_path, diagnostics)
            if self.ai_required:
                raise

        full_markdown = self._merge_markdown(chapter_markdowns)
        markdown_path = markdown_dir / "full_report.md"
        markdown_path.write_text(full_markdown, encoding="utf-8")

        from ReportGenerator.full_report_renderer import save_full_html, save_full_pdf

        title = f"{self.sale_name or self.job_id}{self.calmonth}经营分析报告"
        html_path = save_full_html(full_markdown, html_dir / "full_report.html", title=title)
        pdf_path = save_full_pdf(full_markdown, pdf_dir / "full_report.pdf", title=title)

        diagnostics["status"] = "completed"
        diagnostics["outputs"] = {
            "markdown": str(markdown_path.resolve()),
            "html": str(html_path.resolve()),
            "pdf": str(pdf_path.resolve()),
        }
        diagnostics_path = report_dir / "diagnostics.json"
        self._save_json(diagnostics_path, diagnostics)

        return FullReportResult(
            report_dir=report_dir,
            markdown_path=markdown_path,
            html_path=html_path,
            pdf_path=pdf_path,
            diagnostics_path=diagnostics_path,
            diagnostics=diagnostics,
        )

    async def _apply_ai_narratives(
        self,
        raw_responses: Dict[int, Dict[str, Any]],
        chapter7_source: Dict[str, Any],
        chapter8_source: Dict[str, Any],
        chapter_markdowns: Dict[int, str],
        cleaned_by_chapter: Dict[int, Dict[str, Any]],
        report_dir: Path,
        diagnostics: Dict[str, Any],
    ) -> None:
        """一次模型调用生成并回填第3/4/5/7章行动指南和第8章总结。"""
        if not self.ai_required and self.report_ai_writer is None:
            diagnostics["ai"] = {"status": "disabled"}
            return

        from ReportAI import ReportAIWriter
        from ReportAI.fact_pack import build_fact_pack
        from ReportGenerator.chapter5_generator import (
            build_chapter5_action_context,
            infer_chapter5_omit,
            normalize_chapter5_data,
        )
        from ReportGenerator.chapter7_generator import build_chapter7_action_context, normalize_chapter7_data
        from ReportGenerator.chapter8_generator import build_chapter8_action_context, normalize_chapter8_data

        chapter4_cleaned = cleaned_by_chapter.get(4, {})
        chapter4_context = {
            "metric_evidence": [
                {k: v for k, v in item.items() if k != "原始记录"}
                for item in chapter4_cleaned.get("metric_evidence", [])
                if isinstance(item, dict)
            ],
            "missing_fields": chapter4_cleaned.get("missing_fields", []),
            "warnings": chapter4_cleaned.get("warnings", []),
        }
        chapter5_data = normalize_chapter5_data(self._with_person_metadata(raw_responses.get(5, {})), period=self.calmonth)
        chapter5_context = build_chapter5_action_context(chapter5_data, infer_chapter5_omit(chapter5_data))
        chapter8_data = chapter8_source.get("data", {}) if isinstance(chapter8_source, dict) else {}
        dimension_summary = chapter8_data.get("dimension_summary", {}) if isinstance(chapter8_data, dict) else {}
        receivable_summary = dimension_summary.get("应收", {}) if isinstance(dimension_summary, dict) else {}
        chapter5_context["逾期应收合计"] = {
            "value": receivable_summary.get("overdue_amount") if isinstance(receivable_summary, dict) else None,
            "unit": "万元",
        }
        chapter7_context = build_chapter7_action_context(normalize_chapter7_data(chapter7_source, period=self.calmonth))
        chapter8_context = build_chapter8_action_context(normalize_chapter8_data(chapter8_source, period=self.calmonth))
        chapter3_facts = "\n".join(
            line for line in chapter_markdowns.get(3, "").splitlines()
            if not line.strip().startswith("* 行动指南：")
        )
        section_contexts = {
            "chapter3": {"deterministic_report_without_action_guide": chapter3_facts},
            "chapter4": chapter4_context,
            "chapter5": chapter5_context,
            "chapter7": chapter7_context,
            "chapter8": chapter8_context,
        }
        fact_pack = build_fact_pack(section_contexts)
        writer = self.report_ai_writer or ReportAIWriter.from_settings()
        bundle = await writer.generate(fact_pack)

        from ReportGenerator.chapter3_generator import format_chapter3_data
        from ReportGenerator.chapter4_generator import format_chapter4_data
        from ReportGenerator.chapter5_generator import format_chapter5_data
        from ReportGenerator.chapter7_generator import format_chapter7_data
        from ReportGenerator.chapter8_generator import format_chapter8_data

        chapter_markdowns[3], _ = format_chapter3_data(
            self._with_person_metadata(raw_responses.get(3, {})),
            period=self.calmonth,
            action_guide_text=bundle.chapter3_action.text,
        )
        chapter_markdowns[4], _ = format_chapter4_data(
            self._with_person_metadata(raw_responses.get(4, {})),
            period=self.calmonth,
            action_guide_actions={
                "structure_action": bundle.chapter4_structure_action.text,
                "price_action": bundle.chapter4_price_action.text,
            },
        )
        chapter_markdowns[5], _ = format_chapter5_data(
            self._with_person_metadata(raw_responses.get(5, {})),
            period=self.calmonth,
            action_guide_text=bundle.chapter5_action.text,
        )
        chapter_markdowns[7], _ = format_chapter7_data(
            chapter7_source,
            period=self.calmonth,
            action_guide_text=bundle.chapter7_action.text,
        )
        chapter_markdowns[8], _ = format_chapter8_data(
            chapter8_source,
            period=self.calmonth,
            advantage_text=bundle.chapter8_advantage.text,
            weakness_text=bundle.chapter8_weakness.text,
            strategy_lines=[f"{item.dimension}：{item.text}" for item in bundle.chapter8_strategies],
        )

        markdown_dir = report_dir / "markdown"
        for module in (3, 4, 5, 7, 8):
            (markdown_dir / f"chapter{module}.md").write_text(chapter_markdowns[module], encoding="utf-8")
            diagnostics["chapters"].setdefault(str(module), {})["ai_source"] = "AI"
        diagnostics["chapters"]["8"]["summary_source"] = "AI"
        diagnostics["ai"] = {"status": "ok", **bundle.manifest, "sections": {
            "chapter3": "AI", "chapter4": "AI", "chapter5": "AI", "chapter7": "AI", "chapter8": "AI"
        }}
        ai_dir = report_dir / "ai"
        self._save_json(ai_dir / "narrative_bundle.json", bundle.to_dict())
        self._save_json(ai_dir / "manifest.json", diagnostics["ai"])

        from ReportGenerator.chapter8_renderer import save_final_html as save_chapter8_html
        from ReportGenerator.chapter8_renderer import save_final_pdf as save_chapter8_pdf

        save_chapter8_html(chapter_markdowns[8], report_dir / "html" / "chapter8.html")
        save_chapter8_pdf(chapter_markdowns[8], report_dir / "pdf" / "chapter8.pdf")

    async def _fetch_raw_chapters(self) -> Dict[int, Dict[str, Any]]:
        requests = [
            {"job_id": self.job_id, "time": self.calmonth, "module": module}
            for module in range(1, 7)
        ]
        return await fetch_chapter_data_batch(
            requests=requests,
            concurrent_limit=self.chapter_concurrent_limit,
            api_key=self.api_key,
            api_url=self.api_url,
            timeout=self.timeout,
            verify_ssl=self.verify_ssl,
        )

    def _build_base_chapters(
        self,
        raw_responses: Dict[int, Dict[str, Any]],
        cleaned_dir: Path,
        markdown_dir: Path,
        diagnostics: Dict[str, Any],
    ) -> Tuple[Dict[int, str], Dict[int, Dict[str, Any]]]:
        chapter_markdowns: Dict[int, str] = {}
        cleaned_by_chapter: Dict[int, Dict[str, Any]] = {}

        for module in range(1, 7):
            response = self._with_person_metadata(raw_responses.get(module, {}))
            has_error, message = check_chapter_response(
                response,
                module=module,
                expected_chapter_keywords=CHAPTER_KEYWORDS.get(module),
                required_metric_data_keys=(),
            )
            subject = response.get("data") if isinstance(response, dict) else {}
            chapter_name = subject.get("章节名称", f"第{module}章") if isinstance(subject, dict) else f"第{module}章"
            diagnostics["chapters"][str(module)] = {
                "status": "raw_error" if has_error else "raw_ok",
                "chapter_name": chapter_name,
                "raw_message": message,
                "source": "api",
            }

            try:
                markdown, stats = self._format_base_chapter(module, response)
                chapter_markdowns[module] = markdown
                cleaned = stats.get("cleaned_data", stats)
                if isinstance(cleaned, dict):
                    cleaned_by_chapter[module] = cleaned
                else:
                    cleaned_by_chapter[module] = {"stats": cleaned}
                self._save_json(cleaned_dir / f"chapter{module}_cleaned.json", cleaned_by_chapter[module])
                (markdown_dir / f"chapter{module}.md").write_text(markdown, encoding="utf-8")
                diagnostics["chapters"][str(module)].update({
                    "status": "ok",
                    "stats": {k: v for k, v in stats.items() if k not in {"cleaned_data", "action_context"}},
                })
            except Exception as e:
                title = str(chapter_name or f"第{module}章")
                chapter_markdowns[module] = _fallback_chapter_markdown(title, f"本章暂不可生成: {e}")
                (markdown_dir / f"chapter{module}.md").write_text(chapter_markdowns[module], encoding="utf-8")
                diagnostics["chapters"][str(module)].update({"status": "failed", "error": str(e)})

        return chapter_markdowns, cleaned_by_chapter

    def _format_base_chapter(self, module: int, response: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        if module == 1:
            from ReportGenerator.chapter1_generator import format_chapter1_data

            return format_chapter1_data(response, period=self.calmonth)

        if module == 2:
            from ReportGenerator.chapter2_renderer import build_final_markdown

            rows = _chapter_rows_from_response(response)
            markdown = build_final_markdown(rows, period=self.calmonth)
            return markdown, {"有效指标数": len(rows), "cleaned_data": {"rows": rows}}

        if module == 3:
            from ReportGenerator.chapter3_generator import format_chapter3_data

            markdown, stats = format_chapter3_data(response, period=self.calmonth)
            rows = _chapter_rows_from_response(response)
            stats["cleaned_data"] = {"rows": rows, "stats": {k: v for k, v in stats.items() if k != "cleaned_data"}}
            return markdown, stats

        if module == 4:
            from ReportGenerator.chapter4_generator import format_chapter4_data

            return format_chapter4_data(response, period=self.calmonth)

        if module == 5:
            from ReportGenerator.chapter5_generator import format_chapter5_data

            return format_chapter5_data(response, period=self.calmonth)

        if module == 6:
            from ReportGenerator.chapter6_generator import format_chapter6_data

            return format_chapter6_data(response, period=self.calmonth)

        raise ChapterDataError(f"暂不支持第{module}章")

    def _with_person_metadata(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict) or not isinstance(response.get("data"), dict):
            return response
        data = dict(response["data"])
        data.setdefault("经营部名称", self.person_config.get("city_operation_department", ""))
        data.setdefault("城市经营部", self.person_config.get("city_operation_department", ""))
        data.setdefault("区域经理姓名", self.person_config.get("sale_name", ""))
        data.setdefault("区域经理工号", self.person_config.get("job_id", ""))
        data.setdefault("部门名称", self.person_config.get("business_department", ""))
        copied = dict(response)
        copied["data"] = data
        return copied

    def _merge_markdown(self, chapters: Dict[int, str]) -> str:
        header = [
            f"# {self.person_config.get('city_operation_department', '')}{self.sale_name or self.job_id}{self.calmonth}经营分析报告".strip(),
            "",
            f"工号：{self.job_id}",
            f"姓名：{self.sale_name or '—'}",
            f"组织：{self.person_config.get('business_department', '')} / {self.person_config.get('region', '')} / {self.person_config.get('province', '')} / {self.person_config.get('city_operation_department', '')}",
            "",
        ]
        body = []
        for module in range(1, 9):
            content = chapters.get(module) or _fallback_chapter_markdown(f"第{module}章", "本章未生成。")
            body.append(content.strip())
        return "\n".join(header + ["\n\n".join(body), ""]) 

    def _report_dir(self) -> Path:
        safe_name = self.sale_name or "unknown"
        return self.output_root / self.calmonth / f"{self.job_id}_{safe_name}"

    @staticmethod
    def _save_json(path: Path, data: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def derive_chapter7_source(
    raw_responses: Dict[int, Dict[str, Any]],
    person_config: Dict[str, Any],
    calmonth: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """从 1-6 章原始指标里尝试提取第七章行销行为所需字段。"""
    rows = list(_iter_metric_rows(raw_responses))
    diagnostics = {"status": "pending", "matched_fields": {}, "missing_fields": []}

    total = _find_visit_metric(rows, include=("拜访",), exclude=("项目", "占比", "客户"))
    project = _find_visit_metric(rows, include=("项目", "拜访"), exclude=("占比",))
    project_ratio = _find_metric_value(rows, include=("项目", "拜访", "占比"), exclude=())
    customer_ratio = _find_metric_value(rows, include=("客户", "拜访", "占比"), exclude=())

    for key, result in {
        "拜访总频次": total,
        "项目拜访频次": project,
        "项目拜访占比": project_ratio,
        "客户拜访占比": customer_ratio,
    }.items():
        if result:
            diagnostics["matched_fields"][key] = result.get("source")
        else:
            diagnostics["missing_fields"].append(key)

    diagnostics["status"] = "ok" if not diagnostics["missing_fields"] else "partial"
    if len(diagnostics["missing_fields"]) == 4:
        diagnostics["status"] = "unavailable"

    data = {
        "月份": calmonth,
        "区域经理工号": person_config.get("job_id", ""),
        "区域经理姓名": person_config.get("sale_name", ""),
        "部门名称": person_config.get("city_operation_department", ""),
        "章节名称": "七、行销行为",
        "visit": {
            "total": _metric_payload(total),
            "project": _metric_payload(project),
        },
        "time_allocation": {
            "项目拜访占比": project_ratio.get("value") if project_ratio else None,
            "客户拜访占比": customer_ratio.get("value") if customer_ratio else None,
        },
    }
    return {"code": 1, "message": "derived_from_chapter_1_to_6", "data": data}, diagnostics


def _fallback_chapter_markdown(title: str, message: str) -> str:
    title = title if title.startswith(("#", "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、")) else title
    return f"## {title}\n\n{message}\n"


def _chapter_rows_from_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = response.get("data") if isinstance(response, dict) else None
    if isinstance(data, dict) and isinstance(data.get("章节数据"), list):
        return data["章节数据"]
    return []


def _iter_metric_rows(raw_responses: Dict[int, Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for module, response in raw_responses.items():
        data = response.get("data") if isinstance(response, dict) else None
        rows = data.get("章节数据") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                yield {"module": module, "chapter_name": data.get("章节名称", ""), **row}


def _find_visit_metric(rows: Iterable[Dict[str, Any]], include: Tuple[str, ...], exclude: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
    for row in rows:
        text = f"{row.get('指标名称', '')} {row.get('指标路径', '')}"
        if all(word in text for word in include) and not any(word in text for word in exclude):
            metric = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
            return {
                "actual": _to_float(metric.get("实际值")),
                "target": _to_float(metric.get("目标值")),
                "achievement_rate": _to_float(metric.get("达成率")),
                "deduction_score": _to_float(metric.get("扣分值")),
                "source": _source_desc(row),
            }
    return None


def _find_metric_value(rows: Iterable[Dict[str, Any]], include: Tuple[str, ...], exclude: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
    for row in rows:
        text = f"{row.get('指标名称', '')} {row.get('指标路径', '')}"
        if all(word in text for word in include) and not any(word in text for word in exclude):
            metric = row.get("指标数据") if isinstance(row.get("指标数据"), dict) else {}
            return {"value": _to_float(metric.get("实际值")), "source": _source_desc(row)}
    return None


def _metric_payload(metric: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not metric:
        return {}
    return {
        "实际值": metric.get("actual"),
        "目标值": metric.get("target"),
        "达成率": metric.get("achievement_rate"),
        "扣分值": metric.get("deduction_score"),
    }


def _source_desc(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "module": row.get("module"),
        "chapter_name": row.get("chapter_name"),
        "指标名称": row.get("指标名称", ""),
        "指标路径": row.get("指标路径", ""),
    }


def _rank_display(data: Dict[str, Any], scope: str) -> str:
    rank = data.get(f"{scope}_rank")
    total = data.get(f"{scope}_total")
    if rank and total:
        return f"{rank}/{total}"
    return ""


def _nested_value(data: Any, key: str) -> Optional[Any]:
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    if isinstance(value, dict):
        return value.get("value") or value.get("实际值")
    return value


def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None
