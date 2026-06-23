from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from ReportGenerator.browser_pdf import html_to_pdf


def test_customer_pdf_uses_chromium_text_rendering_inside_async_flow() -> None:
    html = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<style>body { font-family: "Microsoft YaHei", "Heiti SC", sans-serif; }</style>
<body><p>正文字体渲染回归测试</p></body></html>"""

    with TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "browser-text.pdf"

        async def render() -> None:
            html_to_pdf(html, output_path)

        asyncio.run(render())
        pdf_bytes = output_path.read_bytes()

    assert b"/Creator (Chromium)" in pdf_bytes
    assert b"ReportLab PDF Library" not in pdf_bytes
