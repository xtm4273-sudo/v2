"""使用 OpenAI 兼容 HTTP 接口生成第八章 AI 预览。"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from ReportGenerator.chapter8_ai_writer import Chapter8SummaryWriter
from ReportGenerator.chapter8_generator import format_chapter8_data_with_ai
from ReportGenerator.chapter8_renderer import save_final_html, save_final_pdf
from run_full_report_strict import normalize_display_numbers, normalize_missing_labels


class HttpChatModel:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: int = 120):
        self.api_key = api_key
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout

    async def ainvoke(self, messages):
        return await asyncio.to_thread(self._invoke, messages)

    def _invoke(self, messages):
        body = json.dumps(
            {"model": self.model, "messages": messages, "temperature": 0.1},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        return SimpleNamespace(content=result["choices"][0]["message"]["content"])


async def run(args):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("缺少 DEEPSEEK_API_KEY，未调用大模型。")

    source = json.loads(Path(args.source).read_text(encoding="utf-8"))
    model = HttpChatModel(api_key, args.base_url, args.model, timeout=args.timeout)
    markdown, stats = await format_chapter8_data_with_ai(
        source,
        period=args.calmonth,
        action_writer=Chapter8SummaryWriter(model=model),
    )
    if stats.get("行动指南来源") != "AI":
        raise SystemExit("大模型输出未通过事实校验，未生成 AI 预览。")

    markdown = normalize_display_numbers(normalize_missing_labels(markdown))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "chapter8_ai.md"
    html_path = output_dir / "chapter8_ai.html"
    pdf_path = output_dir / "chapter8_ai.pdf"
    stats_path = output_dir / "chapter8_ai_stats.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    save_final_html(markdown, html_path)
    save_final_pdf(markdown, pdf_path)
    print(json.dumps({"source": "AI", "markdown": str(markdown_path.resolve()), "pdf": str(pdf_path.resolve())}, ensure_ascii=False))


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--calmonth", default="202606")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--timeout", type=int, default=120)
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
