# 1. Airflow 공식 이미지 사용
FROM apache/airflow:3.1.8-python3.12

USER root

# [Step 1] 시스템 의존성 설치 (root 권한 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# [Step 2] 프로젝트 설정 파일 복사 및 권한 설정
COPY pyproject.toml uv.lock ./
RUN chown airflow:root pyproject.toml uv.lock

# [Step 3] Airflow 사용자로 전환 (pip 설치 및 패키지 관리 전용)
USER airflow

# [Step 6] 핵심 수정: pyproject.toml을 직접 빌드하지 않고, lock 파일 기반으로 패키지만 설치
# --frozen을 사용하기 위해 uv pip install -r <(uv export) 형태를 쓰고 싶지만, 
# uv 설치 문제로 requirements.txt를 사용.
COPY requirements.txt ./
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r requirements.txt
RUN pip check


# [Step 7] Playwright 브라우저 
RUN pip install playwright

# ⚠️ 중요: playwright 시스템 의존성을 root로 설치
USER root
RUN python -m playwright install-deps chromium

# 캐시 정리
RUN apt-get clean && rm -rf /root/.cache/pip

# ⚠️ 중요: airflow 유저로 다시 전환 후 브라우저 설치
USER airflow
RUN python -m playwright install chromium

# 최종적으로 airflow 유저로 전환
USER airflow
