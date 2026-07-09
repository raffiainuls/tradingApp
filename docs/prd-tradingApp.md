# PRD — Personal Stock Trading App (IDX)

**Status:** v2.0 — as-built, disesuaikan dengan kondisi development terakhir
**Owner:** Internal / Solo Use
**Last Updated:** 2026-07-09
**Menggantikan:** Draft v0.1 (Juni 2026, `~/documents/PRD_TradingApp (1).md`)

> Dokumen ini merekam **apa yang sudah dibangun dan keputusan-keputusan yang diambil**, plus
> backlog yang belum. Detail teknis implementasi & gotchas ada di [CLAUDE.md](../CLAUDE.md);
> cara menjalankan ada di [README.md](../README.md).

---

## 1. Ringkasan Produk

Aplikasi web personal untuk mendukung aktivitas trading saham di pasar IDX. Mencakup pencatatan
portofolio & jurnal trading, analisis teknikal chart-based, watchlist + AI Picks, screener
rule-based seluruh universe (~949 emiten), dan AI Advisor berbasis Hermes Agent. Dibangun untuk
digunakan secara mandiri oleh satu pengguna (tanpa auth), self-hosted via Docker Compose.

**Status keseluruhan: 5 tab utama sudah live.** Tab Fundamental belum dibangun (terblokir
ketiadaan sumber data fundamental — lihat §9).

---

## 2. Tujuan & Sasaran

- Memusatkan semua aktivitas riset dan pencatatan trading di satu tempat
- Mengurangi bias keputusan dengan data dan analisis yang terstruktur
- Memanfaatkan AI untuk reasoning kandidat saham & analisa mendalam — dengan **angka selalu
  dari sistem sendiri (deterministik), AI tidak pernah dipercaya soal angka**
- Membangun data historis trading sendiri sebagai aset jangka panjang

---

## 3. Tech Stack (aktual)

| Layer | Teknologi |
|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind + lightweight-charts 4 |
| Backend API | FastAPI + uvicorn (clickhouse-connect, psycopg2, pandas/numpy) |
| Message Broker | Apache Kafka (Confluent 7.5.0) — topik `raw-ohlcv`, `ohlc-live` |
| Time-series DB | ClickHouse 24.3 (`market.ohlcv`, ReplacingMergeTree) |
| Relational DB | PostgreSQL 16 (porto, transaksi, jurnal, watchlist, ai_picks) |
| Data source | yFinance (`.JK` tickers, `^JKSE`→IHSG), delay ~15 menit, poll 300s |
| Universe | Auto-fetch `all.csv` dari repo Dataset-Saham-IDX (~949 emiten) |
| AI — Tab 3 (AI Picks) | LLM generik self-hosted via HTTP OpenAI-compatible (`LLM_BASE_URL`) — Ollama/vLLM/LocalAI |
| AI — Tab 5 (AI Advisor) | Hermes Agent (`bro_analysis` CLI) via bridge HTTP di host |
| Deployment | Docker Compose (self-hosted); bridge Hermes jalan di host, bukan container |

Perubahan dari draft v0.1: React murni → **Next.js 14**; InfluxDB (sempat ada di implementasi
awal) → **dihapus**, ClickHouse satu-satunya time-series store; `@baguskto/saham` MCP →
**dibatalkan** (lihat §6).

---

## 4. Arsitektur Data Flow (aktual)

```
yFinance (delay 15m, ~949 emiten IDX, poll 300s)
   → ingestion/poller.py   (TCP server :9009, stream pipe-delimited bar, handshake "HELLO")
   → tcp-bridge/bridge.py  (TCP client → Kafka topic `raw-ohlcv`)
   → clickhouse-writer     (Kafka → ClickHouse `market.ohlcv` + re-publish ke Kafka `ohlc-live`)
   → backend (FastAPI)     (REST: history + indikator + screener dari ClickHouse;
                            WS hub: consume `ohlc-live` → broadcast ke browser)
   → frontend (Next.js)    (Tab 1–5 + ticker tape footer)

PostgreSQL ← backend (porto, transaksi, jurnal, watchlist, ai_picks)   [Tab 1 & 3]
ClickHouse ← storage permanen OHLCV                                    [Tab 2/3/4/5]

── Lapisan AI (dua mekanisme TERPISAH, jangan ditukar) ──────────────────────────
Tab 3 AI Picks   : backend → HTTP OpenAI-compatible (LLM_BASE_URL) → LLM self-hosted
                   (batch banyak saham; LLM_BASE_URL kosong = no-op, tetap jalan rule-based)
Tab 5 AI Advisor : backend (Docker) → HTTP → scripts/hermes_advisor_bridge.py (HOST :8090)
                   → subprocess `bro_analysis chat -q` (single-stock / single-batch)
                   Data teknikal 100% dari ClickHouse + indicators.py — Hermes hanya menulis
                   narasi & memilih simbol, TIDAK fetch/hitung data sendiri.
```

Perbedaan besar dari draft v0.1: ada lapisan **TCP (poller ↔ tcp-bridge)** sebelum Kafka,
ada topik `ohlc-live` + **WebSocket** untuk update live ke frontend, dan **AI agent tidak
memakai MCP/dataset eksternal apa pun** — semua data dari ClickHouse sendiri.

---

## 5. Modul & Fitur

### Tab 1 — Trading Journal ✅

- Portofolio aktif: input manual (kode, lot, harga beli, tanggal), unrealized P&L, alokasi sektor
- Log transaksi beli/jual + kalkulasi **realized P&L FIFO** per transaksi & per emiten
- Analitik: win rate, profit factor, average holding period, best/worst trade, equity curve
- Catatan per posisi (alasan beli, target, cut loss)
- Belum ada: import CSV broker (Stockbit/IPOT) — backlog

### Tab 2 — Trading Analyst ✅

- Candlestick multi-timeframe (5m/15m/1h/1d/1wk) dengan zoom/pan, volume bar, live via WebSocket
- **19 indikator** multi-pane tersinkron (`backend/indicators.py`):
  - Trend: SMA(20/50/200), EMA(20/50), MACD, ADX/DMI, Parabolic SAR
  - Momentum: RSI, Stochastic, Williams %R, CCI
  - Volatility: Bollinger Bands, ATR, Keltner Channel
  - Volume: VWAP (session-reset intraday), OBV, A/D Line, Volume Profile (POC)
- Ringkasan teknikal: verdict + skor komposit −100..+100 (`latest_signals()`)
- Ticker tape footer (top-60 by volume), deep-link `?symbol=` dari tab lain
- Belum ada: drawing tools (S/R manual, trendline, Fibonacci) & multi-timeframe view — backlog

### Tab 3 — Watchlist + AI Picks ✅

- **Watchlist manual**: CRUD + catatan per emiten, di-enrich skor dari cache screener
- **AI Picks**: top-15 bullish dari mesin skoring rule-based →
  - Reasoning naratif per saham via LLM generik (batch, HTTP OpenAI-compatible) — **opsional**:
    `LLM_BASE_URL` kosong = kartu tetap tampil rule-based dengan `reasoning=null`
  - Level harga **deterministik dari backend, bukan LLM**: entry=`close`,
    target=`close+2×ATR`, cutloss=`close−1.5×ATR`
  - Generate **MANUAL saja** (tombol → `POST /generate` via BackgroundTasks; polling status 4s;
    lock anti-paralel). Auto-generate TTL sengaja dihapus — hemat token LLM.

### Tab 4 — Screener ✅

- Rule-based, seluruh universe ~949 emiten: 1 query ClickHouse + pandas, cached 5 menit
- Skor komposit + verdict, preset siap pakai, filter (skor, verdict, harga, volume, dll.)
- Emiten papan "Pemantauan Khusus" dibuang otomatis (board_map dari `all.csv`)
- Klik emiten → Tab 2 Analyst; ★ → tambah ke watchlist
- Keputusan: **rule-based saja, tanpa "AI screener"** — peran AI ada di Tab 3 (reasoning) dan
  Tab 5 (seleksi), bukan di screener

### Tab 5 — AI Advisor (Hermes Agent) ✅

- **Analisa 1 saham**: semua angka teknikal dihitung backend (ClickHouse + `indicators.py`),
  dikirim dalam prompt → Hermes hanya menulis narasi analisa. Panel teknikal tetap tampil
  meski bridge Hermes mati (narasi AI-nya saja yang absen).
- **Rekomendasi Hari Ini — genuinely AI-driven**: pool kandidat top-skor **verdict apa pun**
  (bukan pre-filter bullish) dikirim semua ke Hermes + kriteria eksplisit (Momentum Breakout /
  Oversold Bounce / Trend Continuation) → **Hermes sendiri yang menyeleksi** (boleh 0 s.d. N,
  tidak dipaksa penuh). Simbol pilihan diparse dari baris `PILIHAN:`; simbol halusinasi dibuang;
  angka yang ditampilkan tetap 100% dari sistem. Fallback deterministik (top-N by score) kalau
  parsing gagal/bridge mati — tidak pernah blank.
- Eksekusi **manual & sinkron** (1 panggilan Hermes per klik, ~10–90 detik, spinner tanpa
  polling); hasil **ephemeral** (tidak disimpan ke DB)
- Belum ada (dari visi v0.1): rekomendasi hold/sell porto aktif, chat interface bebas,
  alert/notifikasi — backlog §9

### Tab Fundamental — ❌ belum dibangun

Belum punya slot di sidebar. Terblokir sumber data: ClickHouse hanya OHLCV; yfinance kena 429
dari IP server; saham-mcp datanya beku. Perlu sumber fundamental terpisah dulu (lihat §9).

---

## 6. Keputusan Desain Penting (decision log)

| Keputusan | Alasan |
|---|---|
| **`@baguskto/saham` MCP & Dataset-Saham-IDX DIBATALKAN sebagai sumber data AI** (draft v0.1 menjadikannya pilar Tab 5) | Diverifikasi empiris 2026-07-01: real-time yfinance/saham-mcp kena **429** dari IP server (AS132203 Tencent Cloud — anti-bot menilai reputasi per ASN); histori GitHub-nya **beku sejak Feb 2025**, lebih basi dari ClickHouse sendiri |
| AI Advisor & semua tab pakai **ClickHouse + `indicators.py` sendiri** | Self-healing, konsisten antar tab, satu sumber kebenaran |
| **Dua mekanisme AI terpisah**: Tab 3 = LLM generik HTTP (batch); Tab 5 = Hermes CLI via bridge host (single) | Batch 15 saham butuh endpoint murah/self-hosted; analisa mendalam butuh agent (Hermes). Jangan ditukar |
| Tab 3 **provider-agnostic, BUKAN Claude API** | Biaya — reasoning batch harian lebih murah di LLM self-hosted |
| Hermes dipanggil **tanpa `--skills`** | Skill-nya menyuruh agent fetch sendiri via yfinance → 429 + angka tidak konsisten dgn backend. Prompt sudah berisi semua angka |
| Bridge HTTP di host (`hermes_advisor_bridge.py`), bukan subprocess dari container | `bro_analysis` hanya ada di PATH host; filesystem container beda. Pola sama dgn `LLM_BASE_URL` |
| Level harga AI Picks **deterministik dari ATR di backend** | Supaya angka tidak dikarang LLM |
| Generate AI Picks **manual saja** (auto-TTL dihapus) | Permintaan user — hemat token LLM |
| Hasil Tab 5 **ephemeral** (tanpa tabel baru) | Satu panggilan per klik, regenerate murah, tidak perlu histori |
| **Rule-based screener** (bukan AI/hybrid) | Menjawab Open Question #3 draft v0.1 |
| **Tanpa auth** | Solo use, self-hosted — menjawab Open Question #6 |

---

## 7. Data Sources (aktual)

| Sumber | Jenis Data | Dipakai Oleh | Status |
|---|---|---|---|
| yFinance (via pipeline Kafka→ClickHouse) | OHLCV ~949 emiten + IHSG | Semua tab | ✅ Aktif (delay 15m; poll dari server bisa kena 429 — lihat TROUBLESHOOTING.md) |
| `all.csv` Dataset-Saham-IDX (GitHub) | Daftar universe + papan pencatatan | ingestion (universe), screener (board_map) | ✅ Aktif — **hanya metadata**, bukan data harga |
| `@baguskto/saham` MCP | — | — | ❌ Dibatalkan (429 + data beku, §6) |
| Fundamental (laporan keuangan) | P/E, ROE, EPS, dll. | Tab Fundamental (rencana) | ❌ Belum ada sumber |
| Broker summary / smart money | Akumulasi/distribusi broker | Enhancement (rencana) | 🔍 Riset selesai, belum ada yang lolos uji — lihat [enhancement.md](enhancement.md) |

---

## 8. Status Fase Pengembangan

### Fase 1 — MVP (Core Journal + Chart) ✅ SELESAI
- [x] Infrastruktur: Kafka, ClickHouse, PostgreSQL, FastAPI, Next.js (Docker Compose)
- [x] Ingestion pipeline: yFinance → TCP → Kafka → ClickHouse
- [x] Tab 1: Trading Journal (porto + transaksi + analitik FIFO)
- [x] Tab 2: Chart interaktif + 19 indikator + WebSocket live

### Fase 2 — Watchlist + Screener ✅ SELESAI (minus Fundamental)
- [x] Tab 3: Watchlist manual + AI Picks
- [x] Tab 4: Screener rule-based (preset + filter)
- [ ] Tab Fundamental — terblokir sumber data
- [ ] Import CSV dari broker

### Fase 3 — AI Agent ✅ SEBAGIAN
- [x] Integrasi Hermes (bridge host) + LLM generik self-hosted
- [x] Tab 5: Analisa mendalam 1 saham
- [x] Tab 5: Rekomendasi saham harian (Hermes menyeleksi sendiri)
- [ ] Rekomendasi hold/sell untuk porto aktif
- [ ] Chat interface bebas dengan AI
- [ ] Alert & notifikasi

---

## 9. Backlog & Roadmap

Prioritas dari [enhancement.md](enhancement.md) (indikator & analisis, urut effort-vs-value):

1. **Market breadth** (% saham > SMA200, advance/decline, distribusi verdict) — nol dependency
   data baru, bahan sudah ada dari scan screener
2. **Masukkan indikator nganggur ke skor** — Stochastic/CCI/OBV dkk sudah dihitung tapi belum
   menyumbang `latest_signals()`
3. **SuperTrend** — reuse `atr()` yang ada
4. **Candlestick pattern recognition** — sudah dirujuk implisit oleh prompt AI Advisor
5. **Benerin data sektor (NULL semua) + isi data mingguan (kosong)** — prasyarat rotasi sektor
   & konfirmasi multi-timeframe

Fitur produk:
- Rekomendasi hold/sell porto aktif (Tab 5) — porto sudah ada di Postgres, tinggal orkestrasi
- Import CSV broker (Tab 1)
- Chat interface + alert/notifikasi (Tab 5) — visi lama v0.1, belum diprioritaskan
- Tab Fundamental — menunggu keputusan sumber data
- Drawing tools di chart (Tab 2)

Riset terbuka:
- **Broker summary**: 8 kandidat diriset (Tier 1: Sectors.app, GOAPI.IO, NeaByteLab/IDX-API,
  Invezgo, datasaham.io). NeaByteLab sudah diuji langsung 2026-07-04: kode benar, tapi endpoint
  IDX kena Cloudflare challenge dari IP server — kemungkinan jalan dari IP residential. Detail
  lengkap di [enhancement.md](enhancement.md).
- **Data fresh permanen** (mengurangi risiko 429): kurangi `POLL_INTERVAL` (skor cuma butuh
  data harian) / data EOD resmi IDX / proxy residential

---

## 10. Open Questions

| # | Pertanyaan | Status |
|---|---|---|
| 1 | Indikator & metrik AI Picks Tab 3 | ✅ Terjawab — skoring rule-based + level ATR + reasoning LLM opsional |
| 2 | Fitur spesifik Tab 2 Analyst | ✅ Terjawab — 19 indikator multi-pane + technical summary (drawing tools backlog) |
| 3 | Screener: rule-based / AI / hybrid | ✅ Terjawab — rule-based saja |
| 4 | Sumber data fundamental IDX | ⏳ MASIH TERBUKA — yfinance 429, saham-mcp beku, perlu sumber baru |
| 5 | LLM Tab 5 | ✅ Terjawab — Hermes via bridge host (Tab 5); LLM generik self-hosted (Tab 3) |
| 6 | Authentication | ✅ Terjawab — tidak perlu (solo, self-hosted) |
| 7 | Deployment target | ✅ Terjawab — Docker Compose di server sendiri; catatan: IP datacenter kena anti-bot (Yahoo/IDX/Cloudflare), lihat TROUBLESHOOTING.md |
| 8 | Sumber broker summary (baru) | ⏳ TERBUKA — riset selesai, kandidat belum ada yang lolos uji dari server ini |

---

*v2.0 ditulis 2026-07-09 sebagai potret as-built. Update dokumen ini saat ada keputusan desain
baru atau fitur backlog yang selesai.*
