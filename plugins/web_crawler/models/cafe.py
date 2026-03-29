from dataclasses import dataclass


@dataclass(slots=True)
class CafeRow:
    keyword: str
    order: int
    date: str
    cafe_name: str
    subject: str
    url: str
