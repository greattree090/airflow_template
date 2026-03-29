import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import datetime
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

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
CAFE_TAB_TARGET_SELECTOR = "section.sc_new.sp_ncafe li.bx, #main_pack li.bx"
CAFE_DATE_FETCH_TIMEOUT_SEC = 5.0
ABSOLUTE_DATE_PATTERN = re.compile(r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})")
CAFE_ARTICLE_DATE_SELECTORS = (
    ".article_info .date",
    "span.date",
    "meta[property='article:published_time']",
    "meta[name='article:published_time']",
    "meta[property='og:article:published_time']",
    "meta[name='og:article:published_time']",
    "meta[property='article:modified_time']",
    "meta[name='article:modified_time']",
    "time[datetime]",
    ".se_publishDate",
    ".tit_info .date",
    ".write_date",
    ".post_date",
    ".date",
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
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    locale="ko-KR",
                    user_agent=PLAYWRIGHT_USER_AGENT,
                    viewport=PLAYWRIGHT_VIEWPORT,
                )
                try:
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
            return _parse_cafe_rows(keyword, html, self.max_rows)
        except Exception:
            logger.exception("Cafe collection failed. keyword=%s", keyword)
            return []
        finally:
            if page is not None:
                await page.close()


def _build_cafe_tab_url(query: str, sort_order: str = DEFAULT_SORT_ORDER) -> str:
    return f"{NAVER_SEARCH_URL}?{urlencode({'ssc': CAFE_TAB_SSC, 'query': query, 'st': sort_order})}"


def _parse_cafe_rows(keyword: str, html: str, max_rows: int = DEFAULT_MAX_ROWS) -> list[CafeRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[CafeRow] = []
    row_limit = max(1, max_rows)

    for card in soup.select(CAFE_TAB_TARGET_SELECTOR):
        if _is_cafe_ad_card(card):
            continue
        row = _parse_cafe_card(keyword, card, len(rows) + 1)
        if row is None:
            continue
        rows.append(row)
        if len(rows) >= row_limit:
            break

    return rows


def _parse_cafe_card(keyword: str, card, order: int) -> CafeRow | None:
    cafe_anchor = card.select_one(".user_info .name")
    date_element = card.select_one(".user_info .sub")
    subject_anchor = card.select_one(".title_link[href]")

    if cafe_anchor is None or date_element is None or subject_anchor is None:
        return None

    cafe_name = _normalize_text(cafe_anchor.get_text(" ", strip=True))
    date = _extract_cafe_card_date(card, date_element)
    subject = _normalize_text(subject_anchor.get_text(" ", strip=True))
    url = _to_absolute_url(subject_anchor.get("href"))

    if not cafe_name or not date or not subject or not url:
        return None

    return CafeRow(keyword=keyword, order=order, date=date, cafe_name=cafe_name, subject=subject, url=url)


def _extract_cafe_card_date(card, date_element) -> str:
    fallback_date = _normalize_text(date_element.get_text(" ", strip=True))

    absolute_date = _extract_absolute_date(fallback_date)
    if absolute_date:
        return absolute_date

    absolute_date = _extract_absolute_date(str(card))
    if absolute_date:
        return absolute_date

    subject_anchor = card.select_one(".title_link[href]")
    url = _to_absolute_url(subject_anchor.get("href")) if subject_anchor is not None else None
    if not url:
        return fallback_date

    fetched_date = _extract_cafe_article_date(url)
    if fetched_date:
        return fetched_date

    return fallback_date


def _extract_absolute_date(value: str | None) -> str | None:
    if not value:
        return None
    match = ABSOLUTE_DATE_PATTERN.search(value)
    if match is None:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}.{int(month):02d}.{int(day):02d}."


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


def _extract_cafe_article_date(url: str) -> str | None:
    try:
        request = Request(url, headers={"User-Agent": PLAYWRIGHT_USER_AGENT, "Referer": NAVER_BASE_URL})
        with urlopen(request, timeout=CAFE_DATE_FETCH_TIMEOUT_SEC) as response:
            html = response.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        logger.debug("Cafe article date fetch skipped. url=%s", url)
        return None
    return _extract_cafe_article_date_from_html(html)


def _extract_cafe_article_date_from_html(html: bytes | str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for selector in CAFE_ARTICLE_DATE_SELECTORS:
        for element in soup.select(selector):
            for candidate in (element.get("content"), element.get("datetime"), element.get_text(" ", strip=True)):
                normalized_date = _normalize_cafe_date_text(candidate)
                if normalized_date:
                    return normalized_date
    return None


def _is_cafe_ad_card(card) -> bool:
    if card.select_one(".link_ad, .ico_ad, a[href*='ader.naver.com']") is not None:
        return True
    if card.select_one("img[src*='searchad-phinf'], img[src*='ad-creative']") is not None:
        return True
    classes = {
        class_name.lower()
        for tag in card.find_all(True)
        for class_name in (tag.get("class") or [])
    }
    if any(_looks_like_ad_class_name(c) for c in classes):
        return True
    return _normalize_text(card.get_text(" ", strip=True)).startswith("광고 ")


def _looks_like_ad_class_name(class_name: str) -> bool:
    ad_class_names = {"ad", "ad_area", "ad_banner", "ad_box", "ad_wrap", "banner", "banner_area", "ico_ad", "link_ad", "sp_ad"}
    if class_name in ad_class_names:
        return True
    return class_name.startswith(("ad_", "ad-", "banner_", "banner-")) or class_name.endswith(("_ad", "-ad", "_banner", "-banner"))


def _to_absolute_url(href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
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
