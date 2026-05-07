from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
import re
from urllib.parse import urljoin

from django.utils import timezone
import requests
from bs4 import BeautifulSoup

from news.models import NewsItem


class NewsCrawler:
    ANNOUNCEMENT_KEYWORDS = ("公告", "披露", "通告", "結果", "业绩", "財務", "股東會")
    RESEARCH_KEYWORDS = ("研报", "研究", "评级", "目標價", "目标价", "coverage", "research")
    INDUSTRY_KEYWORDS = ("行业", "板块", "产业", "供给", "景气", "政策", "commodity", "market")

    def __init__(self, source_fetchers: dict | None = None, session: requests.Session | None = None):
        self.session = session or self._build_session()
        self.source_fetchers = source_fetchers or {
            "a_stock": [self._fetch_eastmoney_announcements, self._fetch_sina_company_news],
            "hk_stock": [self._fetch_aastocks_news],
        }

    def crawl_a_stock_news(self, stock_code: str):
        items = self._fetch_with_group("a_stock", stock_code)
        return self._normalize_items(items, stock_code)

    def crawl_hk_stock_news(self, stock_code: str):
        items = self._fetch_with_group("hk_stock", stock_code)
        return self._normalize_items(items, stock_code)

    def deduplicate(self, items):
        deduplicated = []
        seen = set()
        for item in items:
            key = (str(item["title"]).strip(), str(item["source"]).strip())
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(item)
        return deduplicated

    def classify(self, item):
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if any(keyword.lower() in haystack for keyword in self.ANNOUNCEMENT_KEYWORDS):
            return NewsItem.Category.ANNOUNCEMENT
        if any(keyword.lower() in haystack for keyword in self.RESEARCH_KEYWORDS):
            return NewsItem.Category.RESEARCH
        if any(keyword.lower() in haystack for keyword in self.INDUSTRY_KEYWORDS):
            return NewsItem.Category.INDUSTRY
        return NewsItem.Category.SENTIMENT

    def _fetch_with_group(self, group: str, stock_code: str):
        result = []
        fetchers = self.source_fetchers.get(group, [])
        if isinstance(fetchers, Callable):
            fetchers = [fetchers]
        for fetcher in fetchers:
            fetched = fetcher(stock_code)
            if fetched:
                result.extend(fetched)
        return result

    def _normalize_items(self, items: list[dict], stock_code: str):
        normalized = []
        for item in items:
            row = deepcopy(item)
            row["stock_code"] = stock_code
            row["title"] = str(row["title"]).strip()
            row["source"] = str(row["source"]).strip()
            row["summary"] = str(row.get("summary", "")).strip()
            row["url"] = str(row["url"]).strip()
            row["published_at"] = self._normalize_datetime(row.get("published_at"))
            row["category"] = row.get("category") or self.classify(row)
            normalized.append(row)
        return self.deduplicate(normalized)

    def _build_session(self):
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            }
        )
        return session

    def _fetch_eastmoney_announcements(self, stock_code: str):
        url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
        params = {
            "page_size": 10,
            "page_index": 1,
            "ann_type": "A",
            "stock_list": stock_code,
            "client_source": "web",
        }
        response = self.session.get(url, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        items = []
        for row in payload.get("data", {}).get("list", []):
            art_code = row.get("art_code", "")
            items.append(
                {
                    "title": row.get("title") or row.get("title_ch") or "",
                    "source": "东方财富",
                    "summary": " / ".join(column.get("column_name", "") for column in row.get("columns", []) if column.get("column_name")),
                    "url": f"https://data.eastmoney.com/notices/detail/{stock_code}/{art_code}.html",
                    "published_at": self._parse_eastmoney_datetime(row.get("display_time") or row.get("notice_date")),
                    "category": NewsItem.Category.ANNOUNCEMENT,
                }
            )
        return items

    def _fetch_sina_company_news(self, stock_code: str):
        prefix = "sh" if stock_code.startswith(("5", "6", "9")) else "sz"
        url = f"https://finance.sina.com.cn/realstock/company/{prefix}{stock_code}/nc.shtml"
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "gb18030"
        soup = BeautifulSoup(response.text, "html.parser")

        items = []
        seen = set()
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            if "/stock/relnews/" not in href and "/roll/" not in href:
                continue
            title = anchor.get_text(" ", strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            items.append(
                {
                    "title": title,
                    "source": "新浪财经",
                    "summary": "",
                    "url": href,
                    "published_at": self._parse_datetime_from_url(href),
                }
            )
            if len(items) >= 10:
                break
        return items

    def _fetch_aastocks_news(self, stock_code: str):
        url = f"https://www.aastocks.com/en/stocks/analysis/stock-aafn/{stock_code}/0/hk-stock-news/1"
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        container = soup.select_one("#aafn-search-c1")
        if container is None:
            return []

        items = []
        for block in container.select("div[ref]"):
            title_anchor = block.select_one(".newshead4 a[href]")
            summary_node = block.select_one(".newscontent4")
            if title_anchor is None:
                continue
            title = title_anchor.get_text(" ", strip=True)
            href = title_anchor.get("href", "")
            href = urljoin("https://www.aastocks.com", href)
            summary = summary_node.get_text(" ", strip=True) if summary_node else ""
            published_at = self._parse_aastocks_datetime(block)
            items.append(
                {
                    "title": title,
                    "source": "AASTOCKS",
                    "summary": summary,
                    "url": href,
                    "published_at": published_at,
                }
            )
        return items

    def _normalize_datetime(self, value):
        if value is None:
            return timezone.now()
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    def _parse_eastmoney_datetime(self, value: str | None):
        if not value:
            return timezone.now()
        cleaned = str(value).strip()
        if cleaned.count(":") == 3:
            cleaned = cleaned.rsplit(":", 1)[0]
        return self._normalize_datetime(cleaned)

    def _parse_datetime_from_url(self, url: str):
        match = re.search(r"/(20\d{2})-(\d{2})-(\d{2})/", url)
        if not match:
            return timezone.now()
        return self._normalize_datetime(f"{match.group(1)}-{match.group(2)}-{match.group(3)} 00:00:00")

    def _parse_aastocks_datetime(self, block):
        scripts = block.select(".newstime4 script")
        for script in scripts:
            text = script.get_text(" ", strip=True)
            match = re.search(r"dt:'(?P<dt>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})'", text)
            if match:
                return self._normalize_datetime(match.group("dt").replace("/", "-"))
        return timezone.now()
