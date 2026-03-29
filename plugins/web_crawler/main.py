import logging
from pathlib import Path

from web_crawler.exceptions import ApplicationException
from web_crawler.repositories import get_collectors
from web_crawler.services import CrawlService

logger = logging.getLogger(__name__)


def collect(keywords: list[str], platforms: list[str] | None = None) -> dict:
    """키워드를 수집하고 직렬화 가능한 dict를 반환한다."""

    logger.info(f"Collecting data for keywords: {keywords} on platforms: {platforms or 'all'}")

    return {}


def export(results: dict, output_dir: Path) -> dict[str, str]:
    """수집 결과를 CSV로 저장하고 파일 경로 dict를 반환한다."""
    return CrawlService(get_collectors()).export(results, output_dir)


def run(keywords: list[str], platforms: list[str] | None = None, output_dir: Path | None = None) -> dict[str, str]:
    """키워드를 수집하고 직렬화 가능한 dict를 반환한다."""

    data = CrawlService(get_collectors(platforms)).collect(keywords)

    if not data:
        raise ApplicationException("수집된 데이터가 없습니다.")

    result = CrawlService(get_collectors()).export(data, output_dir)

    return result