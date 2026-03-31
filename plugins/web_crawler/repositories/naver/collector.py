import asyncio
import logging

from web_crawler.exceptions import CollectionException
from web_crawler.models import SearchResultsBundle
from web_crawler.repositories.base import SearchCollector, TargetContents
from web_crawler.repositories.naver.contents import BlogTabContents, CafeTabContents, SmartBlockContents

logger = logging.getLogger(__name__)


class NaverSearchCollector(SearchCollector):
    collector_name = "naver"

    def __init__(self, tasks: list[TargetContents] | None = None) -> None:
        self.tasks = tasks or [
            SmartBlockContents(),
            CafeTabContents(),
            BlogTabContents(),
        ]

    def collect(self, keywords: list[str]) -> SearchResultsBundle:
        logger.info("네이버 수집 작업을 비동기로 실행합니다. tasks=%s", len(self.tasks))

        return asyncio.run(self._collect_async(keywords))

    async def _collect_async(self, keywords: list[str]) -> SearchResultsBundle:
        try:
            task_results = await asyncio.gather(
                *(task.run(keywords) for task in self.tasks),
            )
        except Exception as exc:
            raise CollectionException("네이버 수집 작업 실행 중 오류가 발생했습니다.") from exc

        results = SearchResultsBundle()
        
        for task_result in task_results:
            results.extend(task_result)

        logger.info(
            "%s 수집이 종료되었습니다. smartblock=%s cafe=%s blog=%s",
            self.collector_name,
            len(results.smartblock_rows),
            len(results.cafe_rows),
            len(results.blog_rows),
        )
        return results
