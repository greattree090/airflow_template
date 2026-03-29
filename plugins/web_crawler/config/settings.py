import os
from pathlib import Path


class Settings:
    """os.environ에서 설정값을 읽는다."""

    @classmethod
    def get_output_dir(cls) -> Path:
        return cls._get_path("APP_OUTPUT_DIR", "/opt/airflow/output")

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
    def _get_path(cls, env_key: str, default: str) -> Path:
        path = Path(os.getenv(env_key, default))
        return path if path.is_absolute() else path.resolve()

    @classmethod
    def _get_int(cls, env_key: str, default: int) -> int:
        raw = os.getenv(env_key)
        return int(raw) if raw is not None else default
