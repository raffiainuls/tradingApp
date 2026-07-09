# CLAUDE.md — IDX Trading App

Panduan untuk Claude Code saat bekerja di project ini.

## Gambaran

Aplikasi web personal untuk trading saham IDX. Mengikuti `docs/prd-tradingApp.md` (v2.0 as-built).
Status saat ini: **Tab 1 (Journal), Tab 2 (Analyst), Tab 3 (Watchlist + AI Picks), Tab 4 (Screener), Tab 5 (AI Advisor)** sudah dibangun.
Tab 3 = watchlist manual + **AI Picks** (top-15 bullish dari mesin skoring; reasoning LLM batch via HTTP OpenAI-compatible; level entry/target/cutloss deterministik dari ATR). Tab 4 = screener/daily-picks rule-based (backend/screener.py: skor komposit 949 emiten dari ClickHouse, cached 5m; preset + filter; buang papan "Pemantauan Khusus" via board_map dari all.csv). Tab 5 = **AI Advisor** — analisa single-stock + rekomendasi harian via **Hermes Agent** (`bro_analysis`), data teknikal 100% dari ClickHouse kita sendiri (BUKAN yfinance/MCP — lihat gotcha di bawah kenapa).
**Lapisan AI Picks (Tab 3) provider-agnostic**: HTTP OpenAI-compatible `LLM_BASE_URL`/`LLM_MODEL` → Ollama/vLLM/LocalAI self-hosted (BUKAN Claude API krn biaya). `LLM_BASE_URL` kosong (default) = no-op instan, AI Picks tetap jalan rule-based tanpa reasoning.
**AI Advisor (Tab 5) pakai Hermes CLI subprocess** (single-stock/single-batch, `docs/hermes-integration.md`) via **bridge HTTP di host** (`scripts/hermes_advisor_bridge.py`) — **beda mekanisme** dari AI Picks (batch banyak saham, HTTP ke gateway LLM generik). JANGAN ditukar.
Tab Fundamental belum punya slot di Sidebar.

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
backend/config.py         → env (ClickHouse + Postgres + Kafka + AI Picks + LLM generik)
backend/db.py             → ClickHouse client (THREAD-LOCAL, krn FastAPI threadpool) + Postgres pool + ensure_*_table()
backend/indicators.py     → SEMUA indikator (Trend/Momentum/Volatility/Volume) + signals
backend/realtime.py       → WS connection set + broadcast
backend/screener.py       → scoring engine 949 emiten (1 query ClickHouse + pandas groupby, cached 5m) + filter
backend/llm_client.py     → klien LLM generik OpenAI-compatible (call_llm); LLM_BASE_URL kosong = no-op instan
backend/ai_picks.py       → orkestrasi AI Picks (top-N bullish + reasoning LLM + level ATR), state in-memory + lock
backend/hermes_bridge.py  → klien HTTP ke Hermes Advisor Bridge (host); ask_hermes() NEVER raise
backend/ai_advisor.py     → orkestrasi AI Advisor: analyze_symbol() (1 saham) + daily_recommendations() (Hermes SENDIRI menyeleksi dari pool luas, bukan cuma komentar)
backend/routers/market.py → Tab 2: /api/symbols, /api/history, /api/quotes, /ws (data-driven dari ClickHouse)
backend/routers/journal.py→ Tab 1: positions, transactions, analytics (FIFO P&L)
backend/routers/watchlist.py → Tab 3: /api/watchlist (CRUD manual, enrich skor dari screener cache)
backend/routers/screener.py  → Tab 4: /api/screener, /api/screener/presets (rule-based)
backend/routers/ai_picks.py  → Tab 3: /api/ai-picks (read-only) +/status +/generate (generate MANUAL via BackgroundTasks)
backend/routers/ai_advisor.py→ Tab 5: POST /api/ai-advisor/analysis?symbol=, POST /api/ai-advisor/daily-picks (sinkron, manual)
backend/main.py           → app, lifespan (ensure_watchlist_table + ensure_ai_picks_table), Kafka consumer thread (ohlc-live → WS)
scripts/hermes_advisor_bridge.py → HTTP kecil (stdlib only) di HOST yg subprocess `bro_analysis chat -q`, dipakai backend Tab 5
db/clickhouse-init.sql    → schema market.ohlcv (ReplacingMergeTree)
db/init.sql               → Postgres schema positions + transactions + watchlist + ai_picks (+ seed) — Tab 5 TANPA tabel baru (ephemeral)
frontend/app/analyst/     → Tab 2 page (+ TickerTape footer; baca ?symbol= dari URL)
frontend/app/journal/     → Tab 1 page
frontend/app/watchlist/   → Tab 3 page (watchlist manual + AI Picks card grid + polling status)
frontend/app/screener/    → Tab 4 page (screener: preset + filter + tabel ranking, ★ tambah ke watchlist)
frontend/app/advisor/     → Tab 5 page (form analisa 1 saham + tombol rekomendasi harian; baca ?symbol= dari URL)
frontend/components/AnalystChart.tsx → multi-pane synced lightweight-charts (localization en-US)
frontend/components/TickerTape.tsx   → marquee footer (top-60 by volume)
frontend/components/VerdictBadge.tsx → badge verdict (shared: Screener + AI Picks + AI Advisor)
frontend/components/TechnicalSummary.tsx → panel verdict+skor+indikator dari tipe `Signals` (shared: Analyst + AI Advisor)
frontend/components/Sidebar.tsx      → nav; `ready:true` utk tab yang aktif
frontend/lib/api.ts       → base URL diturunkan runtime dari window.location (bukan hardcode localhost)
frontend/lib/types.ts, format.ts (format manual ID, tanpa toLocaleString; scoreColor)
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

Untuk Tab 5 (AI Advisor) — bridge dijalankan di mesin tempat Hermes (`bro_analysis`) terinstal.
**Topologi sejak migrasi ke laptop (2026-07-09): app jalan di laptop ini (Windows, IP
residential — solusi 429 Yahoo), Hermes + bridge TETAP di server VPS**
(`docs/hermes-server-migration.md`). Di VPS:
```bash
HERMES_BRIDGE_API_KEY=<key> python3 scripts/hermes_advisor_bridge.py --port 8090 &
```
lalu di `.env` laptop isi `HERMES_BRIDGE_URL=http://<IP Tailscale/publik VPS>:8090` +
`HERMES_BRIDGE_API_KEY` (sama dgn di VPS). Tanpa/selama belum di-set, Tab 5 tetap tampil
(data teknikal dari ClickHouse), cuma narasi AI-nya absen.

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
- **AI Picks (Tab 3) — sudah dibangun, provider-agnostic**: `llm_client.call_llm()` HTTP OpenAI-compatible (`LLM_BASE_URL`/`LLM_MODEL`) → Ollama/vLLM/LocalAI. **`LLM_BASE_URL` kosong = no-op INSTAN tanpa network call** (beda dari Hermes CLI yang masih spawn subprocess lalu catch `FileNotFoundError`); AI Picks tetap menghasilkan kartu rule-based dengan `reasoning=null`. `call_llm` NEVER raise — 1 saham gagal tidak menggagalkan batch.
- **AI Picks trigger/concurrency — MANUAL SAJA (tanpa auto/TTL)**: `GET /api/ai-picks` read-only, TIDAK memicu generate. Generate HANYA lewat `POST /api/ai-picks/generate` (tombol di UI) → `ai_picks.generate` via FastAPI `BackgroundTasks` (jalan SETELAH response dikirim, jadi POST tetap cepat). Frontend polling `/status` tiap 4 detik SELAMA `generating:true`, reload picks saat selesai (cross-tab konvergen). `_lock` (non-blocking acquire) cegah generate paralel (double-click / multi-tab). State in-memory aman krn backend 1 worker uvicorn (tanpa `--workers`). Frontend optimis set `generating:true` setelah POST krn BackgroundTasks belum sempat flip state. (Auto-generate berbasis TTL sengaja DIHAPUS atas permintaan user — hemat token LLM.)
- **Level harga AI Picks deterministik**: entry=`close`, target=`close+2×ATR`, cutloss=`close−1.5×ATR` (fallback ATR≈2% close). Dihitung di backend (`ai_picks._levels`), BUKAN dari LLM — supaya angka tidak ngarang.
- **AI Picks ≠ AI Advisor**: AI Picks (Tab 3) = batch banyak saham via HTTP (`llm_client.py`). Tab 5 AI Advisor = single-stock/single-batch via Hermes CLI subprocess (`docs/hermes-integration.md`). Dua mekanisme berbeda, JANGAN ditukar.
- **AI Advisor (Tab 5) — kenapa TIDAK pakai yfinance/saham-mcp**: sudah diverifikasi empiris (2026-07-01) — real-time yfinance/saham-mcp 429 dari IP server ini (sama kayak masalah ingestion); histori GitHub dataset saham-mcp (`wildangunawan/Dataset-Saham-IDX`) BEKU sejak commit terakhir 2025-02-23, lebih basi dari ClickHouse kita sendiri. Keputusan: AI Advisor 100% pakai ClickHouse+`indicators.py` (self-healing, sama seperti Tab 3/4), TIDAK integrasi saham-mcp. Kalau nanti mau data fresh permanen, opsi realistis: (a) kurangi `POLL_INTERVAL` krn skor cuma butuh data harian, (b) data resmi EOD dari IDX (belum diriset endpointnya), (c) proxy residential/poller dari IP rumah (berbayar/perlu infra tambahan) — di luar scope Tab 5.
- **Kenapa IP datacenter kena block tapi IP rumah kemungkinan tidak**: sistem anti-bot (Yahoo, Cloudflare) menilai reputasi di level ASN — traffic dari blok IP cloud provider (AWS/GCP/Tencent/dst, termasuk IP server ini: `43.134.129.64` = AS132203 Tencent Cloud Singapore) default dicurigai krn manusia asli nyaris tidak pernah browsing dari sana, beda dgn IP residential ISP yang dipakai jutaan user biasa (blokir massal = terlalu banyak korban tak berdosa bagi provider).
- **AI Advisor — backend (Docker) tidak bisa langsung panggil Hermes (host)**: `bro_analysis` cuma ada di PATH HOST VPS (`~/.local/bin`), backend jalan di CONTAINER — filesystem beda, subprocess langsung/sys.path-import ala contoh lama di `docs/hermes-integration.md` TIDAK JALAN tanpa volume-mount yang rapuh. Solusi: `scripts/hermes_advisor_bridge.py` — HTTP kecil (stdlib only) yang jalan di mesin Hermes, backend panggil via `HERMES_BRIDGE_URL`. Pola ini identik dgn `LLM_BASE_URL` (Tab 3) — HTTP, bukan proses lokal.
- **AI Advisor — topologi LINTAS MESIN sejak migrasi laptop (2026-07-09)**: app di laptop (IP residential), Hermes + bridge tetap di VPS → `HERMES_BRIDGE_URL` bukan lagi `host.docker.internal` melainkan IP Tailscale/publik VPS. Konsekuensi: bridge sekarang punya auth — `POST /advise` cek `Authorization: Bearer <HERMES_BRIDGE_API_KEY>` (`hmac.compare_digest`; `/health` tetap terbuka; env kosong = auth nonaktif utk topologi satu-mesin lama), backend kirim header itu dari `config.HERMES_BRIDGE_API_KEY`. `ask_hermes()` tetap NEVER raise → koneksi laptop↔VPS putus = narasi AI absen, data teknikal tetap tampil. `extra_hosts` di compose dibiarkan (harmless). Detail & checklist operasional: `docs/hermes-server-migration.md`.
- **AI Advisor — SENGAJA tidak pakai `--skills` Hermes**: skill `stock-technical-fundamental-analysis`/`daily-stock-picks` (lihat SKILL.md masing-masing) instruksikan agent fetch sendiri via `yf.Ticker(...).history()` begitu skill dimuat — persis yang mau dihindari (429 & data tidak konsisten dgn yang sudah dihitung backend). Jadi `hermes_advisor_bridge.py` panggil `bro_analysis chat -q "<prompt>"` POLOS (tanpa `--skills`), dan prompt-nya SUDAH menyertakan semua angka teknikal — Hermes cuma diminta menulis narasi, bukan fetch/hitung ulang. `_SYSTEM_PREAMBLE` di `ai_advisor.py` eksplisit larang Hermes fetch data lain.
- **AI Advisor — parsing output Hermes CLI**: `bro_analysis chat -q` bungkus jawaban dalam box unicode (`╭─ ⚕ Hermes ─...─╮` ... `╰─...─╯`), tiap baris di-indent 4 spasi, tanpa kode ANSI saat di-capture non-interactive (`subprocess.run(capture_output=True)`). `hermes_advisor_bridge.py::_extract_reply()` regex-parse ini. Kalau Hermes CLI berubah format output di versi mendatang, parser ini yang perlu disesuaikan duluan.
- **AI Advisor — generate MANUAL & SINKRON (bukan BackgroundTasks)**: beda dari AI Picks (batch 15 saham → perlu background+polling), Tab 5 cuma SATU panggilan Hermes per klik (baik analisa 1 saham maupun 1 batch komentar harian) — jadi endpoint langsung `return` (blocking di threadpool FastAPI, ~10-90 detik tergantung beban Hermes), frontend cukup tampilkan spinner tanpa polling. Tidak ada tabel Postgres baru — hasil ephemeral (tidak disimpan), regenerate tiap klik.
- **AI Advisor — fundamental data (P/E, ROE, dst) BELUM ada**: ClickHouse cuma simpan OHLCV, bukan fundamental. Sengaja tidak fetch dari yfinance (429). Kalau mau nanti, perlu sumber data terpisah (bukan ClickHouse/yfinance/saham-mcp).
- **AI Advisor — "Rekomendasi Hari Ini" Hermes SENDIRI yang menyeleksi (genuinely AI-driven), bukan cuma komentar**: revisi dari desain awal (2026-07-01) atas permintaan user — desain pertama (Hermes cuma menulis komentar di atas top-N bullish yang SUDAH kita filter) dianggap terlalu mirip mekanisme AI Picks Tab 3. Desain final: `ai_advisor._candidate_pool(AI_ADVISOR_POOL_SIZE)` ambil top-skor **verdict apa pun** (BUKAN cuma bullish, cuma exclude papan Khusus) → kirim SEMUA ke Hermes dengan kriteria eksplisit dari skill `daily-stock-picks` (Momentum Breakout/Oversold Bounce/Trend Continuation) di prompt → Hermes evaluasi satu-satu & putuskan sendiri mana yang lolos (boleh 0 s.d. `AI_ADVISOR_DAILY_TOP_N`, TIDAK dipaksa penuh). Simbol pilihan di-ekstrak dari baris `PILIHAN: SYM1,SYM2,...` di akhir respons (`ai_advisor._parse_picks`, regex + validasi terhadap pool — simbol halusinasi/di luar pool dibuang diam-diam). **Angka yang ditampilkan tetap 100% dari sistem** (diambil dari pool kita berdasarkan simbol yang dipilih Hermes), Hermes cuma menentukan simbol mana yang lolos + alasannya — tidak pernah dipercaya soal angka. Fallback kalau parsing gagal/bridge mati: top-N pool by score (deterministik, tidak pernah blank).
- **AI Advisor daily-picks lebih lambat dari desain sebelumnya**: karena sekarang Hermes mengevaluasi SELURUH pool (bisa 40-50 baris data) satu-satu (bukan cuma comment atas 8-10 yang sudah difilter), latency naik jadi ~30-50 detik (pernah tercatat 49s) dari sebelumnya ~10-20 detik. Masih di bawah `HERMES_BRIDGE_TIMEOUT_SECONDS` (150s).

## Riset: Kandidat API Broker Summary IDX (2026-07-01, BELUM diimplementasi/diuji langsung)

Konteks: skill Hermes `stock-technical-fundamental-analysis` punya framework analisis Broker
Summary (Fase 6 — akumulasi/distribusi smart money, Dow Theory phases) tapi **eksplisit bilang
datanya tidak tersedia via yfinance**, harus dari sumber eksternal. Di bawah ini hasil riset 8
kandidat penyedia data — **cuma riset dokumentasi/kode publik, belum ada yang benar-benar dites
integrasinya**. Kalau mau lanjut ke implementasi, verifikasi ulang harga & uji panggilan API asli
dulu (jangan percaya begitu saja — `saham-mcp` sebelumnya juga awalnya terlihat meyakinkan
tapi ternyata data historisnya beku & real-time-nya 429).

**Tier 1 — endpoint broker summary terkonfirmasi ada (bukti dari dokumentasi/kode, bukan cuma marketing):**
1. **[Sectors.app](https://sectors.app/)** — PALING lengkap: 7 endpoint khusus broker
   (`GET /v2/broker-summary/{symbol}/`, `broker-activity-top`, `broker-registry`,
   `foreign-flow-by-symbol`, dll — lihat [dokumentasi source](https://github.com/supertypeai/sectors_api_docs/tree/main/api-references/v2/indonesia/brokers)).
   Auth via header `Authorization: [API_KEY]`. **Berbayar** — endpoint API cuma untuk subscriber
   "Insider Plan"; harga persis tidak bisa diverifikasi (halaman pricing 403 dari IP server ini,
   kemungkinan Cloudflare — sama seperti masalah kita akses idx.co.id).
2. **[GOAPI.IO](https://goapi.io/)** — endpoint `getBrokerSummary(symbol, date)` terkonfirmasi
   nyata di [PHP SDK](https://github.com/goapi-io/php-sdk) & Elixir SDK, didokumentasikan di
   Swagger (`goapi.io/swagger/`). Produk "Stock Market IDX" ada free trial tanpa kuota jelas;
   harga berbayar tidak jelas (satu-satunya angka yang ketemu promo basi 2023, ~Rp 600-900rb/bulan
   — JANGAN dianggap harga sekarang).
3. **[NeaByteLab/IDX-API](https://github.com/NeaByteLab/IDX-API)** (GitHub, open source, MIT) —
   fungsi `syncBrokerSummary()` kategori "Trading Modules", **klaim pakai API RESMI IDX langsung**
   (bukan scraping), sync ke SQLite lokal via Deno v2.5+. **Gratis & self-hosted** — paling
   menjanjikan kalau klaim "API resmi IDX"-nya benar (belum kita tes jalankan), krn menghindari
   biaya vendor pihak ketiga. Worth dicoba clone & jalankan sungguhan sebelum percaya penuh.
4. **[Invezgo](https://invezgo.com/id/data-api-saham-indonesia)** — modul `analysis` di
   [JS SDK](https://github.com/Invezgo/invezgo-js-sdk) eksplisit sebut fitur "broker summary,
   broker stalker, inventory chart, momentum chart"; Go SDK punya `GetBrokerList()`. Method/endpoint
   persis broker summary tidak ketemu di README (perlu cek `api.invezgo.com/documentation`,
   situs utama 403 dari sini). Berbayar, harga tidak ketemu.
5. **[datasaham.io](https://datasaham.io/)** (BEDA dari datasaham.id yang cuma app mobile) —
   klaim endpoint broker summary eksplisit di landing page, tapi **pendaftaran API publik lagi
   ditutup** ("hanya untuk user terpilih").

**Tier 2 — tidak relevan / klaim tidak terkonfirmasi:**
6. **POEMS (Phillip Sekuritas)** — API trading utk akun sendiri, cakupan SGX/Jepang/HK/US/China,
   Indonesia/IDX TIDAK disebut sama sekali, tidak ada fitur broker summary. Tidak relevan.
7. **[OHLC.dev](https://ohlc.dev/indonesia-stock-exchange-idx-api)** — "broker summaries" cuma
   disebut di copy marketing, endpoint konkret yang ditunjukkan cuma `/trading/summary` dkk
   (tanpa endpoint broker eksplisit). Dokumentasi asli ada di RapidAPI (halaman JS-rendered,
   gagal di-fetch) — klaim ini LEMAH, belum terkonfirmasi.

**Tier 3 — resmi tapi tidak praktis untuk proyek personal:**
8. **IDX resmi ("Layanan Data BEI")** — broker summary EOD masih ada di web IDX, TAPI **kode
   broker real-time sudah DIHAPUS BEI sejak 6 Desember 2021** (keputusan regulasi anti
   herding/front-running, dikonfirmasi 3 sumber berita). Akses terstruktur/API perlu kontrak
   B2B enterprise (halaman 403 dari IP ini, kemungkinan Cloudflare, tidak ada harga publik).
   Realistis cuma untuk vendor data resmi, bukan proyek personal.

**Kalau mau lanjut:** mulai dari NeaByteLab/IDX-API (gratis, coba jalankan `deno task db:sync`
sungguhan dulu, verifikasi endpoint IDX resmi yang dipanggilnya beneran ada & tidak 429/403) atau
Sectors.app (paling lengkap tapi berbayar — tanya harga langsung ke `help@sectors.app` krn halaman
pricing keblok bot dari sini).
