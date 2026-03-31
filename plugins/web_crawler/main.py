import logging
from pathlib import Path

from web_crawler.exceptions import ApplicationException
from web_crawler.repositories import get_collectors
from web_crawler.services import CrawlService

logger = logging.getLogger(__name__)


def collect_search_results(keywords: list[str], platforms: list[str] | None = None) -> dict:
    """키워드 목록을 크롤링하여 직렬화된 결과 dict를 반환한다.

    Args:
        keywords: 검색할 키워드 목록.
        platforms: 크롤링 대상 플랫폼 목록. ``None``이면 등록된 전체 플랫폼을 사용한다.

    Returns:
        ``SearchResultsBundle.to_dict()`` 형태의 직렬화된 수집 결과.
    """
    logger.info("검색 키워드에 대한 결과를 수집합니다.")
    logger.info("  keywords: %s", keywords)
    logger.info("  platforms: %s", platforms or "all")

    return CrawlService(get_collectors(platforms)).collect(keywords)


def export_search_results(results: dict, output_dir: Path) -> dict[str, str]:
    """수집 결과를 CSV 파일로 저장하고 파일 경로 dict를 반환한다.

    Args:
        results: ``collect_search_results()``가 반환한 직렬화된 수집 결과 dict.
        output_dir: CSV 파일을 저장할 디렉토리 경로.

    Returns:
        콘텐츠 종류를 키, 저장된 CSV 파일의 절대 경로 문자열을 값으로 하는 dict.
    """
    logger.info("검색 키워드에 대한 결과를 내보냅니다.")
    logger.info("  output_dir: %s", output_dir)

    return CrawlService(get_collectors()).export(results, output_dir)


def run(keywords: list[str], platforms: list[str] | None = None, output_dir: Path | None = None) -> dict[str, str]:
    """키워드를 수집한 뒤 CSV로 저장하고 파일 경로 dict를 반환한다.

    ``collect``와 ``export``를 순차적으로 실행하는 편의 함수다.

    Args:
        keywords: 검색할 키워드 목록.
        platforms: 크롤링 대상 플랫폼 목록. ``None``이면 등록된 전체 플랫폼을 사용한다.
        output_dir: CSV 파일을 저장할 디렉토리 경로. ``None``이면 설정 기본값을 사용한다.

    Returns:
        콘텐츠 종류를 키, 저장된 CSV 파일의 절대 경로 문자열을 값으로 하는 dict.

    Raises:
        ApplicationException: 수집 또는 저장 중 오류가 발생한 경우.
    """

    crawlService = CrawlService(get_collectors(platforms))

    results = crawlService.collect(keywords)
    output = crawlService.export(results, output_dir)

    return output


if __name__ == "__main__":

    search_result = collect_search_results(
        keywords=["갤럭시 S26", "아이폰 15"],
        platforms=["naver"]
    )

    logger.info(f"수집된 데이터: {search_result}")