# RestockRadar

A self-initiated demonstration project: a **multi-source new-product monitor** in
the same shape as a real production system — Python scrapers feeding a MySQL
store, surfaced through a PHP admin dashboard and a REST API that a mobile app
consumes. Built to show how I structure a scraper fleet for **speed and
reliability**, where the metric that matters is *time from a product being
listed to it reaching the end user*.

> This is a personal/portfolio build with fictional source sites and seeded
> demo data — not a paid client system. The code and design reflect how I
> approach the real thing.

## Stack

| Layer | Tech |
|-------|------|
| Scrapers | Python 3 · `requests` · `selectolax` · `PyMySQL` |
| Storage | MySQL (InnoDB) |
| Admin + API | PHP 8 · PDO |
| Delivery | REST/JSON feed → mobile app + push worker |

## What it demonstrates

- **One adapter per source** (`scraper/sources/`) — each site is isolated behind
  a small interface, so a markup change on one source is a one-file fix and can
  never take the rest of the fleet down.
- **Resilient fetching** (`scraper/monitor.py`) — rotating proxies + headers,
  retry with exponential backoff + jitter, and a **per-source circuit breaker**
  that backs off a failing site instead of hammering it.
- **Loud failure on drift** — when a parser can't find the structure it depends
  on it raises `MarkupChanged` with a page fingerprint, so alerts name *which*
  source broke rather than silently returning zero products.
- **Fast "is this new?"** — `products.dedup_key` is `UNIQUE`, and the writer uses
  `INSERT … ON DUPLICATE KEY UPDATE`; a row-affected count of 1 means genuinely
  new and worth pushing to the app.
- **Cheap operator visibility** — a `scrape_runs` telemetry table powers source
  health and the detection-lag KPI without scanning the products table.
- **App-facing API** (`api/index.php`) — token-authed JSON, cursor pagination by
  `first_seen` so the app can poll "what's new since my last item" cheaply.

## Layout

```
sql/schema.sql          MySQL schema (products, sources, scrape_runs)
scraper/monitor.py      orchestrator: fetch → parse → upsert, with resilience
scraper/db.py           MySQL persistence (PyMySQL)
scraper/sources/        per-site adapters (base contract + KicksMarket example)
admin/index.php         operator dashboard (KPIs, latest finds, source health)
admin/db.php            PDO connection + helpers
api/index.php           read-only JSON API for the mobile app
```

## Running

```bash
mysql < sql/schema.sql
pip install -r scraper/requirements.txt
DB_HOST=127.0.0.1 DB_USER=root DB_NAME=restockradar python -m scraper.monitor --once
php -S localhost:8080 -t admin      # dashboard at /index.php
```
