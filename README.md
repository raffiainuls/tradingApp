# 📈 IDX Trader — Personal Trading Suite

Aplikasi web personal untuk trading saham **IDX (Bursa Efek Indonesia)**: jurnal trading, analisis teknikal chart-based, dan watchlist/screener berbasis skor teknikal — di atas pipeline data **streaming** real (delayed) dari Yahoo Finance.

> ⚠️ **Disclaimer:** Data via yFinance **delay ~15 menit** (aturan IDX). Aplikasi ini untuk **edukasi & riset pribadi**, **bukan** ajakan jual/beli. Bukan nasihat investasi.

---

## ✨ Fitur

| Tab | Status | Isi |
|---|---|---|
| **1. Trading Journal** | ✅ | Portofolio aktif (unrealized P&L, alokasi sektor), log transaksi, analitik FIFO (win rate, profit factor, equity curve, best/worst, P&L per emiten) |
| **2. Trading Analyst** | ✅ | Candlestick multi-timeframe (5m/15m/1h/1d/1wk), **19 indikator** (multi-pane tersinkron), ringkasan teknikal (verdict + score), ticker tape berjalan, live via WebSocket |
| **3. Watchlist + AI Picks** | ✅ | Watchlist manual + **AI Picks** harian: top-15 bullish dari mesin skoring, reasoning LLM (opsional, self-hosted), level entry/target/cutloss dari ATR |
| **4. Screener** | ✅ | **Screener/daily-picks rule-based** seluruh universe (~949 emiten): skor komposit, preset, filter, buang papan "Pemantauan Khusus", ★ tambah ke watchlist |
| **5. AI Advisor** | ✅ | Analisa mendalam 1 saham + rekomendasi harian via **Hermes Agent** (`bro_analysis` CLI), data teknikal dari ClickHouse sendiri |

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

Untuk narasi AI di **Tab 5 (AI Advisor)**, jalankan tambahan di **host** (bukan Docker,
karena Hermes CLI ada di sana): `python3 scripts/hermes_advisor_bridge.py --port 8090 &`
— opsional, tanpa ini Tab 5 tetap tampil data teknikal saja.

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
│   ├── ai_picks.py             # orkestrasi AI Picks (top-N bullish + reasoning LLM)
│   ├── llm_client.py           # klien LLM generik OpenAI-compatible
│   ├── ai_advisor.py           # orkestrasi AI Advisor (analisa 1 saham + rekomendasi harian)
│   ├── hermes_bridge.py        # klien HTTP ke scripts/hermes_advisor_bridge.py (host)
│   ├── db.py                   # ClickHouse (thread-local) + Postgres
│   └── routers/                # market / journal / watchlist / screener / ai_picks / ai_advisor
├── scripts/
│   └── hermes_advisor_bridge.py # jalan di HOST (bukan Docker) — subprocess bro_analysis chat
├── frontend/                   # Next.js (app/journal, app/analyst, app/watchlist, app/screener, app/advisor)
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

## 🔎 Screener (Tab 4)

Skor komposit teknikal untuk **seluruh universe** dihitung efisien (1 query ClickHouse + pandas groupby, cache 5 menit). Preset siap pakai: **Strong Buy, Oversold + Uptrend, Breakout Volume, Momentum Kuat, Oversold (RSI<30)**. Filter: timeframe, min skor, RSI, volume ratio, di atas MA200, dan **buang papan "Pemantauan Khusus"** (khas IDX). Tombol ★ menambah emiten ke watchlist.

## 🤖 AI Picks (Tab 3)

Saat tombol **🤖 Generate AI Picks** diklik, sistem memilih **top-15 saham bullish** (verdict BUY/STRONG BUY, skor tertinggi, exclude papan "Pemantauan Khusus") dari mesin skoring yang sama dengan Screener, lalu — **bila `LLM_BASE_URL` diisi** — meminta LLM memberi *reasoning* singkat per saham. Level **entry/target/cutloss dihitung deterministik dari ATR** (target `+2×ATR`, cutloss `−1.5×ATR`), bukan dari LLM.

- **Generate manual saja**: AI hanya jalan saat tombol diklik (hemat token LLM). Membuka halaman TIDAK memicu generate — hanya menampilkan batch terakhir yang tersimpan.
- **Provider-agnostic & opsional**: kosongkan `LLM_BASE_URL` → AI Picks tetap jalan (kartu rule-based tanpa reasoning), tanpa network call. Arahkan ke **Ollama/vLLM/LocalAI** self-hosted (BUKAN Claude API).
- **Non-blocking**: `POST /api/ai-picks/generate` menjalankan proses di background (FastAPI `BackgroundTasks`); frontend polling status tiap 4 detik selama proses.

---

## 🧠 AI Advisor (Tab 5)

Analisa mendalam **1 saham** atau minta **rekomendasi harian** via **Hermes Agent** (`bro_analysis`
CLI) — beda mekanisme dari AI Picks (batch, HTTP ke gateway LLM generik). Data teknikal
(RSI/MACD/ADX/Bollinger/skor/verdict) 100% dihitung dari **ClickHouse kita sendiri**
(`backend/indicators.py`, sama seperti Tab 2/3/4) — **bukan** yfinance/MCP, karena real-time
Yahoo/MCP kena rate-limit dari IP server ini, dan histori dataset MCP alternatif (GitHub
`Dataset-Saham-IDX`) sudah beku sejak Feb 2025 (lihat `docs/hermes-integration.md` §9 untuk detail).
Hermes dipanggil **tanpa** skill-nya, supaya tidak diam-diam fetch data sendiri lewat yfinance —
semua angka disuntik ke prompt.

**Dua fitur, dua peran AI yang beda:**
- **Analisa 1 Saham**: Hermes hanya menulis **narasi** dari data yang sudah dihitung (skor/level
  tetap deterministik, tidak dari LLM).
- **Rekomendasi Hari Ini**: Hermes **sendiri yang menyeleksi** — dikirim `AI_ADVISOR_POOL_SIZE`
  kandidat skor tertinggi (verdict apa pun, BUKAN pra-filter bullish), lalu Hermes mengevaluasi
  satu-satu terhadap kriteria (Momentum Breakout, Oversold Bounce, Trend Continuation) dan
  memutuskan sendiri maksimal `AI_ADVISOR_DAILY_TOP_N` mana yang genuinely layak (boleh lebih
  sedikit, tidak dipaksa penuh). Simbol pilihannya divalidasi terhadap pool (anti halusinasi
  ticker) — tapi **angka yang ditampilkan tetap 100% dari sistem kita**, Hermes cuma menentukan
  simbol mana yang lolos.

- **Generate manual saja & sinkron**: klik "Analisa dengan AI" / "Generate Rekomendasi" → satu
  kali panggilan Hermes, tunggu langsung (~10-50 detik untuk analisa 1 saham, bisa ~30-50 detik
  untuk rekomendasi harian krn Hermes evaluasi seluruh pool), tanpa polling (beda dari AI Picks
  yang batch 15 saham di background).
- **Butuh proses tambahan di HOST** (bukan Docker): Hermes (`bro_analysis`) hidup di host, backend
  di container tidak bisa akses langsung. Jalankan dulu:
  ```bash
  python3 scripts/hermes_advisor_bridge.py --port 8090 &
  ```
  Tanpa ini, Tab 5 tetap tampil data teknikal — cuma narasi/pilihan AI-nya fallback ke deterministik.
- **Data per tanggal X**: UI selalu tampilkan tanggal bar terakhir dipakai, supaya transparan
  soal freshness (data harian, bisa beberapa jam-hari kalau ingestion sedang di-rate-limit Yahoo).

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
| `AI_PICKS_TOP_N` | `15` | jumlah saham bullish teratas untuk AI Picks |
| `LLM_BASE_URL` | *(kosong)* | OpenAI-compatible base URL (mis. `http://host:11434/v1`); kosong = AI Picks rule-based only |
| `LLM_MODEL` | `llama3.1` | nama model di endpoint LLM |
| `LLM_API_KEY` | *(kosong)* | bila endpoint LLM butuh auth (Ollama biasanya kosong) |
| `HERMES_BRIDGE_URL` | `http://host.docker.internal:8090` | alamat `scripts/hermes_advisor_bridge.py` di host |
| `HERMES_BRIDGE_TIMEOUT_SECONDS` | `150` | timeout panggilan Hermes (init agent + LLM bisa lama) |
| `AI_ADVISOR_POOL_SIZE` | `50` | jumlah kandidat skor tertinggi (verdict apa pun) yang dievaluasi Hermes |
| `AI_ADVISOR_DAILY_TOP_N` | `8` | batas atas jumlah yang boleh dipilih Hermes (boleh lebih sedikit) |

---

## 🔌 API Utama

| Endpoint | Fungsi |
|---|---|
| `GET /api/symbols` | daftar emiten yang punya data |
| `GET /api/quotes?interval=1d` | quote ringkas semua emiten |
| `GET /api/history/{symbol}?interval=1d` | candles + indikator + signals |
| `WS /ws` | update bar real-time |
| `GET /api/screener?...` | screener/daily-picks (preset & filter) |
| `GET /api/screener/presets` | preset screener siap-pakai |
| `GET/POST/DELETE /api/watchlist` | watchlist manual |
| `GET /api/ai-picks` | batch AI Picks terbaru (read-only, tidak memicu generate) |
| `GET /api/ai-picks/status` | status generate (untuk polling) |
| `POST /api/ai-picks/generate` | **satu-satunya** pemicu generate (tombol di UI) |
| `POST /api/ai-advisor/analysis?symbol=` | analisa 1 saham (teknikal ClickHouse + narasi Hermes) |
| `POST /api/ai-advisor/daily-picks` | rekomendasi harian (top bullish + 1 komentar Hermes) |
| `GET/POST/PUT/DELETE /api/journal/positions` | portofolio |
| `GET/POST/DELETE /api/journal/transactions` | transaksi |
| `GET /api/journal/analytics` | analitik (win rate, equity curve, dll.) |

Dokumentasi interaktif: **http://localhost:8000/docs**

---

## 🗺️ Roadmap

- [x] Tab 1 — Trading Journal
- [x] Tab 2 — Trading Analyst (19 indikator + ticker tape)
- [x] Tab 3 — Watchlist + AI Picks (provider-agnostic, OpenAI-compatible → Ollama/vLLM self-hosted)
- [x] Tab 4 — Screener (rule-based)
- [x] Tab 5 — AI Advisor (Hermes CLI via bridge HTTP, analisa 1 saham + rekomendasi harian)
- [ ] Tab Fundamental Analyst
- [ ] Data fundamental (P/E, ROE, dll.) — belum ada sumber (ClickHouse hanya OHLCV)
- [ ] Import CSV transaksi dari broker

---

## 📚 Dokumentasi lain

- **[docs/prd-tradingApp.md](docs/prd-tradingApp.md)** — PRD v2.0 (as-built): fitur per tab, decision log, backlog & open questions
- **[TESTING.md](TESTING.md)** — cara test backend API, pipeline, & frontend (Playwright via Docker)
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — kalau data tidak tampil (terutama saat deploy di server/VPS)
- **[docs/hermes-integration.md](docs/hermes-integration.md)** — panduan integrasi Hermes Agent untuk AI Advisor (Tab 5)
- **[CLAUDE.md](CLAUDE.md)** — detail teknis & gotchas untuk pengembangan

## 📝 Catatan

- Data **delay ~15 menit**; saat market tutup, candle terakhir tidak berubah.
- Universe ~949 emiten di-**auto-fetch** saat startup; sebagian emiten illikuid mungkin tanpa data intraday.
- **Deploy di server:** buka port **3001** & **8000** di firewall/security group. yFinance bisa diblok dari IP VPS — lihat [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
