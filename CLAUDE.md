# CLAUDE.md — IDX Trading App

Panduan untuk Claude Code saat bekerja di project ini.

## Gambaran

Aplikasi web personal untuk trading saham IDX. Mengikuti `prd-tradingApp.md`.
Status saat ini: **Tab 1 (Journal), Tab 2 (Analyst), Tab 3 (Watchlist & Screener)** sudah dibangun.
Tab 3 = watchlist manual + screener/daily-picks rule-based (backend/screener.py: skor komposit 949 emiten dari ClickHouse, cached 5m; preset + filter; buang papan "Pemantauan Khusus" via board_map dari all.csv). Lapisan AI (Tab 3/5) DITUNDA & akan provider-agnostic (OpenAI-compatible `LLM_BASE_URL`/`LLM_MODEL` → Hermes/Llama self-hosted via Ollama/vLLM, BUKAN Claude API krn biaya).
Tab 4 (Fundamental) & Tab 5 (AI Advisor) = placeholder.

## Arsitektur (streaming Yahoo → TCP → Kafka → ClickHouse)

```
yFinance (delay 15m, ~949 emiten IDX, poll 300s)
   → ingestion/poller.py  (TCP server :9009, stream pipe-delimited bar, handshake "HELLO")
   → tcp-bridge/bridge.py  (TCP client → Kafka topic `raw-ohlcv`)
   → clickhouse-writer/writer.py  (Kafka → ClickHouse `market.ohlcv` + Kafka `ohlc-live`)
   → backend/ (FastAPI): REST history+indikator dari ClickHouse, WS hub (consume ohlc-live)
   → frontend/ (Next.js): Tab 1 Journal + Tab 2 Analyst (+ ticker tape footer)

PostgreSQL ← backend (porto, transaksi, jurnal)  [Tab 1]
ClickHouse ← storage permanen OHLCV               [Tab 2]
```

InfluxDB SUDAH DIHAPUS. Universe ~949 emiten di-auto-fetch saat startup dari
`UNIVERSE_URL` (all.csv repo Dataset-Saham-IDX); fallback ke daftar blue-chip.
`MAX_SYMBOLS=0` di .env = semua emiten.

## Stack

| Layer | Teknologi |
|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind + lightweight-charts 4 |
| Backend | FastAPI + uvicorn (clickhouse-connect, psycopg2) |
| Broker | Apache Kafka (Confluent 7.5.0) — topik `raw-ohlcv`, `ohlc-live` |
| Time-series | ClickHouse 24.3 (`market.ohlcv`, ReplacingMergeTree) |
| Relational | PostgreSQL 16 (journal/porto) |
| Data source | yFinance (.JK tickers, ^JKSE→IHSG) |
| Pipeline TCP | ingestion (server) ↔ tcp-bridge (client) port 9009, format `B\|code\|type\|sector\|interval\|epoch\|o\|h\|l\|c\|v` |

## Struktur File

```
ingestion/poller.py       → yFinance chunked download → TCP server :9009 (dedup by last_ts, self-heal)
ingestion/config.py       → fetch_universe() (~949 emiten) + interval→period
tcp-bridge/bridge.py      → TCP client (HELLO) → Kafka raw-ohlcv
clickhouse-writer/writer.py → Kafka raw-ohlcv → ClickHouse market.ohlcv + Kafka ohlc-live
backend/config.py         → env (ClickHouse + Postgres + Kafka)
backend/db.py             → ClickHouse client (THREAD-LOCAL, krn FastAPI threadpool) + Postgres pool
backend/indicators.py     → SEMUA indikator (Trend/Momentum/Volatility/Volume) + signals
backend/realtime.py       → WS connection set + broadcast
backend/screener.py       → scoring engine 949 emiten (1 query ClickHouse + pandas groupby, cached 5m) + filter
backend/routers/market.py → Tab 2: /api/symbols, /api/history, /api/quotes, /ws (data-driven dari ClickHouse)
backend/routers/journal.py→ Tab 1: positions, transactions, analytics (FIFO P&L)
backend/routers/watchlist.py → Tab 3: /api/watchlist (CRUD), /api/screener, /api/screener/presets
backend/main.py           → app, lifespan (ensure_watchlist_table), Kafka consumer thread (ohlc-live → WS)
db/clickhouse-init.sql    → schema market.ohlcv (ReplacingMergeTree)
db/init.sql               → Postgres schema positions + transactions + watchlist (+ seed)
frontend/app/analyst/     → Tab 2 page (+ TickerTape footer; baca ?symbol= dari URL)
frontend/app/journal/     → Tab 1 page
frontend/app/watchlist/   → Tab 3 page (watchlist manual + screener + preset + filter)
frontend/components/AnalystChart.tsx → multi-pane synced lightweight-charts (localization en-US)
frontend/components/TickerTape.tsx   → marquee footer (top-60 by volume)
frontend/components/Sidebar.tsx      → nav; `ready:true` utk tab yang aktif
frontend/lib/api.ts       → base URL diturunkan runtime dari window.location (bukan hardcode localhost)
frontend/lib/types.ts, format.ts (format manual ID, tanpa toLocaleString)
```

## Indikator (backend/indicators.py)

- **Trend**: SMA(20/50/200), EMA(20/50), MACD, ADX/DMI, Parabolic SAR
- **Momentum**: RSI, Stochastic, Williams %R, CCI
- **Volatility**: Bollinger Bands, ATR, Keltner Channel
- **Volume**: VWAP (session-reset intraday), OBV, A/D Line, Volume Profile (POC)

`compute_all(df, want, interval)` → dict JSON-ready. `latest_signals()` → verdict + score.
Indikator overlay (di chart harga) vs oscillator (panel terpisah) ditentukan di frontend `IndicatorPanel.tsx`.

## Menjalankan

```bash
cd d:/Project/tradingApp
docker compose up -d --build       # pertama kali
docker compose logs -f ingestion   # cek poller ambil data yFinance
```

Akses:
- Frontend: http://localhost:3001
- Backend API: http://localhost:8000 (docs di /docs)
- ClickHouse: http://localhost:8123 (default / tradingch123, db `market`)
- Postgres: localhost:5432 (trading / tradingpass123)

## Catatan Penting (gotchas yang sudah ketemu)

- **Data delay & poll**: yFinance IDX delay ~15 menit, poller jalan tiap `POLL_INTERVAL` (default 300s). Saat market tutup data tidak berubah.
- **Backfill**: clickhouse-writer pakai `auto_offset_reset=earliest` + consumer group → proses semua yang masuk Kafka. ClickHouse `ReplacingMergeTree` dedup re-stream (idempoten).
- **ClickHouse client THREAD-LOCAL** (db.py): clickhouse-connect TIDAK thread-safe; FastAPI endpoint sync jalan di threadpool → request paralel. Jangan share satu client global (dulu bikin /api/quotes kadang kosong).
- **ClickHouse network access**: `CLICKHOUSE_PASSWORD` WAJIB di-set di service clickhouse, kalau tidak image menonaktifkan akses jaringan user default.
- **Frontend API base URL**: diturunkan RUNTIME dari `window.location.hostname` (lib/api.ts), bukan hardcode/bake. Jadi jalan via localhost maupun IP LAN.
- **Frontend cache**: dokumen HTML `no-store` (next.config.js headers) supaya tidak ada stale shell. Kalau tampilan aneh → hard refresh (Ctrl+Shift+R) / Incognito.
- **Format angka**: `lib/format.ts` manual (titik ribuan/koma desimal), JANGAN `toLocaleString("id-ID")` (lempar RangeError di sebagian browser → gagal hydrate). Chart pakai `localization:{locale:"en-US"}`.
- **TCP handshake**: tcp-bridge kirim "HELLO" saat connect; poller abaikan koneksi tanpa handshake (mencegah healthcheck Docker memicu re-backfill).
- **pandas groupby**: DataFrame hasil iterasi `for k,g in df.groupby(...)` TIDAK punya `g.name` → oper key eksplisit (bug di screener).
- **Tambah/atur universe**: universe auto-fetch dari `UNIVERSE_URL` (all.csv). `MAX_SYMBOLS=0`=semua; set angka utk batasi (subset alfabetis). Emiten spesifik wajib-ada → tambah ke `FALLBACK_STOCKS` di `ingestion/config.py`.
- **Tambah indikator**: fungsi di `indicators.py` → daftarkan di `compute_all` + `DEFAULT_INDICATORS` → entry di frontend `IndicatorPanel.tsx` + tipe `types.ts` + render `AnalystChart.tsx`.
- **Tes browser tanpa Node di host**: Playwright via image `mcr.microsoft.com/playwright` + `docker run --network host` (replika persis alur localhost browser user). Skrip ada di scratchpad session.
- **Lapisan AI (Tab 3/5) — belum dibangun**: rancang provider-agnostic via OpenAI-compatible (`LLM_BASE_URL`/`LLM_MODEL`) → arahkan ke Hermes/Llama self-hosted (Ollama/vLLM). Bukan Claude API (biaya).
