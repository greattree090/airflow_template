"""검색 키워드 크롤링 DAG

검색 키워드 목록을 기반으로 웹 크롤링을 실시하고 결과를 저장하는 파이프라인입니다.
"""
import logging
from datetime import datetime
from pathlib import Path

from airflow.sdk import DAG, Param, task


logger = logging.getLogger(__name__)


with DAG(
    dag_id="crawling_search_keywords",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["crawling"],
    params={
        "keywords_file": Param(
            default="sample/input.txt",
            type="string",
            description="검색 키워드 리스트 파일 경로",
        ),
        "platforms": Param(
            default=[],
            type="array",
            description="크롤링할 플랫폼 목록 (비우면 전체 실행). 예: ['naver']",
        ),
        "output_dir": Param(
            default="/opt/airflow/output",
            type="string",
            description="CSV 결과 파일을 저장할 디렉토리 경로",
        ),
    },
) as dag:
    
    from web_crawler.main import collect_search_results, export_search_results

    @task
    def get_search_keywords(**context) -> list[str]:
        """키워드 파일을 읽어 키워드 목록을 반환한다."""
        keywords_file = context["params"]["keywords_file"]

        input_path = Path(keywords_file)
        if not input_path.is_absolute():
            input_path = (Path(__file__).parent / input_path).resolve()

        if not input_path.exists():
            raise FileNotFoundError(f"키워드 파일이 없습니다: {input_path}")

        keywords = [
            line.strip()
            for line in input_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        if not keywords:
            raise ValueError(f"키워드 파일이 비어 있습니다: {input_path}")
        
        logger.info(f"키워드 파일에서 {len(keywords)}개 키워드를 읽었습니다: {input_path}")

        return keywords

    @task
    def crawling_search_keywords(keywords: list[str], **context) -> dict:
        """키워드 목록으로 웹 크롤링을 실행하고 수집 결과를 반환한다."""
        platforms = context["params"]["platforms"] or None

        logger.info("검색 키워드 결과 크롤링 시작 - 키워드 수: %d", len(keywords))
        logger.info("크롤링 대상 플랫폼: %s", platforms or "전체")

        search_results = collect_search_results(keywords, platforms=platforms)

        logger.info("검색 키워드 결과 크롤링 완료 - smartblock=%s cafe=%s blog=%s",
            len(search_results.get("smartblock", [])),
            len(search_results.get("cafe", [])),
            len(search_results.get("blog", [])),
        )

        return search_results

    @task
    def load_result_data(results: dict, **context) -> None:
        """크롤링 결과 데이터를 CSV 파일로 저장한다."""
        logger.info("데이터 저장 시작 - 수집된 키워드 수: %d", len(results.get("smartblock", [])) + len(results.get("cafe", [])) + len(results.get("blog", [])))

        output_dir = Path(context["params"]["output_dir"])
        output_files = export_search_results(results, output_dir)

        logger.info(
            "결과 저장 완료. smartblock=%s cafe=%s blog=%s",
            output_files.get("smartblock"),
            output_files.get("cafe"),
            output_files.get("blog"),
        )

    keywords = get_search_keywords()
    results = crawling_search_keywords(keywords)
    load_result_data(results)


if __name__ == "__main__":
    dag.test(
        run_conf={
            "keywords_file": "sample/input.txt"
        }
    )