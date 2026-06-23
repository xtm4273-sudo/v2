"""Use Chromium's native text layout to print report HTML to PDF."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def html_to_pdf(html: str, output_path: Path) -> Path:
    """Print complete HTML with Chromium instead of drawing text with ReportLab.

    A worker thread keeps Playwright's synchronous API isolated from callers that
    are already running inside an asyncio event loop.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(_print_html, html, output_path).result()
    return output_path


def _print_html(html: str, output_path: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "缺少 Playwright。请先执行 pip install -r requirements.txt "
            "并运行 playwright install chromium。"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.emulate_media(media="print")
            page.evaluate("document.fonts.ready")
            page.pdf(
                path=str(output_path),
                format="A4",
                print_background=True,
                display_header_footer=False,
                margin={
                    "top": "15mm",
                    "bottom": "15mm",
                    "left": "15mm",
                    "right": "15mm",
                },
            )
        finally:
            browser.close()
