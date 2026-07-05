"""测试第五章 HTML/PDF 渲染器。"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ReportGenerator.chapter5_generator import format_chapter5_data
from ReportGenerator.chapter5_renderer import save_final_html, save_final_pdf


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "Data" / "fixtures" / "chapter5_mock.json"


def _svg_node_text_at(html: str, x: int, y: int) -> str:
    marker = f'<rect x="{x}" y="{y}"'
    start = html.find(marker)
    if start == -1:
        return ""
    group_end = html.find("</g>", start)
    snippet = html[start:group_end]
    return " ".join(re.findall(r"<tspan[^>]*>(.*?)</tspan>", snippet))


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
            self.assertIn("chart-node-svg root", html)
            self.assertIn("wide-table", html)
            self.assertIn("逾期金额前五客户", html)
            self.assertIn("减值损失影响金额 TOP5 客户", html)
            self.assertGreater(pdf_path.stat().st_size, 1000)

    def test_receivable_chart_distinguishes_storm_from_non_storm_direct(self):
        markdown = """# 五、应收分析

## 5.1 应收款项概况

应收款项结构：
- 应收款项 99.2万元
  - 应收账款 99.2万元
    - 经销 74.4万元
      - 逾期（含诉讼） 22.2万元
    - 直销 24.8万元
      - 非暴雷直销应收 0.0万元
        - 逾期 0.0万元
      - 暴雷直销应收 24.8万元
        - 逾期 24.8万元
"""
        with tempfile.TemporaryDirectory() as tmp:
            html_path = save_final_html(markdown, Path(tmp) / "chapter5.html")
            html = html_path.read_text(encoding="utf-8")

            self.assertIn('rect x="615" y="134"', html)
            self.assertIn('rect x="615" y="264"', html)
            self.assertEqual(_svg_node_text_at(html, 615, 30), "逾期（含诉讼） 22.2万元")
            self.assertEqual(_svg_node_text_at(html, 805, 134), "逾期 24.8万元")
            self.assertEqual(_svg_node_text_at(html, 805, 264), "逾期 0.0万元")
            self.assertRegex(
                html,
                r'x="615" y="134".*?>暴雷直销应收</tspan><tspan[^>]*>24\.8万元',
            )
            self.assertRegex(
                html,
                r'x="615" y="264".*?>非暴雷直销应收</tspan><tspan[^>]*>0\.0万元',
            )


if __name__ == "__main__":
    unittest.main()
