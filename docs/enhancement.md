# Enhancement — Indikator & Analisis Teknikal (2026-07-01)

> Status: **ide/riset, belum diimplementasi**. Ditulis dari diskusi soal "indikator analisis apa
> yang belum ada di app kita" — bukan rencana final, sekadar kumpulan opsi buat didiskusikan &
> diprioritaskan nanti.

## Konteks

`backend/indicators.py` saat ini sudah punya cakupan lumayan lengkap:

- **Trend**: SMA(20/50/200), EMA(20/50), MACD, ADX/DMI, Parabolic SAR
- **Momentum**: RSI, Stochastic, Williams %R, CCI
- **Volatility**: Bollinger Bands, ATR, Keltner Channel
- **Volume**: VWAP (session-reset intraday), OBV, A/D Line, Volume Profile (POC)

Tapi ada beberapa kategori yang masih kosong, dan (temuan penting) ada indikator yang **sudah
dihitung tapi tidak dipakai** di skor komposit. Semua ide di bawah dikelompokkan berdasarkan itu.

---

## A. Indikator yang sama sekali belum ada

| Indikator | Kenapa berguna | Kompleksitas |
|---|---|---|
| **Candlestick pattern recognition** (Bullish Engulfing, Hammer, Morning Star, dll — skill Hermes punya 24 pola) | Sinyal reversal jangka pendek yang tidak tertangkap indikator berbasis rata-rata. Sudah relevan krn AI Advisor kita menyebut kerangka ini di prompt, tapi datanya sendiri belum kita hitung | Sedang — pure pattern-matching di OHLC, ada contoh kode di skill Hermes yang bisa diadaptasi |
| **Support & Resistance otomatis** (swing high/low, level psikologis) | Panel "Key Levels" di `TechnicalSummary` sekarang cuma SMA/BB — bukan level S/R asli. Krusial utk entry/exit lebih presisi | Sedang |
| **SuperTrend** | Indikator trend modern berbasis ATR (mirip logika Keltner kita), populer utk sinyal beli/jual jelas (garis tunggal, bukan band) | Rendah — reuse `atr()` yang sudah ada |
| **Fibonacci Retracement/Extension** | Proyeksi target/support dari swing terakhir — pelengkap alami dari S/R | Rendah-sedang (butuh Zig Zag dulu utk deteksi swing) |
| **Money Flow Index (MFI)** | "RSI yang mempertimbangkan volume" — jembatan antara RSI (harga) dan OBV (volume) yang sekarang terpisah | Rendah |
| **Pivot Points** (Classic/Camarilla) | Level S/R harian yang dipakai luas utk day-trading, beda pendekatan dari SMA/BB | Rendah |
| **Ichimoku Cloud** | Sistem trend+momentum+S/R sekaligus, populer tapi lebih berat diimplementasi & dijelaskan di chart | Tinggi |
| **Relative Strength vs IHSG** | Saham dibanding indeks (^JKSE sudah kita ingest!) — bagus utk cari "leader vs laggard" | Rendah — data indeks sudah ada |
| **Chaikin Money Flow / Chaikin Oscillator** | "MACD-nya A/D Line" — kita sudah punya A/D Line mentah tapi belum osilator turunannya | Rendah |
| **Aroon Indicator/Oscillator** | Alternatif ADX utk arah & kekuatan tren | Rendah |
| **Elder Ray Index** (Bull Power/Bear Power) | Momentum berbasis EMA, pelengkap RSI/MACD | Rendah |
| **Awesome Oscillator** | Momentum ala Bill Williams, populer di kalangan trader teknikal | Rendah |
| **Vortex Indicator** | Alternatif lain utk identifikasi tren (vs ADX) | Rendah |
| **Donchian Channel** | Indikator breakout sederhana (channel dari highest-high/lowest-low), lebih simpel dari Keltner/BB | Rendah |
| **Zig Zag** | Bukan sinyal trading, tapi FONDASI utk deteksi swing high/low yang dipakai S/R & Fibonacci di atas | Sedang |

---

## B. Sudah dihitung, tapi TIDAK dipakai di skor komposit

Temuan penting: `latest_signals()` — fungsi yang dipakai Screener/AI Picks/AI Advisor utk hitung
skor −100..+100 — **cuma pakai RSI, MACD histogram, posisi SMA20/50/200, dan ADX/DMI**.

Padahal `compute_all()` (dipakai buat chart Analyst) sudah menghitung: **Stochastic, Williams %R,
CCI, Bollinger Bands, ATR, Keltner, VWAP, OBV, A/D Line, Volume Profile** — semua ini tampil di
chart tapi **tidak menyumbang skor sama sekali**. Ada "indikator nganggur" yang sebenarnya sudah
ada, tinggal dimasukkan ke formula skor.

---

## C. Analisis level lebih tinggi (bukan indikator tunggal per-saham)

### 1. Market breadth / kesehatan pasar keseluruhan — **paling siap dibangun sekarang**

Tidak perlu indikator baru sama sekali — cuma agregasi dari data yang **sudah** dihitung tiap 5
menit (`screener.compute_universe`, scan seluruh universe). Contoh:
- % saham di atas SMA200
- Rasio saham naik vs turun hari ini (advance/decline)
- Distribusi verdict (berapa STRONG BUY vs STRONG SELL) di seluruh universe

Ini yang platform profesional biasa sebut "market internals" — dan kita sudah punya bahan
mentahnya gratis karena sudah scan ~949 emiten. **Zero dependency data baru.**

### 2. Divergence detection otomatis (RSI/MACD vs harga)

Kita hitung RSI & MACD, tapi tidak ada logika eksplisit yang mendeteksi "harga bikin higher-high
tapi RSI bikin lower-high" (sinyal reversal klasik). Skill Hermes yang sudah kita baca punya ini
persis (`rsi_divergence`, `obv_divergence`) — bisa diadaptasi.

### 3. Konfirmasi multi-timeframe (skor harian dikonfirmasi tren mingguan)

Arsitekturnya **sudah siap** — `CHART_INTERVALS` di `.env` sudah termasuk `1wk`. TAPI sudah
dicek langsung ke ClickHouse (2026-07-01): **data mingguan belum ada satupun yang tersimpan**,
cuma interval `1d` yang ada di dev environment sekarang. Ini bukan gap analisis, tapi **gap data
hulu** — perlu dibenerin di ingestion dulu sebelum bisa dipakai.

### 4. Rotasi sektor

Kolom `sector` sudah ada di skema ClickHouse (`market.ohlcv`), tapi sudah dicek langsung
(2026-07-01): **nilainya NULL untuk semua simbol** yang ada datanya sekarang. Sama kasusnya
kayak poin 3 — perlu sektor benar-benar terisi dulu (mis. sambungkan dari `all.csv` yang sudah
dipakai `board_map()`) sebelum analisis rotasi sektor bisa jalan.

---

## D. Di luar technical analysis (butuh sumber data baru, bukan cuma kode)

Sudah dibahas terpisah, dicatat lagi di sini biar satu tempat:

- **Fundamental** (P/E, ROE, EPS, dividend yield) — ClickHouse cuma simpan OHLCV, belum ada
  sumber data fundamental (lihat gotcha CLAUDE.md soal ini).
- **Sentimen berita** — belum diriset sama sekali, kandidat sumber data belum diidentifikasi.

### Broker summary / smart money flow — hasil riset 8 kandidat (2026-07-01)

Konteks: skill Hermes `stock-technical-fundamental-analysis` punya framework analisis Broker
Summary (akumulasi/distribusi smart money, Dow Theory phases) tapi **eksplisit bilang datanya
tidak tersedia via yfinance**, harus dari sumber eksternal. Di bawah hasil riset — **cuma riset
dokumentasi/kode publik, belum ada yang benar-benar dites integrasinya** (kecuali NeaByteLab,
lihat status live di bawah). Jangan percaya begitu saja tanpa uji coba nyata — `saham-mcp`
sebelumnya juga awalnya terlihat meyakinkan tapi datanya ternyata beku & real-time-nya 429.

**Tier 1 — endpoint broker summary terkonfirmasi ada (bukti dari dokumentasi/kode, bukan cuma marketing):**

1. **[Sectors.app](https://sectors.app/)** — PALING lengkap: 7 endpoint khusus broker
   (`GET /v2/broker-summary/{symbol}/`, `broker-activity-top`, `broker-registry`,
   `foreign-flow-by-symbol`, dll — lihat [dokumentasi source](https://github.com/supertypeai/sectors_api_docs/tree/main/api-references/v2/indonesia/brokers)).
   Auth via header `Authorization: [API_KEY]`. **Berbayar** — cuma utk subscriber "Insider Plan";
   harga persis tidak bisa diverifikasi (halaman pricing 403 dari IP server ini, kemungkinan
   Cloudflare — sama seperti masalah kita akses idx.co.id).
2. **[GOAPI.IO](https://goapi.io/)** — endpoint `getBrokerSummary(symbol, date)` terkonfirmasi
   nyata di [PHP SDK](https://github.com/goapi-io/php-sdk) & Elixir SDK, didokumentasikan di
   Swagger (`goapi.io/swagger/`). Produk "Stock Market IDX" ada free trial tanpa kuota jelas;
   harga berbayar tidak jelas (satu-satunya angka yang ketemu promo basi 2023, ~Rp 600-900rb/bulan
   — JANGAN dianggap harga sekarang).
3. **[NeaByteLab/IDX-API](https://github.com/NeaByteLab/IDX-API)** (GitHub, open source, MIT) —
   fungsi `syncBrokerSummary()` kategori "Trading Modules", **klaim pakai API RESMI IDX langsung**
   (bukan scraping), sync ke SQLite lokal via Deno v2.5+. **Gratis & self-hosted** — paling
   menjanjikan kalau klaim "API resmi IDX"-nya benar. **→ sedang dicoba jalankan langsung, lihat
   catatan status di bawah.**
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

### Status uji coba langsung — NeaByteLab/IDX-API (2026-07-04)

**Kesimpulan: BLOCKED di tahap setup, belum sempat sampai tes endpoint IDX-nya sama sekali.**

Langkah yang sudah dilakukan:
1. Install Deno 2.9.1 (berhasil).
2. Clone repo (berhasil).
3. Baca source code `src/Trading/index.ts::getBrokerSummary()` — **terkonfirmasi** memanggil
   endpoint internal resmi IDX: `https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary`
   (bukan scraping HTML, benar seperti klaim). Ada handshake session dulu (visit `idx.co.id/id`
   ambil cookie, browser headers lengkap) sebelum request data — pendekatan yang masuk akal
   utk menghindari blokir sederhana.
4. Coba jalankan test script (`deno run` import `TradingModule` langsung) → **macet total di
   tahap download dependency**, bukan di endpoint IDX-nya.

**Akar masalah:** `jsr.io` (registry paket Deno resmi) **403 total** dari IP server ini
(`curl -sI https://jsr.io/` → 403, bahkan di halaman utama, bukan cuma path package) — pola
identik dgn Yahoo/IDX/Cloudflare yang sudah berkali-kali ditemui di proyek ini. Dependency
`@db/sqlite` (dipakai buat database lokal) **cuma tersedia di JSR**, tidak ada mirror npm/GitHub
yang berhasil ditemukan (`@jsr/db__sqlite` di npm registry & npmmirror.com sama-sama 404, repo
`denoland/deno_sqlite` di GitHub juga 404 — kemungkinan nama package tsb sudah dipindah/beda).
Dependency npm lain (`drizzle-kit`, `@libsql/client`) berhasil di-download normal lewat mirror
Tencent — jadi masalahnya spesifik ke JSR, bukan jaringan secara umum.

**Implikasi:** belum bisa disimpulkan apakah endpoint `GetBrokerSummary` IDX sendiri akan kena
403/429 atau tidak dari IP ini — proses gagal SEBELUM sampai ke situ. Untuk lanjut, opsi:
(a) coba jalankan dari jaringan lain (residential/rumah) yang tidak diblokir JSR, generate
`deno.lock` + cache dependency di sana, lalu pindahkan ke server ini; (b) cari cara vendor
`@db/sqlite` secara manual tanpa lewat JSR (belum diriset); (c) skip proyek ini, coba kandidat
lain yang tidak bergantung ke JSR.

---

## Rekomendasi prioritas (kalau harus pilih urutan)

1. **Market breadth** (C.1) — termudah, langsung bisa jalan hari ini, nol dependency data baru.
2. **Manfaatkan indikator yang sudah dihitung** (B) — masukkan Stochastic/CCI/OBV ke
   `latest_signals()`, quick win tanpa indikator baru.
3. **SuperTrend** (A) — reuse `atr()` yang sudah ada, effort rendah, value tinggi.
4. **Candlestick pattern** (A) — karena sudah "dijanjikan" implisit lewat AI Advisor, ada kode
   referensi siap adaptasi dari skill Hermes.
5. **Benerin data sektor + mulai isi data mingguan** (gap data di C.3/C.4) — begitu ada, rotasi
   sektor & konfirmasi multi-timeframe langsung jadi mungkin, plus manfaat lain (chart mingguan
   lebih reliable).

Prioritas di atas urutan saya pribadi berdasarkan effort vs value — belum tentu urutan yang
paling penting buat kebutuhan trading kamu. Diskusikan & sesuaikan sebelum mulai implementasi.
