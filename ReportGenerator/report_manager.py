"""
报告管理器 - 创建目录、保存文件
"""
from typing import Dict, Any, Tuple
from pathlib import Path
import aiofiles


class ReportManager:
    def __init__(self, time: str, sale_config: Dict[str, Any]):
        self.time = time
        self.sale_config = sale_config
        self.sale_id = sale_config["job_id"]
        self.sale_name = sale_config["sale_name"]

    def create_report_directory(self) -> Tuple[Path, Path]:
        """
        创建报告目录
        :return: (report_dir, progress_report_dir)
        """
        report_dir = Path("Reports") / self.time / self.sale_name
        report_dir.mkdir(parents=True, exist_ok=True)

        progress_dir = report_dir / "progress_report"
        progress_dir.mkdir(exist_ok=True)

        return report_dir, progress_dir

    async def save_chapter_markdown(
        self, chapter_num: int, content: str, progress_dir: Path
    ) -> Path:
        """保存章节 Markdown 文件"""
        file_path = progress_dir / f"Chapter{chapter_num}_{self.sale_name}.md"
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)
        return file_path
