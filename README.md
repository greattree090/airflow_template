# Airflow Template

Apache Airflow 3.x 기반 웹 크롤링 파이프라인 템플릿.
네이버 검색 결과(SmartBlock, 카페, 블로그)를 키워드 단위로 수집하여 CSV로 저장한다.

- Python 3.12+
- Apache Airflow 3.1.8 (TaskFlow API / `airflow.sdk`, CeleryExecutor)
- Playwright + Chromium (비동기 브라우저 자동화)
- BeautifulSoup4 (HTML 파싱)

---

## 디렉토리 구조

```
airflow_template/
├── dags/
│   ├── crawling_search_keywords_dag.py   # 크롤링 DAG
│   ...
│
├── plugins/
│   ├── web_crawler/                      # 크롤러 플러그인 (layered architecture)
│   ...
│ 
├── .env                                  # Docker/Airflow 설정 (git 미포함)
├── docker-compose.yaml
├── Dockerfile
├── pyproject.toml
├── uv.lock
└── requirements.txt
```

---

## 시작하기

### 1. 환경변수 설정

```bash
cp .env.sample .env
```

`.env` 파일에서 아래 값을 설정한다.

```env
AIRFLOW_UID=50000                          # Linux: id -u 결과값, Windows/Mac: 50000
AIRFLOW_PORT=9000                          # Airflow 웹 UI 포트
_AIRFLOW_WWW_USER_USERNAME=admin           # 관리자 ID
_AIRFLOW_WWW_USER_PASSWORD=admin           # 관리자 PW
```

### 2. 이미지 빌드 및 실행

```bash
docker compose build
docker compose up airflow-init
docker compose up -d
```

### 3. 접속

Airflow 웹 UI: `http://localhost:{AIRFLOW_PORT}`

### 4. 종료

```bash
docker compose down
```

---

## DAG 목록

### 1. crawling_search_keywords_dag

```
get_search_keywords()          # 키워드 파일 → list[str]
  → crawling_search_keywords() # 크롤링 → dict (XCom)
  → load_result_data()         # CSV 저장
```

### DAG Params

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `keywords_file` | `sample/input.txt` | 키워드 파일 경로 (DAG 파일 기준 상대경로 가능) |
| `platforms` | `[]` (전체) | 크롤링 플랫폼 목록. 예: `["naver"]` |
| `output_dir` | `/opt/airflow/output` | CSV 저장 디렉토리 |

---

## Plugins

### web_crawler

네이버 검색 결과를 수집하는 크롤러 플러그인. layered architecture로 구성되어 있다.

| 레이어 | 경로 | 역할 |
|--------|------|------|
| 진입점 | `main.py` | `collect()` / `export()` / `run()` — DAG에서 호출 |
| Service | `services/` | 수집 오케스트레이션, CSV 저장 |
| Repository | `repositories/` | 외부 웹 크롤링 (읽기 전용) |
| Model | `models/` | 도메인 모델, XCom 직렬화 |
| Config | `config/` | 설정 읽기 (os.environ > application.properties) |

크롤러 설정은 `plugins/web_crawler/config/application.properties`에서 관리한다.

| 설정 키 | 기본값 | 설명 |
|---------|--------|------|
| `NAVER_MAX_CONCURRENCY` | `4` | 키워드 병렬 처리 수 |
| `NAVER_TIMEOUT_MS` | `30000` | 페이지 로딩 타임아웃 (ms) |
| `NAVER_RENDER_WAIT_MS` | `3000` | 렌더링 대기 시간 (ms) |

새 플랫폼 추가 시 `repositories/__init__.py`의 `_REGISTRY`에 등록해야 한다.

예시)

```python
_REGISTRY: dict[str, type[SearchCollector]] = {
    "naver": NaverSearchCollector,
    "google": GoogleSearchCollector,  # 추가
}
```

---

## 결과 파일 확인

크롤링 결과 CSV는 컨테이너 내 `/opt/airflow/output`에 저장된다.
로컬로 꺼내려면 `docker cp`를 사용한다.

```bash
# 전체 output 디렉토리
docker cp airflow_template-airflow-worker-1:/opt/airflow/output ./output

# 특정 파일만
docker cp airflow_template-airflow-worker-1:/opt/airflow/output/blog.csv ./blog.csv
```

---


## Docker 관련 참고

- `shm_size: '4gb'` — airflow-worker에 설정. Chromium이 `/dev/shm`을 공유 메모리로 사용하므로 크롤링 시 필요
- Chromium 실행 시 `--no-sandbox`, `--disable-setuid-sandbox`, `--disable-gpu` 플래그 사용
- `playwright install-deps chromium`은 Dockerfile에서 root 권한으로 실행
