from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class BlogRow:
    keyword: str
    order: int
    date: date
    blog_name: str
    subject: str
    url: str
