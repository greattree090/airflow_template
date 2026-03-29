import asyncio
import logging
from collections.abc import Iterator
from datetime import datetime
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
BLOG_TAB_TARGET_SELECTOR = "section.sc_new.sp_nblog [data-template-id='ugcItem'], div._fe_view_power_content"
BLOG_DATE_FETCH_TIMEOUT_SEC = 5.0
BLOG_ARTICLE_DATE_SELECTORS = (
    "span.se_publishDate.pcol2",
    ".se_publishDate.pcol2",
    ".se_publishDate",
    "meta[property='article:published_time']",
    "meta[name='article:published_time']",
    "meta[property='og:article:published_time']",
    "meta[name='og:article:published_time']",
    "time[datetime]",
)
BLOG_ARTICLE_IFRAME_SELECTORS = (
    "iframe#mainFrame[src]",
    "iframe[src*='PostView.naver']",
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
        except Exception:
            logger.exception("Blog collection failed. keyword=%s", keyword)
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
        if _is_blog_ad_card(card):
            continue
        row = _parse_blog_card(keyword, card, len(rows) + 1)
        if row is None:
            continue
        rows.append(row)
        if len(rows) >= row_limit:
            break

    return rows


def _parse_blog_card(keyword: str, card, order: int) -> BlogRow | None:
    author_anchor = card.select_one(".sds-comps-profile-info-title-text a[href]")
    date_element = card.select_one(".sds-comps-profile-info-subtext")
    if author_anchor is None or date_element is None:
        return None

    blog_name = _normalize_text(author_anchor.get_text(" ", strip=True))
    author_url = _to_absolute_url(author_anchor.get("href"))
    if not blog_name or not author_url:
        return None

    subject_anchor = _select_blog_subject_anchor(card, blog_name, author_url)
    if subject_anchor is None:
        return None

    subject = _normalize_text(subject_anchor.get_text(" ", strip=True))
    url = _to_absolute_url(subject_anchor.get("href"))
    date = _extract_blog_card_date(card, date_element, url)
    if not subject or not url or not date:
        return None

    return BlogRow(keyword=keyword, order=order, date=date, blog_name=blog_name, subject=subject, url=url)


def _extract_blog_card_date(_card, date_element, url: str | None) -> str:
    displayed_date = _normalize_text(date_element.get_text(" ", strip=True))
    normalized = _normalize_blog_date_text(displayed_date)
    if normalized:
        return normalized

    if not url:
        return displayed_date

    fetched_date = _extract_blog_article_date(url)
    if fetched_date:
        return fetched_date

    return displayed_date


def _normalize_blog_date_text(value: str | None) -> str | None:
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

    for date_format in BLOG_ABSOLUTE_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, date_format).strftime("%Y.%m.%d.")
        except ValueError:
            continue

    return None


def _extract_blog_article_date(url: str) -> str | None:
    outer_html = _fetch_blog_html(url)
    if outer_html is None:
        return None

    outer_date = _extract_blog_article_date_from_html(outer_html)
    if outer_date:
        return outer_date

    article_view_url = _extract_blog_article_view_url_from_html(outer_html)
    if article_view_url is None:
        return None

    inner_html = _fetch_blog_html(article_view_url, referer=url)
    if inner_html is None:
        return None

    return _extract_blog_article_date_from_html(inner_html)


def _fetch_blog_html(url: str, referer: str = NAVER_BASE_URL) -> bytes | None:
    try:
        request = Request(url, headers={"User-Agent": PLAYWRIGHT_USER_AGENT, "Referer": referer})
        with urlopen(request, timeout=BLOG_DATE_FETCH_TIMEOUT_SEC) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        logger.debug("Blog article fetch skipped. url=%s", url)
        return None


def _extract_blog_article_view_url_from_html(html: bytes | str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for selector in BLOG_ARTICLE_IFRAME_SELECTORS:
        for iframe in soup.select(selector):
            iframe_src = _normalize_text(iframe.get("src"))
            if iframe_src:
                return urljoin(NAVER_BLOG_URL, iframe_src)
    return None


def _extract_blog_article_date_from_html(html: bytes | str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for selector in BLOG_ARTICLE_DATE_SELECTORS:
        for element in soup.select(selector):
            for candidate in (element.get("content"), element.get("datetime"), element.get_text(" ", strip=True)):
                normalized_date = _normalize_blog_date_text(candidate)
                if normalized_date:
                    return normalized_date
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
