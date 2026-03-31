import asyncio
import logging

from collections.abc import Iterator
from datetime import date, datetime
from typing import TypeVar
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from web_crawler.config import Settings
from web_crawler.models import CafeRow, SearchResultsBundle
from web_crawler.repositories.base import TargetContents

logger = logging.getLogger(__name__)

NAVER_BASE_URL = "https://search.naver.com"
NAVER_SEARCH_URL = f"{NAVER_BASE_URL}/search.naver"
CAFE_TAB_SSC = "tab.cafe.all"
DEFAULT_SORT_ORDER = "rel"
DEFAULT_MAX_ROWS = 10

CAFE_DATE_FETCH_TIMEOUT_SEC = 5.0
CAFE_TAB_TARGET_SELECTOR = "section.sc_new.sp_ncafe li.bx, #main_pack li.bx"
CAFE_AD_BANNER_SELECTOR = (
    "a[class^='fender-ui'] svg.fender-ui_08aaffd5.fender-ui_c3b5e09c",
    ".ico_ad",
    ".link_ad",
)

CAFE_ARTICLE_IFRAME_SELECTORS = "iframe#cafe_main[src]"
CAFE_ARTICLE_DATE_SELECTORS = (
    ".article_header span.date",
)

CAFE_ABSOLUTE_DATE_FORMATS = (
    "%Y.%m.%d.",
    "%Y.%m.%d",
    "%Y. %m. %d.",
    "%Y. %m. %d",
    "%Y.%m.%d. %H:%M",
    "%Y.%m.%d %H:%M",
    "%Y. %m. %d. %H:%M",
    "%Y. %m. %d %H:%M",
)

PLAYWRIGHT_VIEWPORT = {"width": 1440, "height": 4000}
PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

T = TypeVar("T")


class CafeTabContents(TargetContents):
    task_name = "cafe"

    def __init__(
        self,
        sort_order: str = DEFAULT_SORT_ORDER,
        max_rows: int = DEFAULT_MAX_ROWS,
        max_concurrency: int | None = None,
        timeout_ms: int | None = None,
        render_wait_ms: int | None = None,
    ) -> None:
        self.sort_order = sort_order
        self.max_rows = max(1, max_rows)
        self.max_concurrency = max(1, max_concurrency if max_concurrency is not None else Settings.get_naver_max_concurrency())
        self.timeout_ms = timeout_ms if timeout_ms is not None else Settings.get_naver_timeout_ms()
        self.render_wait_ms = render_wait_ms if render_wait_ms is not None else Settings.get_naver_render_wait_ms()

    async def run(self, keywords: list[str]) -> SearchResultsBundle:
        logger.info("Cafe task started. keywords=%s", len(keywords))

        results = SearchResultsBundle()
        if not keywords:
            logger.info("Cafe task finished. rows=%s", 0)
            return results

        async with async_playwright() as playwright:
            # chromium 실행
            browser = await playwright.chromium.launch(
                headless=True,
                # args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
            )

            try:
                context = await browser.new_context(
                    locale="ko-KR",
                    user_agent=PLAYWRIGHT_USER_AGENT,
                    viewport=PLAYWRIGHT_VIEWPORT,
                )
                try:
                    # 키워드를 max_concurrency 개씩 나눠서 수집 작업을 병렬로 실행
                    for batch in _chunked(keywords, self.max_concurrency):
                        batch_rows = await asyncio.gather(
                            *(self._collect_keyword(context, keyword) for keyword in batch),
                        )
                        for rows in batch_rows:
                            results.cafe_rows.extend(rows)
                finally:
                    await context.close()
            finally:
                await browser.close()

        logger.info("Cafe task finished. rows=%s", len(results.cafe_rows))
        return results

    async def _collect_keyword(self, context, keyword: str) -> list[CafeRow]:
        page = None

        try:
            page = await context.new_page()

            await page.goto(
                _build_cafe_tab_url(query=keyword, sort_order=self.sort_order),
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )

            await page.wait_for_timeout(self.render_wait_ms)

            html = await page.content()

            return await _parse_cafe_rows(keyword, html, self.max_rows, context)
        
        except Exception as e:
            logger.exception("Cafe collection failed. keyword=%s", keyword)
            logger.exception(e)
            return []
        
        finally:
            if page is not None:
                await page.close()


def _build_cafe_tab_url(query: str, sort_order: str = DEFAULT_SORT_ORDER) -> str:
    return f"{NAVER_SEARCH_URL}?{urlencode({'ssc': CAFE_TAB_SSC, 'query': query, 'st': sort_order})}"


async def _parse_cafe_rows(keyword: str, html: str, max_rows: int = DEFAULT_MAX_ROWS, context=None) -> list[CafeRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[CafeRow] = []
    row_limit = max(1, max_rows)

    for card in soup.select(CAFE_TAB_TARGET_SELECTOR):
        # 광고 배너 여부 확인
        if _is_cafe_ad_card(card):
            continue

        # 카페 탭 검색 결과 목록 추출
        row = await _parse_cafe_card(keyword, card, len(rows) + 1, context)

        if row is None:
            continue

        rows.append(row)

        # row_limit 개수만큼 결과 행을 수집
        if len(rows) >= row_limit:
            break

    return rows


async def _parse_cafe_card(keyword: str, card, order: int, context) -> CafeRow | None:

    # 카페 링크
    cafe_anchor = card.select_one(".user_info a.name")
    # 작성일
    date_element = card.select_one(".user_info span.sub")
    # 게시물 링크
    subject_anchor = card.select_one(".title_area a.title_link[href]")

    if cafe_anchor is None or date_element is None or subject_anchor is None:
        return None

    # 카페명
    cafe_name = _normalize_text(cafe_anchor.get_text(" ", strip=True))
    subject = _normalize_text(subject_anchor.get_text(" ", strip=True))
    url = _to_absolute_url(subject_anchor.get("href"))
    date = await _extract_cafe_card_date(date_element, url, context)

    if not cafe_name or not date or not subject or not url:
        return None

    return CafeRow(
        keyword=keyword,
        order=order,
        date=date,
        cafe_name=cafe_name,
        subject=subject,
        url=url,
    )


async def _extract_cafe_card_date(date_element, url: str | None, context) -> date | None:
    displayed_date = _normalize_text(date_element.get_text(" ", strip=True))

    normalized_displayed_date = _normalize_cafe_date_text(displayed_date)

    if normalized_displayed_date:
        return normalized_displayed_date

    if not url:
        return None

    # date 포맷에 맞지 않는 경우, 글 상세 페이지에서 작성일을 추출 시도
    fetched_date = await _extract_cafe_article_date(url, context)

    if fetched_date:
        return fetched_date

    return None


def _normalize_cafe_date_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = _normalize_text(value)
    if not cleaned:
        return None

    iso_candidate = cleaned.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate).strftime("%Y.%m.%d.")
    except ValueError:
        pass

    for date_format in CAFE_ABSOLUTE_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, date_format).strftime("%Y.%m.%d.")
        except ValueError:
            continue

    return None


async def _extract_cafe_article_date(url: str, context) -> date | None:
    page = None

    try:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # iframe이 렌더링 됐는지 확인 후, 아직 렌더링이 안됐으면 최대 3초까지 대기
        iframe_locator = page.locator(CAFE_ARTICLE_IFRAME_SELECTORS).first
        if not await iframe_locator.is_visible():
            await iframe_locator.wait_for(timeout=3000)

        iframe = await iframe_locator.element_handle()
        if iframe is None:
            return None

        frame = await iframe.content_frame()
        if frame is None:
            return None

        for selector in CAFE_ARTICLE_DATE_SELECTORS:
            try:
                date_element = frame.locator(selector).first
                if not await date_element.is_visible():
                    await date_element.wait_for(timeout=3000)
                text = await date_element.inner_text()

                normalized_date = _normalize_cafe_date_text(text)
                if normalized_date:
                    return normalized_date
            except Exception:
                continue

    except Exception as e:
        logger.warning("Cafe article date fetch failed. url=%s error=%s", url, e)

    finally:
        if page is not None:
            await page.close()

    return None


def _is_cafe_ad_card(card) -> bool:

    for selector in CAFE_AD_BANNER_SELECTOR:
        if card.select_one(selector) is not None:
            return True

    return False


def _to_absolute_url(href: str | None) -> str | None:
    if not href:
        return None

    href = href.strip()

    # Javascript 링크나 빈 링크는 무시
    if not href or href == "#" or href.startswith("javascript:"):
        return None

    # 쿼리 스트링 등 제거
    url = urlparse(urljoin(NAVER_BASE_URL, href))
    return urlunparse(url._replace(query="", fragment=""))


def _normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(text.split())


def _chunked(values: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]
