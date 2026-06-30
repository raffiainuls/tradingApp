# 📈 IDX Trader — Personal Trading Suite

Aplikasi web personal untuk trading saham **IDX (Bursa Efek Indonesia)**: jurnal trading, analisis teknikal chart-based, dan watchlist/screener berbasis skor teknikal — di atas pipeline data **streaming** real (delayed) dari Yahoo Finance.

> ⚠️ **Disclaimer:** Data via yFinance **delay ~15 menit** (aturan IDX). Aplikasi ini untuk **edukasi & riset pribadi**, **bukan** ajakan jual/beli. Bukan nasihat investasi.

---

## ✨ Fitur

| Tab | Status | Isi |
|---|---|---|
| **1. Trading Journal** | ✅ | Portofolio aktif (unrealized P&L, alokasi sektor), log transaksi, analitik FIFO (win rate, profit factor, equity curve, best/worst, P&L per emiten) |
| **2. Trading Analyst** | ✅ | Candlestick multi-timeframe (5m/15m/1h/1d/1wk), **19 indikator** (multi-pane tersinkron), ringkasan teknikal (verdict + score), ticker tape berjalan, live via WebSocket |
| **3. Watchlist & Screener** | ✅ | Watchlist manual + **screener/daily-picks rule-based** seluruh universe (~949 emiten): skor komposit, preset, filter, buang papan "Pemantauan Khusus" |
| **4. Fundamental Analyst** | 🚧 | Placeholder (fase berikutnya) |
| **5. AI Advisor** | 🚧 | Placeholder — akan **provider-agnostic** (Hermes/LLM self-hosted via OpenAI-compatible API) |

---

## 🏗️ Arsitektur

```
yFinance (~949 emiten IDX, delay 15m, poll 300s)
      │  fetch chunked
      ▼
  ingestion  ── TCP server :9009 (stream pipe-delimited bar, handshake "HELLO")
      │
      ▼
  tcp-bridge ── TCP client → Kafka topic `raw-ohlcv`
      │
      ▼
  clickhouse-writer ── Kafka → ClickHouse `market.ohlcv` (+ Kafka `ohlc-live`)
      │
      ▼
  backend (FastAPI) ── REST (history + indikator + screener dari ClickHouse) + WebSocket hub
      │
      ▼
  frontend (Next.js) ── Tab 1 / 2 / 3

PostgreSQL  ← journal, portofolio, transaksi, watchlist  (Tab 1 & 3)
ClickHouse  ← storage permanen OHLCV (ReplacingMergeTree)  (Tab 2 & 3)
```

Pipeline meniru pola **streaming TCP → Kafka** namun memakai data IDX nyata (delayed) dan menyimpan history di **ClickHouse**.

---

## 🧱 Tech Stack

- **Frontend:** Next.js 14 (App Router) · TypeScript · Tailwind CSS · [lightweight-charts](https://github.com/tradingview/lightweight-charts) 4
- **Backend:** FastAPI · uvicorn · clickhouse-connect · psycopg2 · pandas/numpy
- **Streaming:** Apache Kafka (Confluent 7.5.0) — topik `raw-ohlcv`, `ohlc-live`
- **Time-series DB:** ClickHouse 24.3 (`market.ohlcv`, ReplacingMergeTree)
- **Relational DB:** PostgreSQL 16 (journal/porto/watchlist)
- **Data source:** yFinance (`.JK` ticker, `^JKSE` → IHSG); universe dari [Dataset-Saham-IDX](https://github.com/wildangunawan/Dataset-Saham-IDX)
- **Orkestrasi:** Docker Compose

---

## 🚀 Quick Start

Prasyarat: **Docker Desktop** (Docker + Compose).

```bash
git clone <repo-url> tradingApp
cd tradingApp

cp .env.example .env        # sesuaikan bila perlu (Windows: copy .env.example .env)

docker compose up -d --build
```

Tunggu ~1–3 menit (ClickHouse start + backfill awal yFinance). Lalu buka:

| Service | URL | Kredensial |
|---|---|---|
| **Frontend (dashboard)** | http://localhost:3001 | – |
| Backend API (Swagger) | http://localhost:8000/docs | – |
| ClickHouse (HTTP) | http://localhost:8123 | `default` / `tradingch123` |
| PostgreSQL | `localhost:5432` | `trading` / `tradingpass123` |
| Kafka | `localhost:9092` | – |

> Tip: kalau dashboard kosong sebentar, **hard refresh** (`Ctrl+Shift+R`) — backfill awal butuh beberapa menit untuk mengisi ClickHouse.

Cek progres:
```bash
docker compose logs -f ingestion          # poller ambil data yFinance
docker compose logs -f clickhouse-writer   # insert ke ClickHouse
docker compose exec clickhouse clickhouse-client --password tradingch123 \
  --query "SELECT uniqExact(symbol), count() FROM market.ohlcv"
```

Stop:
```bash
docker compose down          # stop (data tetap di volume)
docker compose down -v       # stop + hapus data (ClickHouse + Postgres)
```

---

## 📂 Struktur Project

```
tradingApp/
├── docker-compose.yml          # 9 service
├── .env.example                # template konfigurasi
├── ingestion/                  # yFinance → TCP server (auto-fetch universe)
├── tcp-bridge/                 # TCP → Kafka
├── clickhouse-writer/          # Kafka → ClickHouse (+ ohlc-live)
├── backend/                    # FastAPI
│   ├── indicators.py           # semua indikator teknikal
│   ├── screener.py             # scoring engine universe
│   ├── db.py                   # ClickHouse (thread-local) + Postgres
│   └── routers/                # market / journal / watchlist
├── frontend/                   # Next.js (app/journal, app/analyst, app/watchlist)
└── db/
    ├── clickhouse-init.sql     # schema market.ohlcv
    └── init.sql                # schema Postgres + seed
```

---

## 📊 Indikator (Tab 2)

- **Trend:** SMA (20/50/200), EMA (20/50), MACD, ADX/DMI, Parabolic SAR
- **Momentum:** RSI, Stochastic, Williams %R, CCI
- **Volatility:** Bollinger Bands, ATR, Keltner Channel
- **Volume:** VWAP (reset per sesi), OBV, A/D Line, Volume Profile (POC)

Plus **Technical Summary**: verdict (STRONG BUY → STRONG SELL) + skor −100..+100 + key levels.

## 🔎 Screener (Tab 3)

Skor komposit teknikal untuk **seluruh universe** dihitung efisien (1 query ClickHouse + pandas groupby, cache 5 menit). Preset siap pakai: **Strong Buy, Oversold + Uptrend, Breakout Volume, Momentum Kuat, Oversold (RSI<30)**. Filter: timeframe, min skor, RSI, volume ratio, di atas MA200, dan **buang papan "Pemantauan Khusus"** (khas IDX).

---

## ⚙️ Konfigurasi (`.env`)

| Variabel | Default | Keterangan |
|---|---|---|
| `MAX_SYMBOLS` | `0` | `0` = semua ~951 emiten; `>0` = batasi (subset alfabetis) |
| `POLL_INTERVAL` | `300` | interval poll yFinance (detik) |
| `CHART_INTERVALS` | `5m,15m,1h,1d,1wk` | timeframe yang di-fetch |
| `CHUNK_SIZE` | `60` | ticker per batch (hindari rate-limit) |
| `UNIVERSE_URL` | all.csv Dataset-Saham-IDX | sumber daftar emiten |
| `CLICKHOUSE_PASSWORD` | `tradingch123` | **wajib** (kalau kosong, akses jaringan ClickHouse dinonaktifkan) |

---

## 🔌 API Utama

| Endpoint | Fungsi |
|---|---|
| `GET /api/symbols` | daftar emiten yang punya data |
| `GET /api/quotes?interval=1d` | quote ringkas semua emiten |
| `GET /api/history/{symbol}?interval=1d` | candles + indikator + signals |
| `WS /ws` | update bar real-time |
| `GET /api/screener?...` | screener/daily-picks (preset & filter) |
| `GET/POST/DELETE /api/watchlist` | watchlist manual |
| `GET/POST/PUT/DELETE /api/journal/positions` | portofolio |
| `GET/POST/DELETE /api/journal/transactions` | transaksi |
| `GET /api/journal/analytics` | analitik (win rate, equity curve, dll.) |

Dokumentasi interaktif: **http://localhost:8000/docs**

---

## 🗺️ Roadmap

- [x] Tab 1 — Trading Journal
- [x] Tab 2 — Trading Analyst (19 indikator + ticker tape)
- [x] Tab 3 — Watchlist & Screener (rule-based)
- [ ] Tab 3/5 — Lapisan AI (provider-agnostic, OpenAI-compatible → Hermes/Llama self-hosted)
- [ ] Tab 4 — Fundamental Analyst
- [ ] Import CSV transaksi dari broker

---

## 📚 Dokumentasi lain

- **[TESTING.md](TESTING.md)** — cara test backend API, pipeline, & frontend (Playwright via Docker)
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — kalau data tidak tampil (terutama saat deploy di server/VPS)
- **[docs/hermes-integration.md](docs/hermes-integration.md)** — panduan integrasi Hermes Agent untuk AI Advisor (Tab 5)
- **[CLAUDE.md](CLAUDE.md)** — detail teknis & gotchas untuk pengembangan

## 📝 Catatan

- Data **delay ~15 menit**; saat market tutup, candle terakhir tidak berubah.
- Universe ~949 emiten di-**auto-fetch** saat startup; sebagian emiten illikuid mungkin tanpa data intraday.
- **Deploy di server:** buka port **3001** & **8000** di firewall/security group. yFinance bisa diblok dari IP VPS — lihat [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
