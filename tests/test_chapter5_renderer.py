"""测试第五章 HTML/PDF 渲染器。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ReportGenerator.chapter5_generator import format_chapter5_data
from ReportGenerator.chapter5_renderer import save_final_html, save_final_pdf


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "Data" / "fixtures" / "chapter5_mock.json"


class Chapter5RendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.markdown, _stats = format_chapter5_data(response)

    def test_save_html_and_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html_path = save_final_html(self.markdown, tmp_path / "chapter5.html")
            pdf_path = save_final_pdf(self.markdown, tmp_path / "chapter5.pdf")

            html = html_path.read_text(encoding="utf-8")

            self.assertTrue(html_path.exists())
            self.assertTrue(pdf_path.exists())
            self.assertIn("第五章应收分析报告", html)
            self.assertIn("receivable-chart", html)
            self.assertIn("chart-node root", html)
            self.assertIn("wide-table", html)
            self.assertIn("逾期金额前五客户", html)
            self.assertIn("减值损失影响金额 TOP5 客户", html)
            self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
