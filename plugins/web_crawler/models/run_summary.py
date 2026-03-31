from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RunSummary:
    keyword_count: int
    smartblock_count: int
    cafe_count: int
    blog_count: int
    output_dir: Path
    output_files: dict[str, Path]
