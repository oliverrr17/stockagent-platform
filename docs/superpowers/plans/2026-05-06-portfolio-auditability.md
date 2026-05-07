# Portfolio Auditability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make portfolio returns auditable by persisting per-position daily contribution details, marking portfolio snapshots as final or provisional, and ensuring the existing daily ingestion path refreshes market snapshots.

**Architecture:** Extend the portfolio snapshot schema with audit metadata and add a per-position daily contribution model keyed to each portfolio snapshot. Update the analytics service to compute, persist, and reuse auditable snapshot inputs while wiring market snapshot refresh into the existing `run_daily_ingestion_now` management command so the Windows scheduled task no longer skips price snapshot persistence.

**Tech Stack:** Django ORM, Django REST Framework, pytest, SQLite/PostgreSQL-compatible migrations

---

### Task 1: Add failing tests for audit persistence

**Files:**
- Modify: `stock_trading/portfolio/tests/test_portfolio_analytics.py`
- Test: `stock_trading/portfolio/tests/test_portfolio_analytics.py`

- [ ] **Step 1: Write failing tests for snapshot audit metadata and contribution rows**

Add tests that expect:
- `PortfolioPerformanceSnapshot` to persist `audit_status`, `external_flow_cny`, and `computed_daily_pnl_cny`
- a new per-position contribution model to persist one row per security for the snapshot date
- provisional status when fallback or degraded pricing is used

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\stockagent\.miniconda3\envs\stock-trading-analysis\python.exe -m pytest stock_trading/portfolio/tests/test_portfolio_analytics.py -k audit -v`
Expected: FAIL because the new fields/model do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add the new model and snapshot fields, then update the analytics service to compute and persist the expected data.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\stockagent\.miniconda3\envs\stock-trading-analysis\python.exe -m pytest stock_trading/portfolio/tests/test_portfolio_analytics.py -k audit -v`
Expected: PASS

### Task 2: Add failing tests for daily ingestion market snapshot refresh

**Files:**
- Modify: `stock_trading/trades/tests/test_management_command_daily_ingestion.py`
- Modify: `stock_trading/portfolio/tests/test_tasks.py`
- Test: `stock_trading/trades/tests/test_management_command_daily_ingestion.py`

- [ ] **Step 1: Write failing tests for market snapshot refresh integration**

Add tests that expect `run_daily_ingestion_now` to call `refresh_market_price_snapshots()` and emit the result in JSON output.

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\stockagent\.miniconda3\envs\stock-trading-analysis\python.exe -m pytest stock_trading/trades/tests/test_management_command_daily_ingestion.py -v`
Expected: FAIL because the command does not invoke the snapshot refresh yet.

- [ ] **Step 3: Write minimal implementation**

Update `run_daily_ingestion_now.py` to invoke `refresh_market_price_snapshots()` after trade ingestion and include the result in the command summary.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\stockagent\.miniconda3\envs\stock-trading-analysis\python.exe -m pytest stock_trading/trades/tests/test_management_command_daily_ingestion.py -v`
Expected: PASS

### Task 3: Expose contribution data for inspection

**Files:**
- Modify: `stock_trading/portfolio/serializers.py`
- Modify: `stock_trading/portfolio/views.py`
- Modify: `stock_trading/portfolio/urls.py`
- Modify: `stock_trading/portfolio/tests/test_api_integration.py`
- Test: `stock_trading/portfolio/tests/test_api_integration.py`

- [ ] **Step 1: Write failing API test for contribution breakdown**

Add an authenticated integration test for a read-only endpoint returning the stored contribution rows for a given snapshot date.

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\stockagent\.miniconda3\envs\stock-trading-analysis\python.exe -m pytest stock_trading/portfolio/tests/test_api_integration.py -k contribution -v`
Expected: FAIL because the endpoint and serializer do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add the serializer, read-only API view, and URL route backed by the persisted contribution model.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\stockagent\.miniconda3\envs\stock-trading-analysis\python.exe -m pytest stock_trading/portfolio/tests/test_api_integration.py -k contribution -v`
Expected: PASS

### Task 4: Update runbook and verify targeted test coverage

**Files:**
- Modify: `docs/daily-ingestion.md`
- Modify: `stock_trading/portfolio/models.py`
- Modify: `stock_trading/portfolio/services/portfolio_analytics.py`
- Modify: `stock_trading/trades/management/commands/run_daily_ingestion_now.py`
- Create: `stock_trading/portfolio/migrations/0005_portfolio_snapshot_audit.py`

- [ ] **Step 1: Update the scheduler runbook**

Document that the Windows daily ingestion task now refreshes market snapshots and that the Celery beat market snapshot task is optional but still supported.

- [ ] **Step 2: Run focused regression tests**

Run: `D:\stockagent\.miniconda3\envs\stock-trading-analysis\python.exe -m pytest stock_trading/portfolio/tests/test_portfolio_analytics.py stock_trading/trades/tests/test_management_command_daily_ingestion.py stock_trading/portfolio/tests/test_api_integration.py stock_trading/portfolio/tests/test_tasks.py -v`
Expected: PASS

- [ ] **Step 3: Run the full portfolio/trades test subset affected by the change**

Run: `D:\stockagent\.miniconda3\envs\stock-trading-analysis\python.exe -m pytest stock_trading/portfolio/tests stock_trading/trades/tests/test_management_command_daily_ingestion.py -v`
Expected: PASS
