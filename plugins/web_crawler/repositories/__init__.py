from web_crawler.repositories.base import SearchCollector, TargetContents
from web_crawler.repositories.naver import NaverSearchCollector

__all__ = ["SearchCollector", "TargetContents", "NaverSearchCollector", "get_collectors"]

_REGISTRY: dict[str, type[SearchCollector]] = {
    "naver": NaverSearchCollector,
}


def get_collectors(platforms: list[str] | None = None) -> list[SearchCollector]:
    """platforms=None 이면 전체, 지정하면 해당 플랫폼만 반환한다."""
    targets = platforms or list(_REGISTRY.keys())
    unknown = set(targets) - _REGISTRY.keys()
    if unknown:
        raise ValueError(f"등록되지 않은 플랫폼: {unknown}")
    return [_REGISTRY[p]() for p in targets]
