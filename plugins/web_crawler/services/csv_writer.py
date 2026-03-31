import csv
import logging
from pathlib import Path

from web_crawler.exceptions import ExportException
from web_crawler.models import BlogRow, CafeRow, SearchResultsBundle, SmartBlockRow

logger = logging.getLogger(__name__)


class CsvExporter:
    def write(self, results: SearchResultsBundle, output_dir: Path) -> dict[str, Path]:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            smartblock_path = output_dir / "smartblock.csv"
            cafe_path = output_dir / "cafe.csv"
            blog_path = output_dir / "blog.csv"

            self._write_smartblock_rows(smartblock_path, results.smartblock_rows)
            self._write_cafe_rows(cafe_path, results.cafe_rows)
            self._write_blog_rows(blog_path, results.blog_rows)
        except OSError as exc:
            raise ExportException(f"CSV 파일 저장에 실패했습니다: {output_dir}") from exc

        logger.info(
            "CSV 저장 완료. smartblock=%s cafe=%s blog=%s",
            smartblock_path,
            cafe_path,
            blog_path,
        )

        return {
            "smartblock": smartblock_path.resolve(),
            "cafe": cafe_path.resolve(),
            "blog": blog_path.resolve(),
        }

    def _write_smartblock_rows(self, output_path: Path, rows: list[SmartBlockRow]) -> None:
        fieldnames = ["keyword", "order", "title", "url"]
        serialized = [
            {"keyword": r.keyword, "order": r.order, "title": r.title, "url": r.url}
            for r in rows
        ]
        self._write_csv(output_path, fieldnames, serialized)

    def _write_cafe_rows(self, output_path: Path, rows: list[CafeRow]) -> None:
        fieldnames = ["keyword", "order", "date", "café", "subject", "url"]
        serialized = [
            {
                "keyword": r.keyword,
                "order": r.order,
                "date": r.date,
                "café": r.cafe_name,
                "subject": r.subject,
                "url": r.url,
            }
            for r in rows
        ]
        self._write_csv(output_path, fieldnames, serialized)

    def _write_blog_rows(self, output_path: Path, rows: list[BlogRow]) -> None:
        fieldnames = ["keyword", "order", "date", "blog", "subject", "url"]
        serialized = [
            {
                "keyword": r.keyword,
                "order": r.order,
                "date": r.date,
                "blog": r.blog_name,
                "subject": r.subject,
                "url": r.url,
            }
            for r in rows
        ]
        self._write_csv(output_path, fieldnames, serialized)

    def _write_csv(
        self,
        output_path: Path,
        fieldnames: list[str],
        rows: list[dict],
    ) -> None:
        with output_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
