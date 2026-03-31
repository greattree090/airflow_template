from abc import ABC, abstractmethod

from web_crawler.models import SearchResultsBundle


class TargetContents(ABC):
    task_name = "collection"

    @abstractmethod
    async def run(self, keywords: list[str]) -> SearchResultsBundle:
        """단일 요구사항에 대한 수집 결과를 반환한다."""
