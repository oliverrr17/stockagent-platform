# Portfolio Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dual-currency cash accounting, FX rates, HK market data, and portfolio analytics so the product can show A-share + HK-share portfolio PnL and TWR-based performance from today forward.

**Architecture:** Backend computes analytics and exposes explicit API payloads for overview, active positions, cleared positions, cash accounts, and cash flows. Market data stays behind provider abstractions: Tushare for A-share daily bars and AKShare for HK prices and FX rates. Frontend renders charts and management flows from API responses rather than rebuilding accounting logic client-side.

**Tech Stack:** Django, DRF, SQLite/PostgreSQL, pytest, React, TypeScript, Ant Design, Recharts, AKShare, Tushare

---

### Task 1: Backend Models And Migrations

**Files:**
- Modify: `D:\stockagent\stock_trading\portfolio\models.py`
- Create: `D:\stockagent\stock_trading\portfolio\migrations\0002_cash_models.py`
- Test: `D:\stockagent\stock_trading\portfolio\tests\test_portfolio_analytics.py`

- [ ] Add `CashAccount`, `CashFlow`, and `FXRate` models with currency enums and uniqueness constraints.
- [ ] Add migration for the new models.
- [ ] Write tests covering:
  - `CashAccount` uniqueness by currency
  - `CashFlow` deposit/withdraw sign handling
  - `FXRate` uniqueness by `(base_currency, quote_currency, rate_date)`

### Task 2: Market Data Providers

**Files:**
- Modify: `D:\stockagent\stock_trading\analysis\services\market_data.py`
- Test: `D:\stockagent\stock_trading\analysis\tests\test_market_data.py`

- [ ] Add `HKAkshareProvider` for HK historical daily data and latest snapshot lookup.
- [ ] Add `FXAkshareProvider` for HKD/CNY daily FX rates.
- [ ] Add a provider builder that returns a composite provider object for:
  - A-share daily bars from Tushare
  - HK daily/snapshot from AKShare
  - FX rates from AKShare
- [ ] Write tests for:
  - HK daily row mapping
  - HK snapshot mapping
  - FX rate normalization to `1 HKD = x CNY`

### Task 3: Portfolio Analytics Service

**Files:**
- Create: `D:\stockagent\stock_trading\portfolio\services\portfolio_analytics.py`
- Modify: `D:\stockagent\stock_trading\portfolio\services\__init__.py`
- Test: `D:\stockagent\stock_trading\portfolio\tests\test_portfolio_analytics.py`

- [ ] Implement signed cash flow aggregation for `CNY` and `HKD`.
- [ ] Implement current holdings analytics:
  - realized pnl
  - unrealized pnl
  - latest market value
  - daily pnl
  - CNY-converted values
- [ ] Implement cleared-position listing.
- [ ] Implement account overview and TWR curve from the start date defined by the earliest cash flow.
- [ ] Write tests for:
  - TWR neutrality to deposits/withdrawals
  - HKD cash conversion using FX rate
  - cleared positions excluded from active list

### Task 4: Portfolio APIs

**Files:**
- Modify: `D:\stockagent\stock_trading\portfolio\serializers.py`
- Modify: `D:\stockagent\stock_trading\portfolio\views.py`
- Modify: `D:\stockagent\stock_trading\portfolio\urls.py`
- Test: `D:\stockagent\stock_trading\portfolio\tests\test_api.py`
- Test: `D:\stockagent\stock_trading\portfolio\tests\test_api_integration.py`

- [ ] Add serializers for cash accounts, cash flows, overview analytics, active position analytics, single-position analytics, and cleared positions.
- [ ] Add routes for:
  - `/api/portfolio/cash-accounts/`
  - `/api/portfolio/cash-flows/`
  - `/api/portfolio/analytics/overview/`
  - `/api/portfolio/analytics/positions/`
  - `/api/portfolio/analytics/positions/{stock_code}/`
  - `/api/portfolio/analytics/cleared/`
- [ ] Add tests that verify the payload shape and currency conversion fields.

### Task 5: News Actions On News Page

**Files:**
- Modify: `D:\stockagent\frontend\src\api\status.ts`
- Modify: `D:\stockagent\frontend\src\pages\NewsPage.tsx`
- Test: `D:\stockagent\frontend\src\pages\NewsPage.test.tsx`

- [ ] Add action buttons in `NewsPage` to call:
  - `crawl-news`
  - `push-news`
  - `push-digest`
- [ ] Keep `刷新` as read-only reload from DB.
- [ ] Add a small result panel showing the last operation response.
- [ ] Add at least one rendering test for the action area.

### Task 6: Portfolio Frontend Analytics UI

**Files:**
- Modify: `D:\stockagent\frontend\package.json`
- Modify: `D:\stockagent\frontend\src\api\portfolio.ts`
- Modify: `D:\stockagent\frontend\src\types\index.ts`
- Modify: `D:\stockagent\frontend\src\pages\PortfolioView.tsx`
- Create: `D:\stockagent\frontend\src\pages\ClearedPositionsPage.tsx`
- Modify: `D:\stockagent\frontend\src\App.tsx`
- Modify: `D:\stockagent\frontend\src\styles.css`
- Test: `D:\stockagent\frontend\src\pages\PortfolioView.test.tsx`

- [ ] Add `recharts` dependency.
- [ ] Add API functions for cash accounts, cash flows, overview analytics, active position analytics, single-position analytics, and cleared positions.
- [ ] Redesign `PortfolioView` to include:
  - total assets
  - realized/unrealized pnl
  - TWR daily/monthly/yearly metrics
  - performance line chart
  - cash account balances
  - cash flow entry form
  - current position selector and per-stock pnl panel
- [ ] Add a dedicated cleared positions page and route.
- [ ] Add at least one frontend test covering rendering of the analytics panel.

### Task 7: Verification

**Files:**
- Modify as needed from earlier tasks

- [ ] Run targeted backend tests for portfolio analytics.
- [ ] Run full backend tests.
- [ ] Run frontend tests.
- [ ] Run frontend build.
- [ ] Manually verify the Portfolio and News pages against live local data.
