from dataclasses import dataclass, field

from web_crawler.models.blog import BlogRow
from web_crawler.models.cafe import CafeRow
from web_crawler.models.smartblock import SmartBlockRow


@dataclass(slots=True)
class SearchResultsBundle:
    smartblock_rows: list[SmartBlockRow] = field(default_factory=list)
    cafe_rows: list[CafeRow] = field(default_factory=list)
    blog_rows: list[BlogRow] = field(default_factory=list)

    def extend(self, other: "SearchResultsBundle") -> None:
        self.smartblock_rows.extend(other.smartblock_rows)
        self.cafe_rows.extend(other.cafe_rows)
        self.blog_rows.extend(other.blog_rows)

    def to_dict(self) -> dict:
        """직렬화를 위해 dict로 변환한다."""
        return {
            "smartblock_rows": [
                {"keyword": r.keyword, "order": r.order, "title": r.title, "url": r.url}
                for r in self.smartblock_rows
            ],
            "cafe_rows": [
                {"keyword": r.keyword, "order": r.order, "date": r.date, "cafe_name": r.cafe_name, "subject": r.subject, "url": r.url}
                for r in self.cafe_rows
            ],
            "blog_rows": [
                {"keyword": r.keyword, "order": r.order, "date": r.date, "blog_name": r.blog_name, "subject": r.subject, "url": r.url}
                for r in self.blog_rows
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SearchResultsBundle":
        """dict에서 복원한다."""
        return cls(
            smartblock_rows=[SmartBlockRow(**r) for r in data.get("smartblock_rows", [])],
            cafe_rows=[CafeRow(**r) for r in data.get("cafe_rows", [])],
            blog_rows=[BlogRow(**r) for r in data.get("blog_rows", [])],
        )
