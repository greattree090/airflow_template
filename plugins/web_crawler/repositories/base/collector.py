from abc import ABC, abstractmethod

from web_crawler.models import SearchResultsBundle


class SearchCollector(ABC):
    collector_name = "search"

    @abstractmethod
    def collect(self, keywords: list[str]) -> SearchResultsBundle:
        """검색 수집기 하나에 대한 결과 묶음을 반환한다."""
