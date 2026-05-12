# Futu HK Trade Ingestion Design

**Date:** 2026-05-12

**Goal:** Add a Futu broker ingestion path for Hong Kong stock real-account trades at the same product level as the existing HSBC Hong Kong ingestion path, while preserving accurate fee capture from Futu and aligning both HSBC and Futu scheduling with the Hong Kong trading calendar.

**Status:** Approved design for implementation planning

## Scope

This design covers:

- Futu ingestion through `OpenD + futu-api`
- Hong Kong real-account trade ingestion only
- daily scheduled ingestion integration
- fee capture and persistence for Futu orders
- migration of HSBC/Futu trading-day gating from the current CN-equity calendar check to a Hong Kong trading-day check
- README and runbook updates for runtime setup and fee caveats

This design explicitly does **not** cover:

- Futu email ingestion
- Futu exported statement ingestion
- U.S. or Singapore market support
- partial-fill fee allocation across multiple deals
- dual-model order/deal persistence
- frontend changes beyond any existing API consumers that already read `TradeRecord`

## Product Constraints Confirmed

- Futu must use `OpenD + futu-api`
- only Hong Kong real-account trading is in scope
- first version should align with the current HSBC Hong Kong path rather than becoming a multi-market broker framework
- partial-fill fee allocation is intentionally out of scope to keep the first version simple
- README must document that broker fees vary by user package, activity, and product type, so example fees are illustrative only

## Existing System Context

The current project has two trade ingestion paths:

- `THS` for A-share trades
- `HSBC_EMAIL` for Hong Kong trades parsed from IMAP mail

Trade persistence is centered on `TradeRecord`, and downstream cost basis, realized PnL, unrealized PnL, and day-level analytics already consume these fields:

- `market`
- `direction`
- `price`
- `quantity`
- `commission`
- `stamp_duty`
- `other_fees`
- `trade_time`
- `source`

The current model and recorder logic assume one persisted `TradeRecord` is the accounting unit used by the portfolio subsystem. That makes it important that the Futu ingestion unit match the fee unit closely enough for cost accounting to remain correct without a larger portfolio refactor.

## External API Constraints

The design relies on these Futu OpenAPI capabilities:

- `get_acc_list()` for resolving eligible accounts
- `history_order_list_query()` for historical Hong Kong orders
- `order_fee_query()` for order-level fee detail

Important behavior from the official docs:

- account access should prefer `acc_id`
- historical trade data is available for real accounts
- fee queries are order-based, not deal-based
- fee queries return aggregate fee amount plus per-fee-item details
- fee and order APIs are rate-limited per `acc_id`

These constraints drive the design toward order-level persistence rather than deal-level persistence.

## Design Decision: Persist Futu At Order Level

The first version will persist **one `TradeRecord` per filled Futu order**, not one record per Futu deal.

### Why

Futu fee data is naturally attached to `order_id`, while the existing project expects fees to live on the same record that drives accounting. If we persisted each deal separately, we would need a fee-allocation policy across partial fills. That was explicitly rejected for the first version.

### Result

Each persisted Futu trade record will represent:

- a Hong Kong real-account order with actual filled quantity
- filled quantity equal to the order’s dealt quantity
- execution price equal to the order’s dealt average price
- fees equal to the order-level fee breakdown returned by `order_fee_query()`

This keeps portfolio accounting consistent without introducing artificial fee allocation rules.

## Data Model Changes

### `TradeRecord.Source`

Add:

- `FUTU_API`

### New `TradeRecord` Fields

Add:

- `external_trade_id`: string field used to store Futu `order_id`
- `fee_details`: JSON field for raw broker fee detail

### Fee Field Strategy

Retain the existing normalized fee columns:

- `commission`
- `stamp_duty`
- `other_fees`

And additionally preserve raw broker detail in:

- `fee_details`

This preserves compatibility with the current portfolio subsystem while keeping enough original broker evidence for auditing and future open-source use.

### Fee Mapping

Map Futu fee items as follows:

- `commission` <- commission
- `stamp_duty` <- stamp duty
- `other_fees` <- platform fees, settlement/transfer fees, trading fees, regulatory levies, and any unknown mapped or unmapped fee items
- `fee_details` <- full raw fee item payload as returned by Futu

Unknown fee names must not block persistence as long as the fee response is otherwise valid. Unknown items should be summed into `other_fees` and retained in raw detail.

## Deduplication Strategy

The current duplicate check uses:

- `stock_code`
- `trade_time`
- `direction`
- `quantity`
- `price`

That is not strong enough once multiple brokers coexist and Futu exposes a stable broker-side order identifier.

The updated persistence rules should be:

- for `FUTU_API`, deduplicate by `(source, external_trade_id)`
- for existing non-Futu records, preserve current compatibility behavior

Implementation may choose either:

- recorder-level conditional duplicate logic, or
- a database uniqueness constraint that supports nullable/non-nullable broker IDs cleanly across SQLite/PostgreSQL

The key requirement is behavioral:

- repeated Futu ingestion runs must be idempotent
- existing HSBC and THS data behavior must remain unchanged

## Hong Kong Trading-Day Gating

### Current Problem

`HSBC_EMAIL` ingestion currently uses the CN-equity trading-day helper. That is semantically wrong for a Hong Kong broker path and can skip valid Hong Kong trading days when CN and HK calendars diverge.

### Required Change

Introduce a dedicated Hong Kong trading-day helper, for example:

- `is_hk_equity_trading_day()`

Then update:

- `run_hsbc_email_ingestion()` to use the HK helper
- new `run_futu_ingestion()` to use the HK helper

Do **not** change THS ingestion; it remains on the CN-equity trading calendar.

### Data Source For HK Trading Days

Preferred behavior:

- if `TUSHARE_TOKEN` is configured, use Tushare Hong Kong market calendar data
- otherwise fall back to weekday-based approximation, matching the current project’s graceful-degradation style

README and runbook docs must state that no-token fallback is approximate around market holidays.

## Futu Connector Design

Create:

- `stock_trading/trades/services/futu_connector.py`

Responsibilities:

- establish OpenD connection
- resolve and validate eligible accounts
- enforce Hong Kong real-account scope
- fetch historical orders
- batch-fetch order fees
- normalize broker payloads into project trade-record dictionaries

### Account Validation Rules

The connector must only allow:

- real accounts
- Hong Kong trading authorization
- the configured broker/account target

If the configured `acc_id` is missing or not eligible, ingestion should fail clearly rather than silently falling back to another account.

### Normalized Output Shape

Each normalized trade dict should align with `TradeRecorder` expectations, including:

- `stock_code`
- `stock_name`
- `market=HK_STOCK`
- `direction`
- `price`
- `quantity`
- `trade_time`
- `source=FUTU_API`
- `commission`
- `stamp_duty`
- `other_fees`
- `external_trade_id`
- `fee_details`

### Time Field

Use the order `updated_time` as persisted `trade_time`.

This is an explicit design tradeoff:

- it is stable and available at order level
- it avoids introducing deal-level fetch and fee allocation complexity
- it is sufficient for current day-level accounting and broker-ingestion parity

It is not intended for future sub-order execution sequence analysis.

## Task Integration

### New Task Entry

Add to `stock_trading/trades/tasks.py`:

- `run_futu_ingestion()`
- `fetch_futu_trades()` Celery task wrapper if needed for consistency with the rest of the module

Behavior:

- skip on non-HK trading day
- validate required environment config
- fetch historical orders within a configurable lookback window
- fetch order fees
- normalize and persist records idempotently
- return created-record count

### Daily Ingestion Command

Update `stock_trading/trades/management/commands/run_daily_ingestion_now.py` so the summary includes:

- `futu_created_count`
- `futu_error`

The orchestration should become:

- THS
- HSBC
- FUTU
- portfolio market snapshot refresh

### Dedicated Futu Command

Add a management command:

- `fetch_futu_trades_now`

Expected options:

- `--dry-run`
- `--json`
- `--output-file`
- `--since-days`
- optional connection/account overrides such as host, port, and `acc-id`

The command should mirror the operator experience of the existing HSBC and THS commands.

## Environment Configuration

Add to `.env.example`:

- `FUTU_HOST`
- `FUTU_PORT`
- `FUTU_ACC_ID`
- `FUTU_SECURITY_FIRM`
- `FUTU_MARKET=HK`
- `FUTU_FETCH_HOUR`
- `FUTU_FETCH_MINUTE`

Optional only if needed at runtime:

- `FUTU_TRADE_PWD_MD5`

The design does not require unlock-by-default for read-only history and fee queries. If runtime behavior proves unlock is required in a particular environment, support it as an opt-in configuration.

## Error Handling Rules

The first version should optimize for correctness over partial success.

- if OpenD connection fails: fail the Futu ingestion path
- if account validation fails: fail the Futu ingestion path
- if historical order fetch fails: fail the Futu ingestion path
- if fee fetch fails for the batch: fail the Futu ingestion path
- if a specific order has unknown fee item labels but valid totals: persist it, aggregate unknown items into `other_fees`, retain raw `fee_details`, and log a warning

This intentionally avoids writing Futu trades with zeroed or guessed fees.

## Testing Strategy

### Connector Unit Tests

Add tests for:

- account filtering and HK real-account validation
- order normalization into internal trade schema
- fee mapping into `commission`, `stamp_duty`, `other_fees`
- unknown fee item handling
- batched fee-query behavior

### Task Tests

Add tests for:

- Futu ingestion skips on non-HK trading day
- HSBC now skips on non-HK trading day rather than CN trading day
- successful Futu ingestion creates the expected number of records
- failed fee fetch causes no records to persist

### Management Command Tests

Add tests for:

- `fetch_futu_trades_now --dry-run`
- JSON output
- file output
- configurable lookback window

### Orchestration Tests

Update daily-ingestion tests so they verify:

- `futu_created_count` appears in summary and JSON output
- `futu_error` is surfaced alongside existing broker errors

## Documentation Changes

### README

Document:

- Futu setup prerequisites (`OpenD + futu-api`)
- Hong Kong real-account-only support in the first version
- fee mapping behavior
- fee disclaimer for open-source readers

The README must explicitly state:

- example fee calculations are illustrative only
- actual commission and platform charges vary by user package, promotions, and product type
- broker-returned `fee_details` is the source of truth for actual persisted costs

### Scheduler Runbook

Update `docs/daily-ingestion.md` to include:

- Futu as part of the daily ingestion path
- default Futu schedule
- OpenD runtime requirement
- Hong Kong trading-day behavior

## Non-Goals And Deferred Work

The following are intentionally deferred:

- partial-fill fee allocation across multiple Futu deals
- deal-level persistence using `deal_id`
- support for U.S./Singapore Futu markets
- a generic multi-broker abstraction layer
- frontend fee-detail visualization
- order/deal fee reconciliation tooling

These can be added later after the first Hong Kong real-account path is stable.

## Recommended Implementation Shape

Implement the first version in this order:

1. Add failing model and recorder tests for `FUTU_API`, `external_trade_id`, `fee_details`, and Futu deduplication behavior
2. Add connector tests for account validation, order normalization, and fee mapping
3. Implement `FutuConnector`
4. Add task and management-command tests
5. Implement `run_futu_ingestion()` and `fetch_futu_trades_now`
6. Update `run_daily_ingestion_now`
7. Add HK trading-day helper and switch HSBC/Futu to it
8. Update `.env.example`, `README.md`, and `docs/daily-ingestion.md`

## Open Questions Resolved In This Design

- Futu transport: `OpenD + futu-api`
- Market scope: Hong Kong real-account only
- Fee detail persistence: keep normalized fee columns plus raw `fee_details`
- Partial fills: do not allocate fees across deals in v1
- Persistence unit: one `TradeRecord` per filled order
- `trade_time`: use order `updated_time`

No unresolved product questions remain for implementation planning.
