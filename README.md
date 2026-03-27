# Airflow Template

Apache Airflow 3.x 기반의 로컬 개발 환경 템플릿입니다.
Docker Compose를 사용하여 CeleryExecutor 구성의 Airflow 클러스터를 실행합니다.

## 디렉토리 구조

```
.
├── .env                     # 환경변수 (git 미포함)
├── config/
│   └── airflow.cfg          # Airflow 설정 파일
├── dags/
│   └── example_dag.py       # 샘플 DAG
├── logs/                    # Airflow 실행 로그 (git 미포함)
├── plugins/                 # 커스텀 플러그인
├── Dockerfile               # 커스텀 Airflow 이미지 빌드
├── docker-compose.yaml      # Airflow 클러스터 구성
├── pyproject.toml           # Python 프로젝트 설정
├── uv.lock                  # 패키지 잠금 파일
└── requirements.txt         # pip 의존성 목록
```

## 시작하기

### 1. 저장소 클론

```bash
git clone <repository-url>
cd airflow-template
```

### 2. 환경변수 설정

```bash
cp .env.sample .env
```

`.env` 파일을 열어 아래 값들을 설정합니다:

```env
AIRFLOW_UID=50000                          # Linux: id -u 결과값, Windows/Mac: 50000
AIRFLOW_PORT=8080                          # Airflow 웹 UI 포트

_AIRFLOW_WWW_USER_USERNAME=your_account    # Airflow 웹 UI 관리자 ID
_AIRFLOW_WWW_USER_PASSWORD=your_password   # Airflow 웹 UI 관리자 PW
```

### 3. Airflow 초기화 및 실행

```bash
# 초기화 (DB 마이그레이션 + 관리자 계정 생성)
docker compose up airflow-init

# 전체 서비스 실행
docker compose up -d
```

### 4. 접속 확인

Airflow 웹 UI: http://{url}:{AIRFLOW_PORT}

### 5. 서비스 종료

```bash
docker compose down
```

## 커스텀 이미지 빌드

추가 Python 패키지가 필요한 경우 `pyproject.toml`에 의존성을 추가한 뒤:

```bash
# docker-compose.yaml에서 image 대신 build 사용으로 전환 후
docker compose build
docker compose up -d
```
