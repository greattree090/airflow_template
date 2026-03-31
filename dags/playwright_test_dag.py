"""Playwright 동작 확인용 진단 DAG

about:blank 처럼 리소스 소모가 거의 없는 페이지를 로드하여
Playwright + Chromium 설치 상태를 확인한다.
"""
import asyncio
import logging
from datetime import datetime

from airflow.sdk import DAG, task

logger = logging.getLogger(__name__)


with DAG(
    dag_id="playwright_test",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["test"],
) as dag:

    @task
    def test_playwright() -> None:
        from playwright.async_api import async_playwright

        async def _run():
            async with async_playwright() as p:
                logger.info("Playwright 초기화 성공")

                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
                )
                logger.info("Chromium 브라우저 실행 성공")

                try:
                    context = await browser.new_context()
                    page = await context.new_page()

                    # 1. about:blank — 네트워크 없이 즉시 로드
                    await page.goto("about:blank")
                    logger.info("about:blank 로드 성공")

                    # 2. data URI — 최소 HTML 렌더링 확인
                    await page.goto("data:text/html,<h1>hello</h1>")
                    title = await page.title()
                    content = await page.inner_text("h1")
                    logger.info("data URI 로드 성공. title=%r content=%r", title, content)

                    # 3. 실제 외부 URL — 네트워크 + 렌더링 확인
                    await page.goto(
                        "https://search.naver.com/search.naver?ssc=tab.blog.all&st=rel",
                        wait_until="domcontentloaded",
                        timeout=0,
                    )
                    title = await page.title()
                    logger.info("naver.com 로드 결과. title=%r", title)

                    await context.close()
                    logger.info("테스트 완료 — Playwright 정상 동작")
                finally:
                    await browser.close()

        asyncio.run(_run())

    test_playwright()
