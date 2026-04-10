# Quick Reference — After Reboot

## 1. Start PostgreSQL

```bash
sudo systemctl start postgresql
```

## 2. Set Environment

```bash
cd ~/sec-edgar-ingestor
export SEC_EDGAR_DB_DSN="postgresql:///sec_edgar?user=tracks"
export SEC_EDGAR_USER_AGENT="MyName email@yahoo.com"
```

Or just make sure `.env` has these values — the app reads it automatically.

## 3. Activate Virtualenv

```bash
source .venv/bin/activate
```

## 4. Run Migrations (first time or after schema changes)

```bash
sec-edgar db migrate
```

## 5. Ingest

```bash
# Dev mode (last 6 months)
sec-edgar ingest 13f --mode dev

# Full backfill
sec-edgar ingest 13f --mode full

# Daily refresh
sec-edgar ingest 13f --mode daily
```

## 6. Refresh Analytics Views

```bash
sec-edgar db refresh-analytics
```
