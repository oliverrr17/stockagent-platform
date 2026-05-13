# Futu HK Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Futu OpenD-based Hong Kong real-account trade ingestion path with order-level fee capture, switch HSBC/Futu scheduling to a Hong Kong trading calendar, and document the runtime and fee-model caveats clearly.

**Architecture:** Extend `TradeRecord` to store broker order identifiers and raw fee detail, then add a focused `FutuConnector` that turns Futu historical orders plus fee-query output into normalized trade payloads. Wire that connector into a new ingestion task and management command, update daily orchestration and Hong Kong trading-day helpers, and keep the existing portfolio/accounting stack unchanged by continuing to populate `commission`, `stamp_duty`, and `other_fees`.

**Tech Stack:** Django ORM, Django management commands, Celery tasks, pytest, SQLite/PostgreSQL-compatible migrations, `futu-api`, Tushare trading calendar

---

### Task 1: Extend trade persistence for Futu broker metadata

**Files:**
- Modify: `stock_trading/trades/models.py`
- Modify: `stock_trading/trades/services/trade_recorder.py`
- Modify: `stock_trading/trades/tests/test_trade_recorder.py`
- Create: `stock_trading/trades/migrations/0004_traderecord_futu_fields.py`
- Test: `stock_trading/trades/tests/test_trade_recorder.py`

- [ ] **Step 1: Write failing recorder tests for Futu broker fields and idempotency**

Add these tests to `stock_trading/trades/tests/test_trade_recorder.py`:

```python
@pytest.mark.django_db
def test_record_trade_is_idempotent_for_futu_external_trade_id():
    recorder = TradeRecorder()
    payload = {
        "stock_code": "00700",
        "stock_name": "Tencent",
        "market": TradeRecord.Market.HK_STOCK,
        "direction": TradeRecord.Direction.BUY,
        "price": Decimal("320.5000"),
        "quantity": 100,
        "trade_time": "2026-05-12T14:23:58+08:00",
        "source": TradeRecord.Source.FUTU_API,
        "external_trade_id": "900000000123456789",
        "commission": Decimal("30.0000"),
        "stamp_duty": Decimal("100.0000"),
        "other_fees": Decimal("27.7000"),
        "fee_details": [{"fee_name": "Commission", "fee_amount": "30.00"}],
    }

    first_record, first_created = recorder.record_trade(payload)
    second_record, second_created = recorder.record_trade(payload)

    assert first_created is True
    assert second_created is False
    assert first_record.pk == second_record.pk
    assert TradeRecord.objects.filter(source=TradeRecord.Source.FUTU_API).count() == 1


@pytest.mark.django_db
def test_record_trade_persists_futu_fee_details():
    recorder = TradeRecorder()

    record, created = recorder.record_trade(
        {
            "stock_code": "00388",
            "stock_name": "HKEX",
            "market": TradeRecord.Market.HK_STOCK,
            "direction": TradeRecord.Direction.SELL,
            "price": Decimal("299.8000"),
            "quantity": 200,
            "trade_time": "2026-05-12T15:01:00+08:00",
            "source": TradeRecord.Source.FUTU_API,
            "external_trade_id": "900000000123456790",
            "commission": Decimal("35.0000"),
            "stamp_duty": Decimal("60.0000"),
            "other_fees": Decimal("18.2200"),
            "fee_details": [
                {"fee_name": "Commission", "fee_amount": "35.00"},
                {"fee_name": "Stamp Duty", "fee_amount": "60.00"},
                {"fee_name": "Trading Fee", "fee_amount": "3.39"},
            ],
        }
    )

    assert created is True
    assert record.external_trade_id == "900000000123456790"
    assert record.fee_details[0]["fee_name"] == "Commission"
```

- [ ] **Step 2: Run the recorder tests to verify they fail**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_trade_recorder.py -v
```

Expected: FAIL because `TradeRecord.Source.FUTU_API`, `external_trade_id`, and `fee_details` do not exist yet, and `TradeRecorder` does not deduplicate Futu by broker ID.

- [ ] **Step 3: Add the Futu fields and recorder logic**

Update `stock_trading/trades/models.py` so `TradeRecord` includes the new source and fields:

```python
class Source(models.TextChoices):
    THS = "THS", "同花顺"
    HSBC_EMAIL = "HSBC_EMAIL", "汇丰邮件"
    FUTU_API = "FUTU_API", "富途接口"
    MANUAL = "MANUAL", "手动录入"


external_trade_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
fee_details = models.JSONField(default=list, blank=True)
```

Update `stock_trading/trades/services/trade_recorder.py` so Futu deduplication uses `external_trade_id` when available:

```python
    def record_trade(self, record_data: dict):
        intent_data = record_data.get("intent_snapshot")
        normalized = self._normalize_record_data(record_data)
        existing = self._find_existing_trade(normalized)
        if existing is not None:
            if intent_data:
                self.sync_intent_snapshot(existing, intent_data)
            return existing, False
```

```python
    def _find_existing_trade(self, record_data: dict):
        source = str(record_data.get("source", "")).strip()
        external_trade_id = str(record_data.get("external_trade_id", "")).strip()
        if source == TradeRecord.Source.FUTU_API and external_trade_id:
            return TradeRecord.objects.filter(
                source=TradeRecord.Source.FUTU_API,
                external_trade_id=external_trade_id,
            ).order_by("-id").first()

        return TradeRecord.objects.filter(**self._unique_lookup(record_data)).order_by("-id").first()
```

Also normalize the new fields:

```python
        normalized["external_trade_id"] = str(normalized.get("external_trade_id", "")).strip()
        normalized["fee_details"] = list(normalized.get("fee_details") or [])
```

Create `stock_trading/trades/migrations/0004_traderecord_futu_fields.py` to add the source choice and the two new fields.

- [ ] **Step 4: Run the recorder tests again to verify they pass**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_trade_recorder.py -v
```

Expected: PASS

### Task 2: Add a Hong Kong trading-day helper and move HSBC onto it

**Files:**
- Modify: `stock_trading/config/trading_calendar.py`
- Modify: `tests/test_trading_calendar.py`
- Modify: `stock_trading/trades/tasks.py`
- Modify: `stock_trading/trades/tests/test_tasks.py`
- Test: `tests/test_trading_calendar.py`
- Test: `stock_trading/trades/tests/test_tasks.py`

- [ ] **Step 1: Write failing tests for Hong Kong trading-day lookup**

Add to `tests/test_trading_calendar.py`:

```python
from config.trading_calendar import is_cn_equity_trading_day, is_hk_equity_trading_day
```

```python
def test_hk_trading_calendar_marks_weekend_as_closed():
    assert is_hk_equity_trading_day(date(2026, 4, 25), token="", client=None) is False


def test_hk_trading_calendar_uses_tushare_trade_cal_when_available():
    client = FakeClient([{"cal_date": "20260513", "is_open": 0}])

    assert is_hk_equity_trading_day(date(2026, 5, 13), token="demo", client=client) is False
    assert client.calls[0]["exchange"] == "XHKG"
    assert client.calls[0]["start_date"] == "20260513"
```

- [ ] **Step 2: Write failing task tests proving HSBC now uses the HK trading calendar**

Add to `stock_trading/trades/tests/test_tasks.py`:

```python
@pytest.mark.django_db
def test_run_hsbc_email_ingestion_uses_hk_trading_day_guard(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_PORT", "993")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with (
        patch("trades.tasks.is_hk_equity_trading_day", return_value=False),
        patch("trades.tasks.EmailCrawler") as crawler_cls,
    ):
        created_count = run_hsbc_email_ingestion()

    assert created_count == 0
    crawler_cls.assert_not_called()
```

- [ ] **Step 3: Run the targeted calendar and HSBC task tests to verify they fail**

Run:

```bash
python -m pytest tests/test_trading_calendar.py stock_trading/trades/tests/test_tasks.py -k "hk_trading_calendar or hsbc_email_ingestion_uses_hk" -v
```

Expected: FAIL because `is_hk_equity_trading_day()` does not exist and HSBC still checks the CN-equity calendar helper.

- [ ] **Step 4: Implement the Hong Kong trading-day helper and switch HSBC**

Update `stock_trading/config/trading_calendar.py` by extracting the shared logic into a helper that accepts the exchange code:

```python
def is_cn_equity_trading_day(target_date: date | datetime | None = None, token: str | None = None, client=None) -> bool:
    return _is_equity_trading_day("SSE", "trading-calendar:sse", target_date, token, client)


def is_hk_equity_trading_day(target_date: date | datetime | None = None, token: str | None = None, client=None) -> bool:
    return _is_equity_trading_day("XHKG", "trading-calendar:xhkg", target_date, token, client)
```

And add:

```python
def _is_equity_trading_day(exchange: str, cache_prefix: str, target_date: date | datetime | None, token: str | None, client):
    trading_date = _normalize_date(target_date)
    if trading_date.weekday() >= 5:
        return False
    cache_key = f"{cache_prefix}:{trading_date.isoformat()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)

    token = token if token is not None else os.getenv("TUSHARE_TOKEN", "").strip()
    if client is None and token:
        try:
            import tushare as ts

            client = ts.pro_api(token)
        except Exception:
            client = None

    if client is not None:
        try:
            frame = client.trade_cal(
                exchange=exchange,
                start_date=trading_date.strftime("%Y%m%d"),
                end_date=trading_date.strftime("%Y%m%d"),
            )
            rows = frame.to_dict("records") if frame is not None else []
            if rows:
                is_open = str(rows[0].get("is_open", "0")).strip() in {"1", "True", "true"}
                cache.set(cache_key, is_open, TRADING_DAY_CACHE_TTL_SECONDS)
                return is_open
        except Exception:
            pass

    cache.set(cache_key, True, TRADING_DAY_CACHE_TTL_SECONDS)
    return True
```

Update `stock_trading/trades/tasks.py`:

```python
from config.trading_calendar import is_cn_equity_trading_day, is_hk_equity_trading_day
```

```python
    if not is_hk_equity_trading_day(today):
        logger.info("Skipping HSBC email fetch on non-trading day %s.", today)
        return 0
```

- [ ] **Step 5: Run the targeted tests again to verify they pass**

Run:

```bash
python -m pytest tests/test_trading_calendar.py stock_trading/trades/tests/test_tasks.py -k "hk_trading_calendar or hsbc_email_ingestion_uses_hk" -v
```

Expected: PASS

### Task 3: Add Futu connector tests before implementation

**Files:**
- Create: `stock_trading/trades/services/futu_connector.py`
- Create: `stock_trading/trades/tests/test_futu_connector.py`
- Test: `stock_trading/trades/tests/test_futu_connector.py`

- [ ] **Step 1: Write failing Futu connector tests for account filtering and normalization**

Create `stock_trading/trades/tests/test_futu_connector.py` with:

```python
from decimal import Decimal

import pytest

from trades.models import TradeRecord
from trades.services.futu_connector import FutuConnector
```

```python
class FakeFutuAPI:
    def __init__(self, accounts, orders, fee_rows):
        self.accounts = accounts
        self.orders = orders
        self.fee_rows = fee_rows
        self.fee_query_batches = []

    def get_acc_list(self):
        return 0, self.accounts

    def history_order_list_query(self, **kwargs):
        return 0, self.orders

    def order_fee_query(self, order_id_list, **kwargs):
        self.fee_query_batches.append(list(order_id_list))
        return 0, self.fee_rows
```

```python
def test_futu_connector_rejects_non_hk_real_account():
    connector = FutuConnector(
        {
            "acc_id": 123,
            "trade_context_factory": lambda **kwargs: FakeFutuAPI(
                accounts=[
                    {
                        "acc_id": 123,
                        "trd_env": "SIMULATE",
                        "trdmarket_auth": "HK",
                        "security_firm": "FUTUSECURITIES",
                    }
                ],
                orders=[],
                fee_rows=[],
            )
        }
    )

    with pytest.raises(ValueError, match="Hong Kong real account"):
        connector.fetch_trade_records()
```

```python
def test_futu_connector_normalizes_order_and_fee_rows():
    connector = FutuConnector(
        {
            "acc_id": 101,
            "trade_context_factory": lambda **kwargs: FakeFutuAPI(
                accounts=[
                    {
                        "acc_id": 101,
                        "trd_env": "REAL",
                        "trdmarket_auth": "HK",
                        "security_firm": "FUTUSECURITIES",
                    }
                ],
                orders=[
                    {
                        "order_id": "900000000123456789",
                        "code": "HK.00700",
                        "stock_name": "腾讯控股",
                        "trd_side": "BUY",
                        "dealt_qty": 100,
                        "dealt_avg_price": 320.5,
                        "updated_time": "2026-05-12 14:23:58",
                    }
                ],
                fee_rows=[
                    {
                        "order_id": "900000000123456789",
                        "fee_amount": 157.70,
                        "fee_details": [
                            {"fee_name": "Commission", "fee_amount": 30.00},
                            {"fee_name": "Stamp Duty", "fee_amount": 100.00},
                            {"fee_name": "Platform Fee", "fee_amount": 15.00},
                            {"fee_name": "Trading Fee", "fee_amount": 5.65},
                            {"fee_name": "SFC Transaction Levy", "fee_amount": 2.70},
                            {"fee_name": "AFRC Transaction Levy", "fee_amount": 0.15},
                            {"fee_name": "Settlement Fee", "fee_amount": 4.20},
                        ],
                    }
                ],
            )
        }
    )

    records = connector.fetch_trade_records()

    assert len(records) == 1
    record = records[0]
    assert record["stock_code"] == "00700"
    assert record["stock_name"] == "腾讯控股"
    assert record["market"] == TradeRecord.Market.HK_STOCK
    assert record["direction"] == TradeRecord.Direction.BUY
    assert record["price"] == Decimal("320.5")
    assert record["quantity"] == 100
    assert record["source"] == TradeRecord.Source.FUTU_API
    assert record["external_trade_id"] == "900000000123456789"
    assert record["commission"] == Decimal("30.00")
    assert record["stamp_duty"] == Decimal("100.00")
    assert record["other_fees"] == Decimal("27.70")
    assert record["fee_details"][0]["fee_name"] == "Commission"
```

```python
def test_futu_connector_rolls_unknown_fee_items_into_other_fees():
    connector = FutuConnector(
        {
            "acc_id": 101,
            "trade_context_factory": lambda **kwargs: FakeFutuAPI(
                accounts=[
                    {
                        "acc_id": 101,
                        "trd_env": "REAL",
                        "trdmarket_auth": "HK",
                        "security_firm": "FUTUSECURITIES",
                    }
                ],
                orders=[
                    {
                        "order_id": "900000000123456790",
                        "code": "HK.00388",
                        "stock_name": "香港交易所",
                        "trd_side": "SELL",
                        "dealt_qty": 200,
                        "dealt_avg_price": 299.8,
                        "updated_time": "2026-05-12 15:01:00",
                    }
                ],
                fee_rows=[
                    {
                        "order_id": "900000000123456790",
                        "fee_amount": 80.40,
                        "fee_details": [
                            {"fee_name": "Commission", "fee_amount": 35.00},
                            {"fee_name": "Mystery Fee", "fee_amount": 9.99},
                            {"fee_name": "Stamp Duty", "fee_amount": 20.00},
                        ],
                    }
                ],
            )
        }
    )

    record = connector.fetch_trade_records()[0]
    assert record["commission"] == Decimal("35.00")
    assert record["stamp_duty"] == Decimal("20.00")
    assert record["other_fees"] == Decimal("25.40")
```

```python
def test_futu_connector_batches_fee_queries_by_400_ids():
    orders = [
        {
            "order_id": str(900000000123450000 + index),
            "code": "HK.00700",
            "stock_name": "腾讯控股",
            "trd_side": "BUY",
            "dealt_qty": 100,
            "dealt_avg_price": 320.5,
            "updated_time": "2026-05-12 14:23:58",
        }
        for index in range(401)
    ]
    fee_rows = [
        {
            "order_id": item["order_id"],
            "fee_amount": 0,
            "fee_details": [],
        }
        for item in orders
    ]
    fake_api = FakeFutuAPI(
        accounts=[
            {
                "acc_id": 101,
                "trd_env": "REAL",
                "trdmarket_auth": "HK",
                "security_firm": "FUTUSECURITIES",
            }
        ],
        orders=orders,
        fee_rows=fee_rows,
    )
    connector = FutuConnector(
        {
            "acc_id": 101,
            "trade_context_factory": lambda **kwargs: fake_api,
        }
    )

    connector.fetch_trade_records()

    assert len(fake_api.fee_query_batches) == 2
    assert len(fake_api.fee_query_batches[0]) == 400
    assert len(fake_api.fee_query_batches[1]) == 1
```

- [ ] **Step 2: Run the Futu connector tests to verify they fail**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_futu_connector.py -v
```

Expected: FAIL because `FutuConnector` does not exist.

- [ ] **Step 3: Implement the minimal Futu connector**

Create `stock_trading/trades/services/futu_connector.py` with:

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import logging

from django.utils import timezone

from trades.models import TradeRecord


logger = logging.getLogger(__name__)


class FutuConnector:
    FEE_BATCH_SIZE = 400

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.acc_id = int(self.config.get("acc_id", 0) or 0)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = int(self.config.get("port", 11111) or 11111)
        self.security_firm = str(self.config.get("security_firm", "")).strip().upper()
        self.trade_context_factory = self.config.get("trade_context_factory")
        self.trade_context = None
```

```python
    def fetch_trade_records(self, start=None, end=None) -> list[dict]:
        context = self._get_trade_context()
        account = self._resolve_account(context)
        orders = self._fetch_orders(context, account, start=start, end=end)
        fee_map = self._fetch_fee_map(context, account, orders)
        return [self._normalize_order(order, fee_map.get(str(order["order_id"]), {})) for order in orders]
```

```python
    def _get_trade_context(self):
        if self.trade_context is not None:
            return self.trade_context
        if callable(self.trade_context_factory):
            self.trade_context = self.trade_context_factory(host=self.host, port=self.port)
            return self.trade_context

        from futu import OpenSecTradeContext

        self.trade_context = OpenSecTradeContext(host=self.host, port=self.port)
        return self.trade_context
```

```python
    def _resolve_account(self, context):
        ret, rows = context.get_acc_list()
        if ret != 0:
            raise RuntimeError("Failed to query Futu accounts.")
        for row in list(rows or []):
            if int(row.get("acc_id", 0)) != self.acc_id:
                continue
            if str(row.get("trd_env", "")).upper() != "REAL":
                raise ValueError("Configured Futu account is not a Hong Kong real account.")
            if "HK" not in str(row.get("trdmarket_auth", "")).upper():
                raise ValueError("Configured Futu account lacks Hong Kong market authorization.")
            if self.security_firm and str(row.get("security_firm", "")).strip().upper() != self.security_firm:
                raise ValueError("Configured Futu account security firm does not match.")
            return row
        raise ValueError("Configured Futu Hong Kong real account was not found.")
```

```python
    def _fetch_orders(self, context, account: dict, start=None, end=None):
        ret, rows = context.history_order_list_query(
            acc_id=int(account["acc_id"]),
            start=start,
            end=end,
        )
        if ret != 0:
            raise RuntimeError("Failed to query Futu historical orders.")

        orders = []
        for row in list(rows or []):
            if int(row.get("dealt_qty", 0) or 0) <= 0:
                continue
            orders.append(row)
        return orders
```

```python
    def _fetch_fee_map(self, context, account: dict, orders: list[dict]) -> dict[str, dict]:
        if not orders:
            return {}

        fee_map: dict[str, dict] = {}
        order_ids = [str(item["order_id"]).strip() for item in orders]
        for index in range(0, len(order_ids), self.FEE_BATCH_SIZE):
            batch_ids = order_ids[index : index + self.FEE_BATCH_SIZE]
            ret, rows = context.order_fee_query(
                order_id_list=batch_ids,
                acc_id=int(account["acc_id"]),
            )
            if ret != 0:
                raise RuntimeError("Failed to query Futu order fees.")
            for row in list(rows or []):
                fee_map[str(row.get("order_id", "")).strip()] = row
        return fee_map
```

```python
    def _normalize_order(self, order: dict, fee_row: dict) -> dict:
        fee_details = list(fee_row.get("fee_details") or [])
        commission = Decimal("0")
        stamp_duty = Decimal("0")
        other_fees = Decimal("0")

        for item in fee_details:
            fee_name = str(item.get("fee_name", "")).strip().lower()
            amount = Decimal(str(item.get("fee_amount", 0)))
            if fee_name == "commission":
                commission += amount
            elif fee_name == "stamp duty":
                stamp_duty += amount
            else:
                other_fees += amount

        stock_code = str(order.get("code", "")).split(".")[-1].zfill(5)
        updated_time = timezone.make_aware(
            datetime.strptime(str(order["updated_time"]), "%Y-%m-%d %H:%M:%S"),
            timezone.get_current_timezone(),
        )

        return {
            "stock_code": stock_code,
            "stock_name": str(order.get("stock_name") or order.get("code_name") or stock_code).strip(),
            "market": TradeRecord.Market.HK_STOCK,
            "direction": self._normalize_direction(order.get("trd_side", "")),
            "price": Decimal(str(order.get("dealt_avg_price", 0))),
            "quantity": int(order.get("dealt_qty", 0)),
            "trade_time": updated_time,
            "source": TradeRecord.Source.FUTU_API,
            "external_trade_id": str(order.get("order_id", "")).strip(),
            "commission": commission,
            "stamp_duty": stamp_duty,
            "other_fees": other_fees,
            "fee_details": fee_details,
        }
```

```python
    def _normalize_direction(self, value: str) -> str:
        text = str(value).strip().upper()
        if text in {"BUY", "TRD_SIDE_BUY"}:
            return TradeRecord.Direction.BUY
        if text in {"SELL", "TRD_SIDE_SELL"}:
            return TradeRecord.Direction.SELL
        raise ValueError(f"Unsupported Futu trade direction: {value}")
```

- [ ] **Step 4: Run the Futu connector tests again to verify they pass**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_futu_connector.py -v
```

Expected: PASS

### Task 4: Add Futu ingestion task coverage and implementation

**Files:**
- Modify: `stock_trading/trades/tasks.py`
- Modify: `stock_trading/trades/tests/test_tasks.py`
- Test: `stock_trading/trades/tests/test_tasks.py`

- [ ] **Step 1: Write failing task tests for Futu ingestion**

Add to `stock_trading/trades/tests/test_tasks.py`:

```python
from trades.tasks import run_futu_ingestion, run_hsbc_email_ingestion, run_ths_ingestion
```

```python
class FakeFutuConnector:
    def __init__(self, config):
        self.config = config

    def fetch_trade_records(self, start=None, end=None):
        return [
            {
                "stock_code": "00700",
                "stock_name": "腾讯控股",
                "market": TradeRecord.Market.HK_STOCK,
                "direction": TradeRecord.Direction.BUY,
                "price": Decimal("320.50"),
                "quantity": 100,
                "trade_time": timezone.make_aware(datetime(2026, 5, 12, 14, 23, 58), timezone.get_current_timezone()),
                "source": TradeRecord.Source.FUTU_API,
                "external_trade_id": "900000000123456789",
                "commission": Decimal("30.00"),
                "stamp_duty": Decimal("100.00"),
                "other_fees": Decimal("27.70"),
                "fee_details": [{"fee_name": "Commission", "fee_amount": "30.00"}],
            }
        ]
```

```python
@pytest.mark.django_db
def test_run_futu_ingestion_persists_hk_trade(monkeypatch):
    monkeypatch.setenv("FUTU_HOST", "127.0.0.1")
    monkeypatch.setenv("FUTU_PORT", "11111")
    monkeypatch.setenv("FUTU_ACC_ID", "101")
    monkeypatch.setenv("FUTU_SECURITY_FIRM", "FUTUSECURITIES")

    with (
        patch("trades.tasks.is_hk_equity_trading_day", return_value=True),
        patch("trades.tasks.FutuConnector", FakeFutuConnector),
    ):
        created_count = run_futu_ingestion()

    assert created_count == 1
    assert TradeRecord.objects.filter(source=TradeRecord.Source.FUTU_API, stock_code="00700").count() == 1
```

```python
@pytest.mark.django_db
def test_run_futu_ingestion_skips_non_hk_trading_day(monkeypatch):
    monkeypatch.setenv("FUTU_HOST", "127.0.0.1")
    monkeypatch.setenv("FUTU_PORT", "11111")
    monkeypatch.setenv("FUTU_ACC_ID", "101")

    with (
        patch("trades.tasks.is_hk_equity_trading_day", return_value=False),
        patch("trades.tasks.FutuConnector") as connector_cls,
    ):
        created_count = run_futu_ingestion()

    assert created_count == 0
    connector_cls.assert_not_called()
```

```python
@pytest.mark.django_db
def test_run_futu_ingestion_skips_when_config_missing(monkeypatch):
    monkeypatch.delenv("FUTU_HOST", raising=False)
    monkeypatch.delenv("FUTU_PORT", raising=False)
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)

    with patch("trades.tasks.is_hk_equity_trading_day", return_value=True):
        created_count = run_futu_ingestion()

    assert created_count == 0
```

- [ ] **Step 2: Run the targeted task tests to verify they fail**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_tasks.py -k "futu_ingestion" -v
```

Expected: FAIL because `run_futu_ingestion()` and `FutuConnector` wiring do not exist yet.

- [ ] **Step 3: Implement `run_futu_ingestion()`**

Update `stock_trading/trades/tasks.py`:

```python
from config.trading_calendar import is_cn_equity_trading_day, is_hk_equity_trading_day
from trades.services.futu_connector import FutuConnector
```

Add:

```python
def run_futu_ingestion() -> int:
    today = timezone.localdate()
    if not is_hk_equity_trading_day(today):
        logger.info("Skipping Futu trade fetch on non-trading day %s.", today)
        return 0

    host = os.getenv("FUTU_HOST", "").strip()
    port = os.getenv("FUTU_PORT", "").strip()
    acc_id = os.getenv("FUTU_ACC_ID", "").strip()
    if not all([host, port, acc_id]):
        logger.warning("FUTU_HOST, FUTU_PORT and FUTU_ACC_ID must be configured; skipping Futu trade fetch.")
        return 0

    connector = FutuConnector(
        {
            "host": host,
            "port": int(port),
            "acc_id": int(acc_id),
            "security_firm": os.getenv("FUTU_SECURITY_FIRM", "").strip(),
        }
    )
    start_date = today - timedelta(days=1)
    records = connector.fetch_trade_records(start=start_date, end=today)
    recorder = TradeRecorder()
    created_count = 0
    for record in records:
        _, created = recorder.record_trade(record)
        created_count += int(created)
    return created_count
```

And add a task wrapper:

```python
@shared_task
def fetch_futu_trades() -> int:
    return run_futu_ingestion()
```

- [ ] **Step 4: Run the targeted task tests again to verify they pass**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_tasks.py -k "futu_ingestion" -v
```

Expected: PASS

### Task 5: Add a dedicated Futu management command

**Files:**
- Create: `stock_trading/trades/management/commands/fetch_futu_trades_now.py`
- Create: `stock_trading/trades/tests/test_management_command_futu.py`
- Test: `stock_trading/trades/tests/test_management_command_futu.py`

- [ ] **Step 1: Write failing management-command tests**

Create `stock_trading/trades/tests/test_management_command_futu.py`:

```python
from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from trades.models import TradeRecord
```

```python
class FakeFutuCommandConnector:
    def __init__(self, config):
        self.config = config

    def fetch_trade_records(self, start=None, end=None):
        return [
            {
                "stock_code": "00700",
                "stock_name": "腾讯控股",
                "market": TradeRecord.Market.HK_STOCK,
                "direction": TradeRecord.Direction.BUY,
                "price": Decimal("320.50"),
                "quantity": 100,
                "trade_time": timezone.now(),
                "source": TradeRecord.Source.FUTU_API,
                "external_trade_id": "900000000123456789",
                "commission": Decimal("30.00"),
                "stamp_duty": Decimal("100.00"),
                "other_fees": Decimal("27.70"),
                "fee_details": [{"fee_name": "Commission", "fee_amount": "30.00"}],
            }
        ]
```

```python
@pytest.mark.django_db
def test_futu_management_command_persists_trades(capsys):
    with patch("trades.management.commands.fetch_futu_trades_now.FutuConnector", FakeFutuCommandConnector):
        call_command(
            "fetch_futu_trades_now",
            host="127.0.0.1",
            port=11111,
            acc_id=101,
        )

    captured = capsys.readouterr()
    assert "created 1 new TradeRecord row" in captured.out
    assert TradeRecord.objects.filter(source=TradeRecord.Source.FUTU_API).count() == 1
```

```python
@pytest.mark.django_db
def test_futu_management_command_dry_run_outputs_json(tmp_path, capsys):
    output_file = tmp_path / "futu_payload.json"
    with patch("trades.management.commands.fetch_futu_trades_now.FutuConnector", FakeFutuCommandConnector):
        call_command(
            "fetch_futu_trades_now",
            dry_run=True,
            json=True,
            output_file=str(output_file),
            host="127.0.0.1",
            port=11111,
            acc_id=101,
        )

    captured = capsys.readouterr()
    assert '"stock_code": "00700"' in captured.out
    assert "dry-run only" in captured.out
    payload = json.loads(Path(output_file).read_text(encoding="utf-8"))
    assert payload[0]["external_trade_id"] == "900000000123456789"
    assert TradeRecord.objects.count() == 0
```

- [ ] **Step 2: Run the Futu management-command tests to verify they fail**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_management_command_futu.py -v
```

Expected: FAIL because `fetch_futu_trades_now` does not exist.

- [ ] **Step 3: Implement `fetch_futu_trades_now`**

Create `stock_trading/trades/management/commands/fetch_futu_trades_now.py`:

```python
from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from trades.services.futu_connector import FutuConnector
from trades.services.trade_recorder import TradeRecorder
```

Add arguments:

```python
    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Fetch and print normalized trades without saving them.")
        parser.add_argument("--json", action="store_true", help="Print normalized trade payload as JSON.")
        parser.add_argument("--output-file", default="", help="Write normalized trades to a UTF-8 JSON file.")
        parser.add_argument("--since-days", type=int, default=1, help="Fetch orders since N days ago. Default: 1")
        parser.add_argument("--host", default="", help="Override FUTU_HOST.")
        parser.add_argument("--port", type=int, default=0, help="Override FUTU_PORT.")
        parser.add_argument("--acc-id", dest="acc_id", type=int, default=0, help="Override FUTU_ACC_ID.")
        parser.add_argument("--security-firm", default="", help="Override FUTU_SECURITY_FIRM.")
```

And implement `handle()` plus serializer:

```python
    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        host = options["host"].strip() or os.getenv("FUTU_HOST", "").strip()
        port = options["port"] or int(os.getenv("FUTU_PORT", "11111"))
        acc_id = options["acc_id"] or int(os.getenv("FUTU_ACC_ID", "0"))
        if not host or not acc_id:
            raise CommandError("FUTU_HOST and FUTU_ACC_ID must be configured.")

        connector = FutuConnector(
            {
                "host": host,
                "port": port,
                "acc_id": acc_id,
                "security_firm": options["security_firm"].strip() or os.getenv("FUTU_SECURITY_FIRM", "").strip(),
            }
        )
        since_date = timezone.localdate() - timedelta(days=max(options["since_days"], 0))
        records = connector.fetch_trade_records(start=since_date, end=timezone.localdate())
        serialized = [self._serialize_trade(item) for item in records]

        output_file = options["output_file"].strip()
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote normalized Futu payload to {output_path}"))

        if options["json"]:
            self.stdout.write(json.dumps(serialized, ensure_ascii=False, indent=2))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Fetched {len(records)} Futu trade(s); dry-run only."))
            return

        recorder = TradeRecorder()
        created_count = 0
        for record in records:
            _, created = recorder.record_trade(record)
            created_count += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Fetched {len(records)} Futu trade(s); created {created_count} new TradeRecord row(s)."
            )
        )

    def _serialize_trade(self, trade: dict) -> dict:
        serialized = dict(trade)
        if "trade_time" in serialized and hasattr(serialized["trade_time"], "isoformat"):
            serialized["trade_time"] = serialized["trade_time"].isoformat()
        for key in ("price", "commission", "stamp_duty", "other_fees"):
            if key in serialized:
                serialized[key] = str(serialized[key])
        return serialized
```

- [ ] **Step 4: Run the Futu management-command tests again to verify they pass**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_management_command_futu.py -v
```

Expected: PASS

### Task 6: Wire Futu into daily ingestion orchestration

**Files:**
- Modify: `stock_trading/trades/management/commands/run_daily_ingestion_now.py`
- Modify: `stock_trading/trades/tests/test_management_command_daily_ingestion.py`
- Test: `stock_trading/trades/tests/test_management_command_daily_ingestion.py`

- [ ] **Step 1: Write failing daily-ingestion tests for Futu summary output**

Update `stock_trading/trades/tests/test_management_command_daily_ingestion.py`:

```python
def test_daily_ingestion_command_runs_all_paths(capsys):
    with (
        patch("trades.management.commands.run_daily_ingestion_now.run_ths_ingestion", return_value=2),
        patch("trades.management.commands.run_daily_ingestion_now.run_hsbc_email_ingestion", return_value=1),
        patch("trades.management.commands.run_daily_ingestion_now.run_futu_ingestion", return_value=3),
        patch("trades.management.commands.run_daily_ingestion_now.refresh_market_price_snapshots", return_value={"securities": 3, "snapshots_written": 6}),
    ):
        call_command("run_daily_ingestion_now")

    captured = capsys.readouterr()
    assert "THS created 2 trade(s)" in captured.out
    assert "HSBC created 1 trade(s)" in captured.out
    assert "FUTU created 3 trade(s)" in captured.out
```

```python
def test_daily_ingestion_command_reports_futu_failure(capsys):
    with (
        patch("trades.management.commands.run_daily_ingestion_now.run_ths_ingestion", return_value=2),
        patch("trades.management.commands.run_daily_ingestion_now.run_hsbc_email_ingestion", return_value=1),
        patch("trades.management.commands.run_daily_ingestion_now.run_futu_ingestion", side_effect=RuntimeError("opend unavailable")),
        patch("trades.management.commands.run_daily_ingestion_now.refresh_market_price_snapshots", return_value={"securities": 3, "snapshots_written": 6}),
    ):
        call_command("run_daily_ingestion_now", json=True)

    captured = capsys.readouterr()
    assert '"futu_error": "opend unavailable"' in captured.out
```

- [ ] **Step 2: Run the daily-ingestion tests to verify they fail**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_management_command_daily_ingestion.py -v
```

Expected: FAIL because `run_daily_ingestion_now` does not call `run_futu_ingestion()` or report Futu results.

- [ ] **Step 3: Implement Futu orchestration support**

Update `stock_trading/trades/management/commands/run_daily_ingestion_now.py`:

```python
from trades.tasks import run_futu_ingestion, run_hsbc_email_ingestion, run_ths_ingestion
```

Add a skip flag:

```python
        parser.add_argument("--skip-futu", action="store_true", help="Skip Futu ingestion.")
```

And add summary/error handling:

```python
        if not options["skip_futu"]:
            try:
                summary["futu_created_count"] = int(run_futu_ingestion())
            except Exception as exc:
                errors["futu_error"] = str(exc)
```

```python
        if "futu_created_count" in summary:
            parts.append(f"FUTU created {summary['futu_created_count']} trade(s)")
```

```python
        if "futu_error" in errors:
            parts.append(f"FUTU error: {errors['futu_error']}")
```

- [ ] **Step 4: Run the daily-ingestion tests again to verify they pass**

Run:

```bash
python -m pytest stock_trading/trades/tests/test_management_command_daily_ingestion.py -v
```

Expected: PASS

### Task 7: Add dependency and runtime documentation for Futu and Hong Kong trading days

**Files:**
- Modify: `environment.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/daily-ingestion.md`

- [ ] **Step 1: Add the runtime dependency**

Update `environment.yml` under `pip:`:

```yaml
      - futu-api==9.4.5408
```

- [ ] **Step 2: Add Futu environment variables**

Update `.env.example`:

```env
# Optional Futu OpenD Hong Kong trade ingestion.
FUTU_HOST=127.0.0.1
FUTU_PORT=11111
FUTU_ACC_ID=123456789
FUTU_SECURITY_FIRM=FUTUSECURITIES
FUTU_MARKET=HK
FUTU_FETCH_HOUR=18
FUTU_FETCH_MINUTE=35
# FUTU_TRADE_PWD_MD5=
```

- [ ] **Step 3: Update the README**

Add to `README.md`:

```markdown
### Optional Futu Hong Kong Trade Ingestion

The project can ingest Hong Kong real-account trades from Futu using `OpenD + futu-api`.

Requirements:

- a running OpenD instance
- a configured Hong Kong real account
- `FUTU_HOST`, `FUTU_PORT`, and `FUTU_ACC_ID` set in `.env`

Fee handling:

- persisted fee totals are derived from broker-returned `fee_details`
- `commission`, `stamp_duty`, and `other_fees` are normalized accounting fields
- raw broker fee details are also persisted for auditability

Important:

- example fee calculations are illustrative only
- actual commission, platform fees, promotions, and product-type charges vary by account
- broker-returned `fee_details` is the source of truth for actual persisted costs
```

- [ ] **Step 4: Update the scheduler runbook**

Update `docs/daily-ingestion.md` so the supported paths and schedule defaults include Futu:

```markdown
- Futu OpenD Hong Kong trade ingestion
```

```markdown
- Futu: `18:35`
```

```env
FUTU_FETCH_HOUR=18
FUTU_FETCH_MINUTE=35
```

Also document:

- OpenD must be running
- HSBC and Futu now follow the Hong Kong trading calendar
- if `TUSHARE_TOKEN` is not configured, holiday handling falls back to weekday approximation

### Task 8: Run focused regression coverage and commit the feature slice

**Files:**
- Modify as needed from earlier tasks

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
python -m pytest \
  tests/test_trading_calendar.py \
  stock_trading/trades/tests/test_trade_recorder.py \
  stock_trading/trades/tests/test_futu_connector.py \
  stock_trading/trades/tests/test_tasks.py \
  stock_trading/trades/tests/test_management_command_futu.py \
  stock_trading/trades/tests/test_management_command_daily_ingestion.py -v
```

Expected: PASS

- [ ] **Step 2: Run the broader trades test suite**

Run:

```bash
python -m pytest stock_trading/trades/tests -v
```

Expected: PASS

- [ ] **Step 3: Commit the completed feature**

Run:

```bash
git add \
  environment.yml \
  .env.example \
  README.md \
  docs/daily-ingestion.md \
  stock_trading/config/trading_calendar.py \
  tests/test_trading_calendar.py \
  stock_trading/trades/models.py \
  stock_trading/trades/migrations/0004_traderecord_futu_fields.py \
  stock_trading/trades/services/trade_recorder.py \
  stock_trading/trades/services/futu_connector.py \
  stock_trading/trades/tasks.py \
  stock_trading/trades/management/commands/fetch_futu_trades_now.py \
  stock_trading/trades/management/commands/run_daily_ingestion_now.py \
  stock_trading/trades/tests/test_trade_recorder.py \
  stock_trading/trades/tests/test_futu_connector.py \
  stock_trading/trades/tests/test_tasks.py \
  stock_trading/trades/tests/test_management_command_futu.py \
  stock_trading/trades/tests/test_management_command_daily_ingestion.py
git commit -m "Add Futu HK trade ingestion"
```

Expected: commit succeeds with the Futu Hong Kong ingestion implementation and related docs/tests.
