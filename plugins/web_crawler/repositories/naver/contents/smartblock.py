import sys
import asyncio
import logging

from collections.abc import Iterator
from typing import TypeVar
from urllib.parse import quote, unquote, urlencode, urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from web_crawler.config import Settings
from web_crawler.models import SearchResultsBundle, SmartBlockRow
from web_crawler.repositories.base import TargetContents

logger = logging.getLogger(__name__)

NAVER_BASE_URL = "https://search.naver.com"
NAVER_SEARCH_URL = f"{NAVER_BASE_URL}/search.naver"
DEFAULT_MAX_ROWS = 10

HEADER_TITLE_SELECTORS = (
    "[data-sds-comp='Header'] span.sds-comps-text-type-headline1",
    "[data-sds-comp='Header'] h2.sds-comps-text",
    ".mod_title_area h2.title",
)

IGNORED_BLOCK_CLASS_NAMES = {
    "_scrollLog",
    "_scrollLogEndline",
    "_search_option_detail_wrap",
    "api_sc_page_wrap",
    "ct_feed_wrap",
}
# 더보기 Element
FOOTER_MORE_CONTAINER_SELECTOR = "div[data-template-id='footer'][data-template-type='more']"
FOOTER_MORE_ANCHOR_SELECTOR = f"{FOOTER_MORE_CONTAINER_SELECTOR} a[href]"
FOOTER_MORE_SUBJECT_SELECTOR = ".fds-comps-footer-more-subject"
FOOTER_MORE_BUTTON_SELECTOR = ".fds-comps-footer-more-button-text"

FALLBACK_MORE_URL_SELECTORS = (
    "a[href*='ad.search.naver.com/search.naver'][href*='where=ad']",
    "a[href*='page=2']",
    "a[href*='where=image']",
    "a[href*='where=influencer']",
    "a[href*='map.naver.com']",
    "a[href*='search.shopping.naver.com']",
    "a[href^='#lb_api=']",
)

PLAYWRIGHT_VIEWPORT = {
    "width": 1080,
    "height": 1920,
}
PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

T = TypeVar("T")


class SmartBlockContents(TargetContents):
    task_name = "smartblock"

    def __init__(
        self,
        max_rows: int = DEFAULT_MAX_ROWS,
        max_concurrency: int | None = None,
        timeout_ms: int | None = None,
        render_wait_ms: int | None = None,
    ) -> None:
        self.max_rows = max(1, max_rows)
        self.max_concurrency = max(1, max_concurrency if max_concurrency is not None else Settings.get_naver_max_concurrency())
        self.timeout_ms = timeout_ms if timeout_ms is not None else Settings.get_naver_timeout_ms()
        self.render_wait_ms = render_wait_ms if render_wait_ms is not None else Settings.get_naver_render_wait_ms()

    async def run(self, keywords: list[str]) -> SearchResultsBundle:
        logger.info("SmartBlock task started. keywords=%s", len(keywords))

        results = SearchResultsBundle()
        if not keywords:
            logger.info("SmartBlock task finished. rows=%s", 0)
            return results

        async with async_playwright() as playwright:
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
                            results.smartblock_rows.extend(rows)
                finally:
                    await context.close()
            finally:
                await browser.close()

        logger.info("SmartBlock task finished. rows=%s", len(results.smartblock_rows))
        return results

    async def _collect_keyword(self, context, keyword: str) -> list[SmartBlockRow]:
        page = None

        try:
            page = await context.new_page()

            await page.goto(
                _build_main_search_url(query=keyword),
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            await page.wait_for_timeout(self.render_wait_ms)

            return await _parse_smartblock_rows(keyword, page, self.max_rows)
        
        except Exception:
            logger.exception("SmartBlock collection failed. keyword=%s", keyword)
            return []
        
        finally:
            if page is not None:
                await page.close()


def _build_main_search_url(query: str) -> str:
    return f"{NAVER_SEARCH_URL}?{urlencode({'where': 'nexearch', 'query': query})}"


async def _parse_smartblock_rows(
    keyword: str,
    page,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> list[SmartBlockRow]:
    html = await page.content()
    page_url = page.url

    soup = BeautifulSoup(html, "html.parser")
    row_limit = max(1, max_rows)
    rows: list[SmartBlockRow] = []

    for block in _iter_smart_blocks(soup):
        rows.append(
            SmartBlockRow(
                keyword=keyword,
                order=len(rows) + 1,
                title=_extract_block_title(block) or "None",
                url=_extract_block_more_url(block, page_url) or "None",
            )
        )
        if len(rows) >= row_limit:
            break

    return rows


def _iter_smart_blocks(soup: BeautifulSoup) -> Iterator:
    main_pack = soup.select_one("#main_pack")
    if main_pack is None:
        return

    for child in main_pack.find_all(recursive=False):
        if getattr(child, "name", None) is None:
            continue
        if not _is_smart_block(child):
            continue
        if not _normalize_text(child.get_text(" ", strip=True)):
            continue
        yield child


def _is_smart_block(block) -> bool:
    if block.name in {"script", "link"}:
        return False

    classes = set(block.get("class") or [])
    if classes.intersection(IGNORED_BLOCK_CLASS_NAMES):
        return False

    if block.name == "section":
        return block.select_one(".pcPowerLink_dacf, [id^='pcPowerLink']") is not None

    if block.get("data-slog-container"):
        return True

    return False


def _extract_block_title(block) -> str | None:
    if block.name == "section":
        return _extract_ad_block_title(block)

    for selector in HEADER_TITLE_SELECTORS:
        element = block.select_one(selector)
        title = _extract_text(element)
        if title:
            return title

    return None


def _extract_ad_block_title(block) -> str | None:
    title_element = block.select_one(".mod_title_area .title")
    title = _extract_text(title_element)
    
    if not title:
        return None
    
    return f"{title}"


def _extract_block_more_url(block, page_url: str) -> str | None:
    footer_anchor = block.select_one(FOOTER_MORE_ANCHOR_SELECTOR)
    if footer_anchor is not None:
        footer_subject = footer_anchor.select_one(FOOTER_MORE_SUBJECT_SELECTOR)
        footer_button = footer_anchor.select_one(FOOTER_MORE_BUTTON_SELECTOR)
        if _extract_text(footer_subject) and _extract_text(footer_button):
            resolved_url = _resolve_anchor_url(footer_anchor, page_url)
            if resolved_url is not None:
                return _finalize_block_more_url(resolved_url)

    for selector in FALLBACK_MORE_URL_SELECTORS:
        fallback_anchor = block.select_one(selector)
        if fallback_anchor is None:
            continue

        resolved_url = _resolve_anchor_url(fallback_anchor, page_url)
        if resolved_url is not None:
            return _finalize_block_more_url(resolved_url)

    return None


def _resolve_anchor_url(anchor, page_url: str) -> str | None:
    lb_trigger = anchor.get("data-lb-trigger")
    resolved_lb_trigger = _resolve_lb_trigger_url(page_url, lb_trigger)

    if resolved_lb_trigger:
        return resolved_lb_trigger

    return _resolve_url(page_url, anchor.get("href"))


def _resolve_url(page_url: str, href: str | None) -> str | None:
    if href is None:
        return None

    # Javascript 링크나 빈 링크는 무시
    href = href.strip()
    if not href or href == "#" or href.startswith("javascript:"):
        return None

    return urljoin(page_url or NAVER_SEARCH_URL, href)


def _resolve_lb_trigger_url(page_url: str, lb_trigger: str | None) -> str | None:
    if lb_trigger is None:
        return None

    lb_trigger = lb_trigger.strip()
    if not lb_trigger or lb_trigger.startswith("javascript:"):
        return None

    base_url = (page_url or NAVER_SEARCH_URL).split("#", 1)[0]
    resolved_trigger = urljoin(page_url or NAVER_SEARCH_URL, lb_trigger)
    return f"{base_url}#lb_api={quote(resolved_trigger, safe='')}"


def _finalize_block_more_url(url: str) -> str:
    decoded_url = unquote(url)
    if "#lb_api=" not in decoded_url:
        return url

    if "ssc=tab.itb.qab" not in decoded_url or "faq_opened=1" in decoded_url:
        return url

    base_url, lb_api = decoded_url.split("#lb_api=", 1)
    separator = "&" if "?" in lb_api else "?"
    lb_api = f"{lb_api}{separator}faq_opened=1"
    return f"{base_url}#lb_api={quote(lb_api, safe='')}"


def _extract_text(element) -> str:
    if element is None:
        return ""
    return _normalize_text(element.get_text(" ", strip=True))


def _normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(text.split())


def _chunked(values: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]
