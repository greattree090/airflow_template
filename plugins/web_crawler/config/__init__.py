import os
from pathlib import Path

from web_crawler.config.settings import Settings

__all__ = ["Settings", "load_env"]

_env_loaded = False


def load_env(env_file: Path | None = None) -> None:
    """.env 파일을 읽어 os.environ에 없는 키만 설정한다.

    이미 환경변수로 주입된 값(Docker/Airflow)은 덮어쓰지 않는다.

    Args:
        env_file: .env 파일 경로. None이면 프로젝트 루트 .env를 사용한다.
    """
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True

    target = env_file or _default_env_file()
    if not target.is_file():
        return

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _default_env_file() -> Path:
    # plugins/web_crawler/config/ 기준 3단계 상위 = 프로젝트 루트
    return Path(__file__).resolve().parents[3] / ".env"
