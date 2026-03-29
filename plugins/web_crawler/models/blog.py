from dataclasses import dataclass


@dataclass(slots=True)
class BlogRow:
    keyword: str
    order: int
    date: str
    blog_name: str
    subject: str
    url: str
