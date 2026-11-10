# Deployment runbook (single always-on VM)

Target (decision D5): one Mumbai-region VM. Try Oracle Cloud Always Free (ARM, ₹0) first; if no capacity,
use AWS Lightsail with 4 GB RAM (~$24/month). Everything runs in Docker Compose, so moving providers means
redeploying, not rewriting.

## 1. Provision
- Ubuntu 24.04, 2+ vCPU, 4 GB RAM, 80 GB disk. Install Docker Engine + compose plugin.
- Do **not** expose port 8000 publicly. Use a private tunnel (Tailscale or Cloudflare Tunnel, free tiers) or a reverse proxy with HTTPS.

## 2. Configure
```bash
git clone <repo> market_sage && cd market_sage/infra
```
```bash
cp .env.example .env && chmod 600 .env
```
Fill in `.env`: DB password, auth hash (single-quoted), JWT secret (random 32+ chars), optional Angel One
credentials and VAPID keys. Keep `MARKET_SAGE_EXECUTION_MODE=paper` (other values are refused).

## 3. Start
```bash
docker compose up -d --build
```
```bash
docker compose logs -f worker
```
The API container migrates the database on start. The worker schedules: live session 09:10 IST,
post-close 18:30 IST (Mon–Fri), learning Sunday 10:00 IST, heartbeat every 5 min.

## 4. First data load
```bash
docker compose exec api market-sage ingest-nse 2016-01-01 2026-11-10
```
```bash
docker compose exec api market-sage post-close
```
Then populate `holidays.csv` from the NSE circular and reconcile `charges_v1.json` with a contract note.

## 5. Monitoring the monitor
- Set `MARKET_SAGE_HEARTBEAT_URL` to a healthchecks.io (or similar) check. You are paged if the worker stops pinging.
- `GET /api/health` for uptime probes.

## 6. Backups and recovery
```bash
docker compose exec db pg_dump -U market_sage market_sage | gzip > backup_$(date +%F).sql.gz
```
Also back up the `msdata` volume (raw files, Parquet, model artefacts). Restore = recreate volumes, load the dump,
`docker compose up -d`. After a restore, verify integrity:
```bash
docker compose exec api market-sage verify-ledger
```

## 7. Model rollback
```bash
docker compose exec api market-sage rollback-model
```
The previous production model is retained as `retired` and restored. Every promotion and rollback is recorded in `model_registry`.

## 8. Upgrades
```bash
git pull && docker compose up -d --build
```
Migrations are applied automatically. The ledger tables are append-only, so a migration must never rewrite them.
