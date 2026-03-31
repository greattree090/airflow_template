from dataclasses import dataclass


@dataclass(slots=True)
class SmartBlockRow:
    keyword: str
    order: int
    title: str
    url: str
