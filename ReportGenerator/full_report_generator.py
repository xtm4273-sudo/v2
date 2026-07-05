"""二期单人完整报告生成器。

当前阶段先支持单人测试闭环：
- 从统一章节接口并发拉取 1-7 章；
- 保存 raw / cleaned / markdown；
- 从 1-7 章清洗结果派生第 8 章；
- 输出完整 Markdown、HTML、PDF 和 diagnostics。
"""
from __future__ import annotations

import asyncio
import json
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from Data import ChapterDataError, check_chapter_response, fetch_chapter_data_batch
from ReportGenerator.display_policy import build_delivery_display_audit, normalize_delivery_display
from ReportGenerator.report_period import default_report_period


CHAPTER_KEYWORDS = {
    1: ("绩效得分与预警", "薪资绩效分析"),
    2: ("利润概况",),
    3: ("销量分析",),
    4: ("毛利率与产品结构",),
    5: ("应收分析", "行销行为"),
    6: ("费用分析",),
    7: ("行销行为",),
}

SOURCE_CHAPTERS = range(1, 8)


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
        report_period: Optional[str] = None,
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
        self.report_period = report_period or default_report_period(calmonth)
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
        diagnostics_path = report_dir / "diagnostics.json"

        diagnostics: Dict[str, Any] = {
            "person": self.person_config,
            "calmonth": self.calmonth,
            "report_period": self.report_period,
            "chapters": {},
            "derived": {},
            "status": "running",
        }
        self._save_json(diagnostics_path, diagnostics)

        try:
            try:
                raw_responses = await self._fetch_raw_chapters()
            except Exception as e:
                failure = _failure_from_exception(e, "fetch_raw_chapters")
                _apply_failure(diagnostics, failure, status="raw_fetch_failed")
                self._save_json(diagnostics_path, diagnostics)
                raise

            self._save_json(raw_dir / "all_raw_chapters.json", raw_responses)
            for module, response in raw_responses.items():
                self._save_json(raw_dir / f"module_{module}.json", response)

            chapter_markdowns, cleaned_by_chapter = self._build_base_chapters(
                raw_responses,
                cleaned_dir,
                markdown_dir,
                diagnostics,
            )

            from ReportGenerator.chapter8_source_builder import build_chapter8_source

            try:
                chapter8_source = build_chapter8_source(
                    cleaned_by_chapter=cleaned_by_chapter,
                    person_config=self.person_config,
                    calmonth=self.report_period,
                )
                self._save_json(cleaned_dir / "chapter8_source.json", chapter8_source)
            except Exception as e:
                failure = _failure_from_exception(
                    e,
                    "build_chapter8_source",
                    context={"source_chapters": sorted(cleaned_by_chapter.keys())},
                )
                diagnostics["derived"]["chapter8"] = {
                    "status": "failed",
                    "error": str(e),
                    **_failure_summary_fields(failure),
                    "failure": failure,
                }
                _apply_failure(diagnostics, failure, status="chapter8_source_failed")
                self._save_json(diagnostics_path, diagnostics)
                raise

            try:
                from ReportGenerator.chapter8_generator import format_chapter8_data

                chapter8_markdown, chapter8_stats = format_chapter8_data(chapter8_source, period=self.report_period)
                chapter_markdowns[8] = chapter8_markdown
                cleaned_by_chapter[8] = chapter8_stats.get("cleaned_data", {})
                self._save_json(cleaned_dir / "chapter8_derived.json", cleaned_by_chapter[8])
                (markdown_dir / "chapter8.md").write_text(chapter8_markdown, encoding="utf-8")
                from ReportGenerator.chapter8_renderer import save_final_html as save_chapter8_html

                chapter8_html_path = save_chapter8_html(chapter8_markdown, html_dir / "chapter8.html")
                diagnostics["chapters"]["8"] = {
                    "status": "ok",
                    "source": "derived_from_chapters_1_to_7",
                    "summary_source": chapter8_stats.get("行动指南来源", "规则"),
                    "warnings": chapter8_stats.get("warnings", []),
                    "html": str(chapter8_html_path.resolve()),
                }
                diagnostics["derived"]["chapter8"] = {"status": "ok"}
            except Exception as e:
                failure = _failure_from_exception(e, "derive_chapter8")
                chapter_markdowns[8] = _fallback_chapter_markdown("八、总结", f"第八章派生失败: {e}")
                diagnostics["chapters"]["8"] = {
                    "status": "failed",
                    "source": "derived",
                    "error": str(e),
                    **_failure_summary_fields(failure),
                    "failure": failure,
                }
                diagnostics["derived"]["chapter8"] = {
                    "status": "failed",
                    "error": str(e),
                    **_failure_summary_fields(failure),
                    "failure": failure,
                }
                (markdown_dir / "chapter8.md").write_text(chapter_markdowns[8], encoding="utf-8")

            try:
                await self._apply_ai_narratives(
                    raw_responses=raw_responses,
                    chapter7_source=self._with_person_metadata(raw_responses.get(7, {})),
                    chapter8_source=chapter8_source,
                    chapter_markdowns=chapter_markdowns,
                    cleaned_by_chapter=cleaned_by_chapter,
                    report_dir=report_dir,
                    diagnostics=diagnostics,
                )
            except Exception as e:
                failure = _failure_from_exception(e, "apply_ai_narratives", failure_type="ai_error")
                diagnostics["ai"] = {
                    "status": "failed",
                    "required": self.ai_required,
                    "error": str(e),
                    **_failure_summary_fields(failure),
                    "failure": failure,
                }
                if self.ai_required:
                    _apply_failure(diagnostics, failure, status="ai_failed")
                else:
                    diagnostics.setdefault("warnings", []).append(failure["failure_reason"])
                self._save_json(diagnostics_path, diagnostics)
                if self.ai_required:
                    raise

            self._apply_delivery_display_policy(chapter_markdowns, report_dir, diagnostics)
            full_markdown = normalize_delivery_display(self._merge_markdown(chapter_markdowns))
            from ReportGenerator.report_period import audit_report_month_labels

            period_issues = audit_report_month_labels(full_markdown, self.report_period)
            diagnostics["period_audit"] = {
                "status": "failed" if period_issues else "ok",
                "report_period": self.report_period,
                "issues": period_issues,
            }
            if period_issues:
                reason = "报告月份审计失败：" + "；".join(period_issues)
                failure = _failure_from_message(
                    "period_error",
                    "period_audit",
                    reason,
                    context={"issues": period_issues, "report_period": self.report_period},
                )
                _apply_failure(diagnostics, failure, status="period_audit_failed")
                self._save_json(diagnostics_path, diagnostics)
                raise ChapterDataError(reason)

            markdown_path = markdown_dir / "full_report.md"
            markdown_path.write_text(full_markdown, encoding="utf-8")

            from ReportGenerator.full_report_renderer import save_full_html, save_full_pdf
            from ReportGenerator.report_period import display_period_label

            title = f"{self.sale_name or self.job_id}{display_period_label(self.report_period)}经营分析报告"
            try:
                html_path = save_full_html(full_markdown, html_dir / "full_report.html", title=title)
                pdf_path = save_full_pdf(
                    full_markdown,
                    delivery_pdf_path(pdf_dir, self.sale_name or self.job_id),
                    title=title,
                )
                cleanup_extra_pdfs(pdf_dir, keep_pdf=pdf_path)
            except Exception as e:
                failure = _failure_from_exception(
                    e,
                    "render_full_report",
                    failure_type="render_error",
                    context={"title": title},
                )
                _apply_failure(diagnostics, failure, status="render_failed")
                self._save_json(diagnostics_path, diagnostics)
                raise

            diagnostics["status"] = "completed"
            diagnostics["outputs"] = {
                "markdown": str(markdown_path.resolve()),
                "html": str(html_path.resolve()),
                "pdf": str(pdf_path.resolve()),
            }
            self._save_json(diagnostics_path, diagnostics)

            return FullReportResult(
                report_dir=report_dir,
                markdown_path=markdown_path,
                html_path=html_path,
                pdf_path=pdf_path,
                diagnostics_path=diagnostics_path,
                diagnostics=diagnostics,
            )
        except Exception as e:
            if "failure" not in diagnostics:
                status = diagnostics.get("status")
                failure = _failure_from_exception(e, "run")
                _apply_failure(diagnostics, failure, status="failed" if status == "running" else status)
                self._save_json(diagnostics_path, diagnostics)
            raise

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
        chapter5_data = normalize_chapter5_data(self._with_person_metadata(raw_responses.get(5, {})), period=self.report_period)
        chapter5_context = build_chapter5_action_context(chapter5_data, infer_chapter5_omit(chapter5_data))
        chapter8_data = chapter8_source.get("data", {}) if isinstance(chapter8_source, dict) else {}
        dimension_summary = chapter8_data.get("dimension_summary", {}) if isinstance(chapter8_data, dict) else {}
        receivable_summary = dimension_summary.get("应收", {}) if isinstance(dimension_summary, dict) else {}
        chapter5_context["逾期应收合计"] = {
            "value": receivable_summary.get("overdue_amount") if isinstance(receivable_summary, dict) else None,
            "unit": "万元",
        }
        chapter7_context = build_chapter7_action_context(normalize_chapter7_data(chapter7_source, period=self.report_period))
        chapter8_context = build_chapter8_action_context(normalize_chapter8_data(chapter8_source, period=self.report_period))
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
        from ReportGenerator.chapter4_generator import extract_chapter2_gross_margin_rate, format_chapter4_data
        from ReportGenerator.chapter5_generator import format_chapter5_data
        from ReportGenerator.chapter7_generator import format_chapter7_data
        from ReportGenerator.chapter8_generator import format_chapter8_data

        chapter_markdowns[3], _ = format_chapter3_data(
            self._with_person_metadata(raw_responses.get(3, {})),
            period=self.report_period,
            action_guide_text=bundle.chapter3_action.text,
        )
        chapter_markdowns[4], _ = format_chapter4_data(
            self._with_person_metadata(raw_responses.get(4, {})),
            period=self.report_period,
            source_period=self.calmonth,
            gross_margin_rate=extract_chapter2_gross_margin_rate(raw_responses.get(2, {})),
        )
        chapter_markdowns[5], _ = format_chapter5_data(
            self._with_person_metadata(raw_responses.get(5, {})),
            period=self.report_period,
            action_guide_text=bundle.chapter5_action.text,
        )
        chapter_markdowns[7], _ = format_chapter7_data(
            chapter7_source,
            period=self.report_period,
            action_guide_text=bundle.chapter7_action.text,
        )
        chapter8_strategy_lines = _chapter8_strategy_lines_with_chapter3_product_rule(
            [f"{item.dimension}：{item.text}" for item in bundle.chapter8_strategies],
            self._with_person_metadata(raw_responses.get(3, {})),
        )
        chapter_markdowns[8], _ = format_chapter8_data(
            chapter8_source,
            period=self.report_period,
            advantage_text=bundle.chapter8_advantage.text,
            weakness_text=bundle.chapter8_weakness.text,
            strategy_lines=chapter8_strategy_lines,
        )

        markdown_dir = report_dir / "markdown"
        for module in (3, 4, 5, 7, 8):
            (markdown_dir / f"chapter{module}.md").write_text(chapter_markdowns[module], encoding="utf-8")
            diagnostics["chapters"].setdefault(str(module), {})["ai_source"] = (
                "规则模板" if module == 4 else "AI"
            )
        diagnostics["chapters"]["8"]["summary_source"] = "AI"
        diagnostics["ai"] = {"status": "ok", **bundle.manifest, "sections": {
            "chapter3": "AI", "chapter4": "规则模板", "chapter5": "AI", "chapter7": "AI", "chapter8": "AI"
        }}
        ai_dir = report_dir / "ai"
        self._save_json(ai_dir / "narrative_bundle.json", bundle.to_dict())
        self._save_json(ai_dir / "manifest.json", diagnostics["ai"])

        from ReportGenerator.chapter8_renderer import save_final_html as save_chapter8_html

        save_chapter8_html(chapter_markdowns[8], report_dir / "html" / "chapter8.html")

    async def _fetch_raw_chapters(self) -> Dict[int, Dict[str, Any]]:
        requests = [
            {"job_id": self.job_id, "time": self.calmonth, "module": module}
            for module in SOURCE_CHAPTERS
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

        for module in SOURCE_CHAPTERS:
            response = self._with_person_metadata(raw_responses.get(module, {}))
            if module == 1:
                response = self._with_ranking_population_totals(response)
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
            if has_error or response.get("code") not in (None, 1, "1"):
                raw_failure = _failure_from_response(
                    response,
                    module=module,
                    stage="validate_raw_chapter",
                    raw_message=message,
                )
                diagnostics["chapters"][str(module)].update({
                    **_failure_summary_fields(raw_failure),
                    "raw_failure": raw_failure,
                })

            try:
                if module == 4:
                    from ReportGenerator.chapter4_generator import (
                        extract_chapter2_gross_margin_rate,
                        format_chapter4_data,
                    )

                    markdown, stats = format_chapter4_data(
                        response,
                        period=self.report_period,
                        source_period=self.calmonth,
                        gross_margin_rate=extract_chapter2_gross_margin_rate(raw_responses.get(2, {})),
                    )
                else:
                    if module == 6:
                        from ReportGenerator.chapter6_generator import format_chapter6_data

                        markdown, stats = format_chapter6_data(
                            response,
                            period=self.report_period,
                            context_raw_data=raw_responses,
                        )
                    else:
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
                failure = _failure_from_exception(
                    e,
                    f"build_chapter_{module}",
                    context={"module": module, "chapter_name": chapter_name},
                )
                title = str(chapter_name or f"第{module}章")
                chapter_markdowns[module] = _fallback_chapter_markdown(title, f"本章暂不可生成: {e}")
                (markdown_dir / f"chapter{module}.md").write_text(chapter_markdowns[module], encoding="utf-8")
                diagnostics["chapters"][str(module)].update({
                    "status": "failed",
                    "error": str(e),
                    **_failure_summary_fields(failure),
                    "failure": failure,
                })

        return chapter_markdowns, cleaned_by_chapter

    def _apply_delivery_display_policy(
        self,
        chapter_markdowns: Dict[int, str],
        report_dir: Path,
        diagnostics: Dict[str, Any],
    ) -> None:
        """Apply customer-facing missing-data rules while keeping raw diagnostics."""
        markdown_dir = report_dir / "markdown"
        audits: Dict[str, Any] = {}
        changed_modules: List[int] = []

        for module, markdown in list(chapter_markdowns.items()):
            normalized = normalize_delivery_display(markdown)
            audit = build_delivery_display_audit(markdown, normalized)
            audits[str(module)] = audit
            if normalized != markdown:
                changed_modules.append(module)
                chapter_markdowns[module] = normalized
            (markdown_dir / f"chapter{module}.md").write_text(chapter_markdowns[module], encoding="utf-8")

        diagnostics["delivery_display_policy"] = {
            "status": "ok" if all(item.get("status") == "ok" for item in audits.values()) else "needs_review",
            "changed_modules": changed_modules,
            "visible_missing_before": sum(item.get("visible_missing_before", 0) for item in audits.values()),
            "visible_missing_after": sum(item.get("visible_missing_after", 0) for item in audits.values()),
            "zero_replacements": sum(item.get("zero_replacements", 0) for item in audits.values()),
            "hidden_topn_or_detail": sum(item.get("hidden_topn_or_detail", 0) for item in audits.values()),
            "chapters": audits,
        }

        if 8 in changed_modules:
            from ReportGenerator.chapter8_renderer import save_final_html as save_chapter8_html

            chapter8_html_path = save_chapter8_html(chapter_markdowns[8], report_dir / "html" / "chapter8.html")
            diagnostics.setdefault("chapters", {}).setdefault("8", {}).update({
                "html": str(chapter8_html_path.resolve()),
            })

    def _format_base_chapter(self, module: int, response: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        if module == 1:
            from ReportGenerator.chapter1_generator import format_chapter1_data

            return format_chapter1_data(response, period=self.report_period)

        if module == 2:
            from ReportGenerator.chapter2_generator import build_chapter2_markdown, build_chapter2_stats, normalize_chapter2_data

            data = normalize_chapter2_data(response, period=self.report_period)
            markdown = build_chapter2_markdown(data)
            stats = build_chapter2_stats(data)
            return markdown, stats

        if module == 3:
            from ReportGenerator.chapter3_generator import format_chapter3_data

            markdown, stats = format_chapter3_data(response, period=self.report_period)
            rows = _chapter_rows_from_response(response)
            stats["cleaned_data"] = {"rows": rows, "stats": {k: v for k, v in stats.items() if k != "cleaned_data"}}
            return markdown, stats

        if module == 4:
            from ReportGenerator.chapter4_generator import format_chapter4_data

            return format_chapter4_data(response, period=self.report_period, source_period=self.calmonth)

        if module == 5:
            from ReportGenerator.chapter5_generator import format_chapter5_data

            return format_chapter5_data(response, period=self.report_period)

        if module == 6:
            from ReportGenerator.chapter6_generator import format_chapter6_data

            return format_chapter6_data(response, period=self.report_period)

        if module == 7:
            from ReportGenerator.chapter7_generator import format_chapter7_data

            return format_chapter7_data(response, period=self.report_period)

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

    def _with_ranking_population_totals(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """把人员组织接口统计的排名分母注入第一章排名记录。"""
        if not isinstance(response, dict) or not isinstance(response.get("data"), dict):
            return response
        province_total = self.person_config.get("province_ranking_total")
        business_total = self.person_config.get("business_ranking_total")
        data = dict(response["data"])
        rows = data.get("章节数据")
        if not isinstance(rows, list):
            return response

        enriched_rows = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("指标数据"), dict):
                enriched_rows.append(row)
                continue
            enriched_row = dict(row)
            metric = dict(row["指标数据"])
            if province_total and metric.get("省区排名") not in (None, 0, "0", ""):
                metric["省区总人数"] = province_total
            if business_total and metric.get("部门排名") not in (None, 0, "0", ""):
                metric["部门总人数"] = business_total
            enriched_row["指标数据"] = metric
            enriched_rows.append(enriched_row)

        data["章节数据"] = enriched_rows
        copied = dict(response)
        copied["data"] = data
        return copied

    def _merge_markdown(self, chapters: Dict[int, str]) -> str:
        from ReportGenerator.report_period import display_period_label

        period_label = display_period_label(self.report_period)
        header = [
            f"# {self.person_config.get('city_operation_department', '')}{self.sale_name or self.job_id}{period_label}经营分析报告".strip(),
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


FAILURE_TYPE_LABELS = {
    "configuration_error": "配置问题",
    "interface_error": "接口问题",
    "data_error": "接口数据问题",
    "ai_error": "AI接口/生成问题",
    "render_error": "HTML/PDF渲染问题",
    "period_error": "报告月份/规则审计问题",
    "program_error": "程序异常",
    "unknown_error": "未知问题",
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def delivery_pdf_filename(person_name: str, generated_at: Optional[datetime] = None) -> str:
    date_text = (generated_at or datetime.now()).strftime("%Y%m%d")
    return f"{_safe_filename_part(person_name)}_{date_text}.pdf"


def delivery_pdf_path(
    pdf_dir: Path,
    person_name: str,
    generated_at: Optional[datetime] = None,
) -> Path:
    return Path(pdf_dir) / delivery_pdf_filename(person_name, generated_at)


def cleanup_extra_pdfs(pdf_dir: Path, keep_pdf: Path) -> None:
    keep_resolved = Path(keep_pdf).resolve()
    for candidate in Path(pdf_dir).glob("*.pdf"):
        if candidate.resolve() != keep_resolved and candidate.exists():
            candidate.unlink()


def _safe_filename_part(value: str) -> str:
    invalid_chars = set('<>:"/\\|?*\n\r\t')
    text = "".join("_" if char in invalid_chars or ord(char) < 32 else char for char in str(value or ""))
    text = text.strip(" ._")
    return text or "unknown"


def _failure_type_label(failure_type: str) -> str:
    return FAILURE_TYPE_LABELS.get(failure_type, FAILURE_TYPE_LABELS["unknown_error"])


def _failure_suggestion(failure_type: str) -> str:
    suggestions = {
        "configuration_error": "检查 .env 或命令行参数中的 SKSHU_BI_API_KEY、AI_API_KEY、接口地址配置。",
        "interface_error": "检查 BI 接口/网络连通性、HTTP 状态码、接口返回内容和 raw/module_X.json。",
        "data_error": "检查接口原始数据是否为空、字段结构是否变化，重点查看 raw/module_X.json。",
        "ai_error": "检查 AI_BASE_URL、AI_API_KEY、模型服务连通性和 ai/narrative_bundle.json。",
        "render_error": "检查 HTML/PDF 渲染依赖、Playwright/Chromium 安装和输出目录权限。",
        "period_error": "检查 calmonth 与 report_period 是否传反，或章节文案中是否混入错误月份。",
        "program_error": "查看 traceback 定位代码异常；若 raw 数据正常，优先排查章节清洗/渲染代码。",
    }
    return suggestions.get(failure_type, "查看 failure.traceback 和各阶段上下文继续定位。")


def _classify_exception(exc: BaseException, stage: str) -> str:
    if isinstance(exc, ChapterDataError):
        return "data_error"
    stage_name = stage.lower()
    exc_name = type(exc).__name__.lower()
    message = str(exc).lower()
    if stage_name.startswith("render"):
        return "render_error"
    if stage_name == "period_audit":
        return "period_error"
    if "ai" in stage_name or "openai" in exc_name or "deepseek" in message:
        return "ai_error"
    if any(word in exc_name or word in message for word in ("timeout", "connection", "httperror", "urlerror", "ssl")):
        return "interface_error"
    return "program_error"


def _failure_from_exception(
    exc: BaseException,
    stage: str,
    failure_type: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resolved_type = failure_type or _classify_exception(exc, stage)
    failure: Dict[str, Any] = {
        "failure_type": resolved_type,
        "failure_type_label": _failure_type_label(resolved_type),
        "failure_stage": stage,
        "failure_reason": str(exc),
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "suggestion": _failure_suggestion(resolved_type),
        "occurred_at": _now_iso(),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }
    if context:
        failure["context"] = context
    return failure


def _failure_from_message(
    failure_type: str,
    stage: str,
    reason: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    failure: Dict[str, Any] = {
        "failure_type": failure_type,
        "failure_type_label": _failure_type_label(failure_type),
        "failure_stage": stage,
        "failure_reason": reason,
        "message": reason,
        "suggestion": _failure_suggestion(failure_type),
        "occurred_at": _now_iso(),
    }
    if context:
        failure["context"] = context
    return failure


def _failure_from_response(
    response: Any,
    module: int,
    stage: str,
    raw_message: str,
) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return _failure_from_message(
            "data_error",
            stage,
            raw_message,
            context={"module": module, "response_type": type(response).__name__},
        )

    api_error = response.get("error")
    api_code = response.get("code")
    if response.get("failure_type"):
        failure_type = str(response["failure_type"])
    elif api_error == "missing_api_key":
        failure_type = "configuration_error"
    elif api_error:
        failure_type = "interface_error"
    elif api_code not in (None, 1, "1"):
        failure_type = "interface_error"
    else:
        failure_type = "data_error"

    reason = raw_message
    if api_error and not reason:
        reason = f"第{module}章接口请求失败: {api_error} - {response.get('message', '')}"
    elif api_code not in (None, 1, "1") and not reason:
        reason = f"第{module}章接口返回失败: code={api_code}, message={response.get('message')}"

    context = {
        "module": module,
        "api_error": api_error,
        "api_code": api_code,
        "api_message": response.get("message"),
        "failure_stage_from_api": response.get("failure_stage"),
        "status_code": response.get("status_code"),
        "api_url": response.get("api_url"),
        "response_text": response.get("response_text"),
        "chapter_name": (response.get("data") or {}).get("章节名称") if isinstance(response.get("data"), dict) else None,
    }
    return _failure_from_message(
        failure_type,
        stage,
        reason or f"第{module}章数据异常",
        context={key: value for key, value in context.items() if value not in (None, "")},
    )


def _failure_summary_fields(failure: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "failure_type": failure.get("failure_type"),
        "failure_type_label": failure.get("failure_type_label"),
        "failure_stage": failure.get("failure_stage"),
        "failure_reason": failure.get("failure_reason"),
    }


def _apply_failure(diagnostics: Dict[str, Any], failure: Dict[str, Any], status: Optional[str] = None) -> None:
    if status:
        diagnostics["status"] = status
    diagnostics.update(_failure_summary_fields(failure))
    diagnostics["failure"] = failure


def derive_chapter7_source(
    raw_responses: Dict[int, Dict[str, Any]],
    person_config: Dict[str, Any],
    calmonth: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """历史兼容：从旧 1-6 章原始指标里尝试提取第七章行销行为字段。"""
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


def _chapter8_strategy_lines_with_chapter3_product_rule(
    strategy_lines: List[str],
    chapter3_raw: Dict[str, Any],
) -> List[str]:
    product_strategy = _chapter3_product_decline_strategy(chapter3_raw)
    non_product_lines = [
        line for line in strategy_lines
        if not str(line).lstrip().startswith(("产品：", "产品:"))
    ]
    if product_strategy:
        return [product_strategy, *non_product_lines]
    return non_product_lines


def _chapter3_product_decline_strategy(chapter3_raw: Dict[str, Any]) -> str:
    try:
        from ReportGenerator.chapter3_generator import build_chapter3_risk_product_names

        product_names = build_chapter3_risk_product_names(chapter3_raw)
    except Exception:
        return ""
    if not product_names:
        return ""
    return f"产品：{'、'.join(product_names)}产品销量下滑，制定针对性推广或调整策略"


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
