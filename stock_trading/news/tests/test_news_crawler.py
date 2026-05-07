from datetime import datetime
import json

from django.utils import timezone

from news.models import NewsItem
from news.services.news_crawler import NewsCrawler


def test_deduplicate_removes_same_title_and_source():
    crawler = NewsCrawler()
    items = [
        {"title": "A", "source": "S1"},
        {"title": "A", "source": "S1"},
        {"title": "A", "source": "S2"},
    ]

    deduplicated = crawler.deduplicate(items)

    assert len(deduplicated) == 2


def test_classify_maps_keywords_to_expected_category():
    crawler = NewsCrawler()

    assert crawler.classify({"title": "公司公告", "summary": ""}) == NewsItem.Category.ANNOUNCEMENT
    assert crawler.classify({"title": "最新研报上调评级", "summary": ""}) == NewsItem.Category.RESEARCH
    assert crawler.classify({"title": "行业景气度回升", "summary": ""}) == NewsItem.Category.INDUSTRY
    assert crawler.classify({"title": "市场热议", "summary": ""}) == NewsItem.Category.SENTIMENT


def test_crawl_a_stock_news_normalizes_items():
    crawler = NewsCrawler(
        source_fetchers={
            "a_stock": [
                lambda stock_code: [
                    {
                        "title": "公司公告",
                        "source": "东方财富",
                        "summary": "summary",
                        "url": "https://example.com/a",
                        "published_at": datetime(2026, 4, 22, 9, 0, 0),
                    }
                ]
            ]
        }
    )

    items = crawler.crawl_a_stock_news("603063")

    assert len(items) == 1
    assert items[0]["stock_code"] == "603063"
    assert items[0]["category"] == NewsItem.Category.ANNOUNCEMENT
    assert timezone.is_aware(items[0]["published_at"])


class FakeResponse:
    def __init__(self, text="", json_data=None, status_code=200, apparent_encoding="utf-8"):
        self.text = text
        self._json_data = json_data
        self.status_code = status_code
        self.apparent_encoding = apparent_encoding
        self.encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, mapping):
        self.mapping = mapping
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        key = (url, json.dumps(params, sort_keys=True, ensure_ascii=False) if params is not None else None)
        return self.mapping[key]


def test_fetch_eastmoney_announcements_from_real_api_shape():
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    params = {
        "page_size": 10,
        "page_index": 1,
        "ann_type": "A",
        "stock_list": "603063",
        "client_source": "web",
    }
    session = FakeSession(
        {
            (
                url,
                json.dumps(params, sort_keys=True, ensure_ascii=False),
            ): FakeResponse(
                json_data={
                    "data": {
                        "list": [
                            {
                                "art_code": "AN202604211821390725",
                                "title": "禾望电气:董事会决议公告",
                                "display_time": "2026-04-21 19:08:39:390",
                                "columns": [{"column_name": "董事会决议公告"}],
                            }
                        ]
                    }
                }
            )
        }
    )
    crawler = NewsCrawler(session=session)

    items = crawler._fetch_eastmoney_announcements("603063")

    assert len(items) == 1
    assert items[0]["source"] == "东方财富"
    assert items[0]["category"] == NewsItem.Category.ANNOUNCEMENT
    assert "AN202604211821390725" in items[0]["url"]


def test_fetch_sina_company_news_parses_links():
    url = "https://finance.sina.com.cn/realstock/company/sh603063/nc.shtml"
    html = """
    <html><body>
      <a href="https://finance.sina.com.cn/roll/2026-04-17/doc-inhutspw1348633.shtml">
        深圳市禾望电气股份有限公司关于召开2026年第二次临时..
      </a>
      <a href="https://finance.sina.com.cn/stock/relnews/cn/2026-04-16/doc-inhusvkh1611301.shtml">
        禾望电气精彩亮相长垣起重展
      </a>
    </body></html>
    """
    session = FakeSession(
        {
            (url, None): FakeResponse(text=html, apparent_encoding="GB2312"),
        }
    )
    crawler = NewsCrawler(session=session)

    items = crawler._fetch_sina_company_news("603063")

    assert len(items) == 2
    assert items[0]["source"] == "新浪财经"
    assert "finance.sina.com.cn" in items[0]["url"]


def test_fetch_aastocks_news_parses_first_page_html():
    url = "https://www.aastocks.com/en/stocks/analysis/stock-aafn/02610/0/hk-stock-news/1"
    html = """
    <div id="aafn-search-c1">
      <div ref="NOW.1513022">
        <div class="newshead4 mar2B">
          <a href="/en/stocks/analysis/stock-aafn-con/02610/AAFN/NOW.1513022/hk-stock-news">
            &lt;Results&gt; Nanshan Aluminum International Full-Year Net Profit
          </a>
        </div>
        <div class="newstime4">
          <div class="inline_block">
            <script type="text/javascript">
              document.write(ConvertToLocalTime({dt:'2026/03/27 00:18'}));
            </script>
          </div>
        </div>
        <div class="newscontent4 mar8T">
          Summary text from AASTOCKS.
        </div>
      </div>
    </div>
    """
    session = FakeSession(
        {
            (url, None): FakeResponse(text=html),
        }
    )
    crawler = NewsCrawler(session=session)

    items = crawler._fetch_aastocks_news("02610")

    assert len(items) == 1
    assert items[0]["source"] == "AASTOCKS"
    assert items[0]["title"].startswith("<Results>")
    assert items[0]["summary"] == "Summary text from AASTOCKS."
