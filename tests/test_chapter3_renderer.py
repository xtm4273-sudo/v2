"""测试第三章 HTML/PDF 渲染器。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ReportGenerator.chapter3_renderer import save_final_html, save_final_pdf


SAMPLE_MARKDOWN = """# 三、销量分析

## 3.1 销量概况

| 销量 | 6月 | 本季度累计 | 1-6月累计 |
| --- | --- | --- | --- |
| 目标 | — | — | — |
| 实际 | 0.24万 | 1.13万 | 7.96万 |
| 达成率 | — | — | — |

## 3.2 过程指标概况

* 当前目标和同期口径不足，暂不评价未达百和同比变化，仅展示过程指标实际值。

| 过程指标 | 实际 | 目标 | 达成率 | 同期 | 同比增长率 |
| --- | --- | --- | --- | --- | --- |
| 产销客户数 | 15个 | — | — | — | — |

## 3.3 产品、产销客户、产销项目及行业

* 表现指标
  * 产品：销量金额口径排名前三为内墙乳胶漆面漆1.80万。
* 行动指南：结合产销客户和产销项目明细盘点增量机会。
"""


class Chapter3RendererTest(unittest.TestCase):
    def test_save_html_and_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html_path = save_final_html(SAMPLE_MARKDOWN, tmp_path / "chapter3.html")
            pdf_path = save_final_pdf(SAMPLE_MARKDOWN, tmp_path / "chapter3.pdf")

            self.assertTrue(html_path.exists())
            self.assertTrue(pdf_path.exists())
            self.assertIn("第三章销量分析报告", html_path.read_text(encoding="utf-8"))
            self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
