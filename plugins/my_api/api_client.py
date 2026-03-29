"""외부 API 호출 모듈"""

import requests


def send_results(api_url: str, payload: dict, timeout: int = 30) -> dict:
    """크롤링 결과를 외부 API로 POST 전송한다."""
    response = requests.post(api_url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
