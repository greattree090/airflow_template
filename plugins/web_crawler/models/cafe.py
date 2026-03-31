from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class CafeRow:
    keyword: str
    order: int
    date: date
    cafe_name: str
    subject: str
    url: str
