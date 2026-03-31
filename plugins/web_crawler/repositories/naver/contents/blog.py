import asyncio
import logging

from collections.abc import Iterator
from datetime import date, datetime
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from web_crawler.config import Settings
from web_crawler.models import BlogRow, SearchResultsBundle
from web_crawler.repositories.base import TargetContents

logger = logging.getLogger(__name__)

NAVER_BASE_URL = "https://search.naver.com"
NAVER_SEARCH_URL = f"{NAVER_BASE_URL}/search.naver"
NAVER_BLOG_URL = "https://blog.naver.com"
BLOG_TAB_SSC = "tab.blog.all"
DEFAULT_SORT_ORDER = "rel"
DEFAULT_MAX_ROWS = 10

BLOG_DATE_FETCH_TIMEOUT_SEC = 5.0
BLOG_TAB_TARGET_SELECTOR = "section.sc_new.sp_nblog [data-template-id='ugcItem'], div._fe_view_power_content"
BLOG_AD_BANNER_SELECTOR = (
    "a[class^='fender-ui'] svg.fender-ui_08aaffd5.fender-ui_c3b5e09c",
)

BLOG_ARTICLE_IFRAME_SELECTORS = (
    "iframe#mainFrame[src]",
    "iframe[src*='PostView.naver']",
)
BLOG_ARTICLE_DATE_SELECTORS = (
    ".se-component-content .blog_date",
    ".se-component-content .se_publishDate",
)

BLOG_ABSOLUTE_DATE_FORMATS = (
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


class BlogTabContents(TargetContents):
    task_name = "blog"

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
        logger.info("Blog task started. keywords=%s", len(keywords))

        results = SearchResultsBundle()

        if not keywords:
            logger.info("Blog task finished. rows=%s", 0)
            return results

        async with async_playwright() as playwright:
            # chromium 실행
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
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
                            results.blog_rows.extend(rows)
                finally:
                    await context.close()
            finally:
                await browser.close()

        logger.info("Blog task finished. rows=%s", len(results.blog_rows))
        return results

    async def _collect_keyword(self, context, keyword: str) -> list[BlogRow]:
        page = None
        
        try:
            page = await context.new_page()

            await page.goto(
                _build_blog_tab_url(query=keyword, sort_order=self.sort_order),
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )

            await page.wait_for_timeout(self.render_wait_ms)

            html = await page.content()

            return _parse_blog_rows(keyword, html, self.max_rows)
        
        except Exception as e:
            logger.exception("Blog collection failed. keyword=%s", keyword)
            logger.exception(e)
            return []
        
        finally:
            if page is not None:
                await page.close()


def _build_blog_tab_url(query: str, sort_order: str = DEFAULT_SORT_ORDER) -> str:
    return f"{NAVER_SEARCH_URL}?{urlencode({'ssc': BLOG_TAB_SSC, 'query': query, 'st': sort_order})}"


def _parse_blog_rows(keyword: str, html: str, max_rows: int = DEFAULT_MAX_ROWS) -> list[BlogRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[BlogRow] = []
    row_limit = max(1, max_rows)

    for card in soup.select(BLOG_TAB_TARGET_SELECTOR):
        # 광고 배너 여부 확인
        if _is_blog_ad_card(card):
            continue

        # 블로그 탭 검색 결과 목록 추출
        row = _parse_blog_card(keyword, card, len(rows) + 1)

        if row is None:
            continue

        rows.append(row)

        # row_limit 개수만큼 결과 행을 수집
        if len(rows) >= row_limit:
            break

    return rows


def _parse_blog_card(keyword: str, card, order: int) -> BlogRow | None:

    # 블로그 카드 내 상단 프로필 영역 (썸네일, 블로그명, 작성일, 광고 배너 등)
    card_profile = card.select_one(".sds-comps-profile, [data-sds-comp='Profile']")

    if card_profile is None:
        return None
    
    # 블로그 링크
    blog_anchor = card_profile.select_one(".sds-comps-profile-info-title-text a[href]")
    # 작성일
    date_element = card_profile.select_one(".sds-comps-profile-info-subtext")

    # 블로그명
    blog_name = _normalize_text(blog_anchor.get_text(" ", strip=True))
    blog_url = _to_absolute_url(blog_anchor.get("href"))

    if not blog_name or not blog_url:
        return None

    # 블로그명과 URL을 활용하여 게시물의 제목과 URL 추출
    subject_anchor = _select_blog_subject_anchor(card, blog_name, blog_url)

    # 글 제목, 게시물 URL, 작성일 추출
    subject = _normalize_text(subject_anchor.get_text(" ", strip=True))
    url = _to_absolute_url(subject_anchor.get("href"))
    date = _extract_blog_card_date(date_element, url)

    if not subject or not url or not date:
        return None

    return BlogRow(
        keyword=keyword,
        order=order,
        date=date,
        blog_name=blog_name,
        subject=subject,
        url=url,
    )


def _extract_blog_card_date(date_element, url: str | None) -> date | None:
    displayed_date = _normalize_text(date_element.get_text(" ", strip=True))

    # date 타입으로 return 
    normalized_displayed_date = _normalize_blog_date_text(displayed_date)

    if normalized_displayed_date:
        return normalized_displayed_date

    if not url:
        return None

    # date 포맷에 맞지 않는 경우, 글 상세 페이지에서 작성일을 추출 시도
    fetched_date = _extract_blog_article_date(url)

    if fetched_date:
        return fetched_date

    return None


def _normalize_blog_date_text(value: str | None) -> date | None:
    if not value:
        return None

    cleaned = _normalize_text(value)

    if not cleaned:
        return None

    iso_candidate = cleaned.replace("Z", "+09:00")
    try:
        return datetime.fromisoformat(iso_candidate).date()
    except ValueError:
        pass

    for date_format in BLOG_ABSOLUTE_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue

    return None


def _extract_blog_article_date(url: str) -> date | None:

    html = _fetch_blog_html(url)

    if html is None:
        return None

    outer_soup = BeautifulSoup(html, "html.parser")

    # 글 상세 페이지 내 iframe 요소에서 실제 글 내용이 로드되는 URL 추출 시도
    inner_url = None
    for selector in BLOG_ARTICLE_IFRAME_SELECTORS:
        iframe = outer_soup.select_one(selector)
        if iframe is not None:
            inner_url = urljoin(NAVER_BLOG_URL, _normalize_text(iframe.get("src")))
            break

    if inner_url is None:
        return None

    # iframe 내의 url 로 다시 접근.
    inner_html = _fetch_blog_html(inner_url, referer=url)
    if inner_html is None:
        return None

    # 내부 요소에서 작성일 추출
    inner_soup = BeautifulSoup(inner_html, "html.parser")

    for selector in BLOG_ARTICLE_DATE_SELECTORS:
        for element in inner_soup.select(selector):
            normalized_date = _normalize_blog_date_text(element.get_text(" ", strip=True))
            if normalized_date:
                return normalized_date

    return None


def _fetch_blog_html(url: str, referer: str = NAVER_BASE_URL) -> bytes | None:

    try:
        request = Request(
            url, 
            headers={
                "User-Agent": PLAYWRIGHT_USER_AGENT, 
                "Referer": referer
            },
        )
        
        with urlopen(request, timeout=BLOG_DATE_FETCH_TIMEOUT_SEC) as response:
            return response.read()
        
    except (HTTPError, URLError, TimeoutError, OSError):
        logger.debug("Blog article fetch skipped. url=%s", url)
        return None


def _select_blog_subject_anchor(card, blog_name: str, author_url: str):
    for anchor in card.select("a[href]"):
        href = _to_absolute_url(anchor.get("href"))
        text = _normalize_text(anchor.get_text(" ", strip=True))

        if not href or not text:
            continue
        if href == author_url or text == blog_name:
            continue
        if href.startswith("https://keep.naver.com/"):
            continue
        if href.startswith(f"{NAVER_BASE_URL}/search.naver") and "#" in href:
            continue
        if "help.naver.com" in href:
            continue

        return anchor
    
    return None


def _is_blog_ad_card(card) -> bool:

    for selector in BLOG_AD_BANNER_SELECTOR:
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

    return urljoin(NAVER_BASE_URL, href)


def _normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(text.split())


def _chunked(values: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]
