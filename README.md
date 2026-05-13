# stockagent

Reproducible development baseline for the stock trading analysis platform.

## Verified Toolchain

This repository has been verified with:

- Python `3.13.12`
- Node `24.14.1`
- npm `11.11.0`
- Conda environment name: `stock-trading-analysis`

## Repository Layout

- `stock_trading/`: Django backend project and domain apps
- `frontend/`: React + Vite frontend
- `tests/`: cross-module backend tests
- `docs/`: runbooks, plans, and backlog notes

## Quick Start (SQLite Default)

The default local workflow uses SQLite. Leave `DB_ENGINE` unset in `.env` and the backend will use `./db.sqlite3`.

### One-click Windows startup

If you want the backend and frontend started together in the background:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start_dev_stack.ps1
```

To stop and relaunch repo-local dev processes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start_dev_stack.ps1 -Restart
```

### 1. Create the backend environment

From the repository root:

```powershell
conda env create -f environment.yml
conda activate stock-trading-analysis
Copy-Item .env.example .env
python stock_trading/manage.py migrate
python stock_trading/manage.py runserver
```

The backend will start at `http://127.0.0.1:8000/`.

### 2. Start the frontend

Open a second terminal in the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

The frontend will start at `http://127.0.0.1:5173/` and proxy `/api` and `/admin` to the Django server.

## Verification Commands

### Backend

```powershell
conda activate stock-trading-analysis
python stock_trading/manage.py check
python -m pytest
```

### Frontend

```powershell
cd frontend
npm ci
npm test
npm run build
```

## Optional Services

### PostgreSQL

SQLite is the default. If you want PostgreSQL instead, set `DB_ENGINE` and the commented `DB_*` values in `.env`.

### Redis and Celery

Redis and Celery are optional for the basic SQLite development path. They are needed for scheduled ingestion and asynchronous jobs.

Start the worker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start_celery_worker.ps1
```

Start beat:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start_celery_beat.ps1
```

Windows Task Scheduler can be used instead of Celery for the current trade/news automation flow:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\register_daily_ingestion_task.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\register_news_tasks.ps1
```

See `docs/daily-ingestion.md` for the scheduler runbook.

## Optional Integrations

The following integrations are optional and only needed for full runtime behavior:

- Tushare token for A-share market data
- TongHuaShun client and bridge Python for THS ingestion
- HSBC IMAP credentials for email-based trade ingestion
- Futu OpenD and `futu-api` for Hong Kong real-account trade ingestion
- SMTP credentials for email notifications

All of these values are documented in `.env.example`.

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
