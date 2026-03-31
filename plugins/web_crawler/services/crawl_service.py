import logging
from collections.abc import Sequence
from pathlib import Path

from web_crawler.models import SearchResultsBundle
from web_crawler.repositories.base import SearchCollector
from web_crawler.services.csv_writer import CsvExporter

logger = logging.getLogger(__name__)


class CrawlService:

    def __init__(
        self,
        collectors: Sequence[SearchCollector],
        exporter: CsvExporter | None = None,
    ) -> None:
        self.collectors = list(collectors)
        self.exporter = exporter or CsvExporter()

    def collect(self, keywords: list[str]) -> dict:
        """키워드를 수집하고 직렬화 가능한 dict를 반환한다."""
        logger.info("검색 키워드 수집을 시작합니다. collectors=%s", len(self.collectors))

        results = SearchResultsBundle()

        for collector in self.collectors:
            collector_name = collector.__class__.__name__
            logger.info("Collector: '%s'", collector_name)
            
            result = collector.collect(keywords)

            logger.info(
                "[%s] 종료. smartblock=%s cafe=%s blog=%s",
                collector_name,
                len(result.smartblock_rows),
                len(result.cafe_rows),
                len(result.blog_rows),
            )

            results.extend(result)

        logger.info(
            "수집 완료. smartblock=%s cafe=%s blog=%s",
            len(results.smartblock_rows),
            len(results.cafe_rows),
            len(results.blog_rows),
        )

        return results.to_dict()

    def export(self, results_dict: dict, output_dir: Path) -> dict[str, str]:
        """dict를 CSV로 저장하고 파일 경로 dict를 반환한다.

        Returns:
            콘텐츠 종류를 키, 저장된 CSV 파일의 절대 경로 문자열을 값으로 하는 dict.
            예시::

                {
                    "smartblock": "/opt/airflow/output/smartblock.csv",
                    "cafe": "/opt/airflow/output/cafe.csv",
                    "blog": "/opt/airflow/output/blog.csv",
                }
        """

        results = SearchResultsBundle.from_dict(results_dict)

        output_files = self.exporter.write(results, output_dir)
        
        return {k: str(v) for k, v in output_files.items()}           
