# Run Trading App

Start semua service IDX Trading App dan verifikasi pipeline.

## Arsitektur pipeline
yFinance (~949 emiten) → ingestion (TCP :9009) → tcp-bridge → Kafka `raw-ohlcv` → clickhouse-writer → ClickHouse `market.ohlcv` (+ Kafka `ohlc-live`) → backend → frontend (+ ticker tape).

## Steps
1. `docker compose up -d --build` dari `d:\Project\tradingApp`
2. Tunggu semua container healthy (clickhouse butuh start_period ~30s)
3. Verifikasi ingestion (poller) auto-fetch universe & stream ke TCP
4. Verifikasi clickhouse-writer insert ke ClickHouse
5. Cek backend `/api/symbols` & `/health`
6. Buka frontend http://localhost:3001

## Services & ports
- frontend (Next.js): http://localhost:3001
- backend (FastAPI): http://localhost:8000 (/docs)
- clickhouse: http://localhost:8123 (default / tradingch123, db `market`)
- postgres: localhost:5432 (trading / tradingpass123)
- kafka: localhost:9092

## Run instructions (PowerShell dari d:\Project\tradingApp)

```powershell
docker compose up -d --build

docker compose ps

# poller (auto-fetch ~949 emiten; market tutup = data statis)
docker compose logs --tail=20 ingestion
# bridge TCP→Kafka
docker compose logs --tail=10 tcp-bridge
# writer Kafka→ClickHouse
docker compose logs --tail=10 clickhouse-writer

# cek data di ClickHouse
docker compose exec clickhouse clickhouse-client --password tradingch123 --query "SELECT uniqExact(symbol), count() FROM market.ohlcv"

# backend API
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod "http://localhost:8000/api/symbols"

Start-Process "http://localhost:3001"
```

## Troubleshooting

**Frontend kosong / chart tidak muncul:** backfill awal (~949 emiten × 5 interval) butuh beberapa menit. Cek `docker compose logs ingestion` (poller) & `clickhouse-writer`. Bila yFinance rate-limit, sebagian chunk kosong → terisi pass berikutnya.

**clickhouse unhealthy / "disabling network access":** pastikan `CLICKHOUSE_PASSWORD` ter-set di service clickhouse (env `.env`).

**Browser hanya tampil 1 emiten / data tidak muncul:** hard refresh (Ctrl+Shift+R) atau Incognito (dokumen HTML `no-store`). Backend base URL diturunkan dari `window.location` runtime.

**Port bentrok (3001/8000/8123/5432/9092):** ubah port mapping di docker-compose.yml. Jangan jalankan bareng streaming_stock_analyze (port 8000/9092 sama).
```
