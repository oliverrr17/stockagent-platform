# Scheduler Runbook

## Supported paths

- THS A-share ingestion
- HSBC email ingestion
- Futu OpenD Hong Kong trade ingestion
- portfolio market snapshot refresh
- portfolio news crawl
- news digest push

## One-shot run

Run all trade ingestion paths immediately:

```powershell
powershell -ExecutionPolicy Bypass -File D:\stockagent\scripts\windows\run_daily_ingestion.ps1
```

This run now also refreshes `SecurityPriceSnapshot` and recomputes portfolio performance snapshots, so the existing daily ingestion task doubles as the default portfolio audit refresh path.

## Celery worker and beat

Start worker:

```powershell
powershell -ExecutionPolicy Bypass -File D:\stockagent\scripts\windows\start_celery_worker.ps1
```

Start beat:

```powershell
powershell -ExecutionPolicy Bypass -File D:\stockagent\scripts\windows\start_celery_beat.ps1
```

Beat still keeps a standalone `portfolio.tasks.refresh_market_price_snapshots` schedule, but if you already rely on the Windows daily ingestion task, that task now covers market snapshot refresh too.

## Schedule defaults

- THS: `16:10`
- HSBC: `18:30`
- Futu: `18:35`
- market snapshots: refreshed inside `run_daily_ingestion_now`

Override them in `.env`:

```env
THS_FETCH_HOUR=16
THS_FETCH_MINUTE=10
HSBC_FETCH_HOUR=18
HSBC_FETCH_MINUTE=30
FUTU_FETCH_HOUR=18
FUTU_FETCH_MINUTE=35
```

## Windows Task Scheduler

Register a daily ingestion task:

```powershell
powershell -ExecutionPolicy Bypass -File D:\stockagent\scripts\windows\register_daily_ingestion_task.ps1
```

Register the news crawl and digest tasks:

```powershell
powershell -ExecutionPolicy Bypass -File D:\stockagent\scripts\windows\register_news_tasks.ps1
```

Default news scheduler times:

- crawl: every hour from `08:00` through `22:00`
- digest: `18:35`

One-shot news runs:

```powershell
powershell -ExecutionPolicy Bypass -File D:\stockagent\scripts\windows\run_news_crawl.ps1
powershell -ExecutionPolicy Bypass -File D:\stockagent\scripts\windows\run_news_digest.ps1
```

Notes:

- News Windows tasks do not require Celery or Redis.
- News tasks are intended to run every day, including non-trading days.
- News crawl only targets active positions (`status=ACTIVE` and `quantity>0`); cleared positions are excluded.

Important:

- THS GUI automation requires the task to run in an interactive user session.
- Keep the TongHuaShun client logged in.
- The task should run with the same effective permission level as the THS client.
- Futu ingestion requires a running OpenD instance and a configured Hong Kong real account.
- HSBC and Futu follow the Hong Kong trading calendar.
- If `TUSHARE_TOKEN` is not configured, Hong Kong holiday handling falls back to weekday approximation.
