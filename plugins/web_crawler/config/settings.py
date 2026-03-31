import os
from functools import lru_cache
from pathlib import Path


class Settings:
    """설정값을 읽는다.

    우선순위: os.environ > application.properties > 하드코딩 기본값
    """

    @classmethod
    def get_output_dir(cls) -> Path:
        value = cls._get_str("APP_OUTPUT_DIR", "/opt/airflow/output")
        path = Path(value)
        return path if path.is_absolute() else path.resolve()

    @classmethod
    def get_naver_max_concurrency(cls) -> int:
        return cls._get_int("NAVER_MAX_CONCURRENCY", 4)

    @classmethod
    def get_naver_timeout_ms(cls) -> int:
        return cls._get_int("NAVER_TIMEOUT_MS", 30_000)

    @classmethod
    def get_naver_render_wait_ms(cls) -> int:
        return cls._get_int("NAVER_RENDER_WAIT_MS", 3_000)

    @classmethod
    def _get_str(cls, key: str, default: str) -> str:
        return os.environ.get(key) or _load_properties().get(key, default)

    @classmethod
    def _get_int(cls, key: str, default: int) -> int:
        raw = os.environ.get(key) or _load_properties().get(key)
        return int(raw) if raw is not None else default


@lru_cache(maxsize=1)
def _load_properties() -> dict[str, str]:
    props_file = Path(__file__).parent / "application.properties"
    if not props_file.is_file():
        return {}
    result = {}
    for line in props_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip("'\"")
    return result
