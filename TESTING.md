# 🧪 Testing Guide

Cara menguji IDX Trader: backend API, pipeline data, dan frontend (browser).
Ganti `localhost` dengan IP server bila menguji deployment (mis. `43.134.129.64`).

---

## 1. Smoke test Backend API (curl)

```bash
# health
curl -s http://localhost:8000/health
# → {"status":"ok","ws_clients":N}

# daftar emiten yg punya data
curl -s "http://localhost:8000/api/symbols" | head -c 200

# quote semua emiten (harus banyak; 0 = ClickHouse kosong → lihat TROUBLESHOOTING.md)
curl -s "http://localhost:8000/api/quotes?interval=1d" | grep -o '"symbol"' | wc -l

# history + indikator + signals 1 emiten
curl -s "http://localhost:8000/api/history/BBCA?interval=1d" | head -c 300

# screener (daily picks)
curl -s "http://localhost:8000/api/screener?min_score=50&above_ma200=true&limit=5"

# journal
curl -s "http://localhost:8000/api/journal/positions"  | head -c 200
curl -s "http://localhost:8000/api/journal/analytics"  | head -c 200

# watchlist
curl -s "http://localhost:8000/api/watchlist"
```

Dokumentasi interaktif (klik & coba): **http://localhost:8000/docs**

---

## 2. Verifikasi Pipeline (Yahoo → TCP → Kafka → ClickHouse)

```bash
# semua service healthy?
docker compose ps

# data di ClickHouse (jumlah baris + jumlah emiten + interval)
docker compose exec clickhouse clickhouse-client --password tradingch123 \
  --query "SELECT count() rows, uniqExact(symbol) symbols, groupUniqArray(interval) ivs FROM market.ohlcv FORMAT Vertical"

# cek 1 emiten per interval
docker compose exec clickhouse clickhouse-client --password tradingch123 \
  --query "SELECT interval, count() FROM market.ohlcv WHERE symbol='BBCA' GROUP BY interval ORDER BY interval"

# log tiap tahap pipeline
docker compose logs --tail=30 ingestion          # poller fetch yFinance → TCP
docker compose logs --tail=20 tcp-bridge         # TCP → Kafka
docker compose logs --tail=20 clickhouse-writer  # Kafka → ClickHouse

# lag consumer Kafka (0 = writer sudah catch-up)
docker compose exec kafka kafka-consumer-groups --bootstrap-server localhost:29092 \
  --group clickhouse-writer --describe
```

**Lulus bila:** semua service `Up`/`healthy`, ClickHouse `rows > 0` & `symbols` mendekati ~949, log writer ada `inserted ...`.

---

## 3. Test Frontend (browser) — Playwright via Docker

Tidak perlu install Node di host. Pakai image resmi Playwright (browser sudah include).

> **Penting:** gunakan `--network host` agar `localhost` di dalam container = host (persis alur browser user).
> Untuk menguji **server remote**, ganti `FRONT` ke `http://<ip-server>:3001` (tanpa `--network host`).

### Skrip `pw-test.mjs`
```js
import { chromium } from 'playwright';
const FRONT = 'http://localhost:3001';
const out = {}, consoleErrors = [], pageErrors = [];
const browser = await chromium.launch();
const page = await browser.newContext({ viewport: { width: 1600, height: 900 } }).then(c => c.newPage());
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', (e) => pageErrors.push(String(e)));

await page.goto(`${FRONT}/analyst`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(6000);                         // beri waktu fetch + hydrate

out.tickerCount = await page.locator('div.w-52 button').count();
out.tapeItems   = await page.locator('.marquee span.font-semibold').count();
// uji search (interaktivitas/hydration): ketik kode lalu cek filter
await page.locator('input[placeholder="Cari saham…"]').fill('BBCA');
await page.waitForTimeout(1200);
out.afterSearch = await page.locator('div.w-52 button').count();
out.consoleErrors = consoleErrors.slice(0, 10);
out.pageErrors    = pageErrors.slice(0, 10);

await page.screenshot({ path: 'pw-test.png', fullPage: false });
console.log(JSON.stringify(out, null, 2));
await browser.close();
```

### Jalankan
```bash
# simpan pw-test.mjs di sebuah folder, lalu (dari folder itu):
docker run --rm --network host -v "$PWD:/work" -w /work \
  mcr.microsoft.com/playwright:v1.49.0-jammy \
  bash -c "npm i playwright@1.49.0 --no-audit --no-fund >/dev/null 2>&1 && node pw-test.mjs"
```
> Windows PowerShell: ganti `$PWD` → `${PWD}`. Image sudah punya browser; `npm i playwright@1.49.0` hanya menautkan paket.

**Lulus bila:** `tickerCount` > 0 (≈ jumlah emiten), `tapeItems` > 0, `afterSearch` mengecil (search jalan),
`consoleErrors`/`pageErrors` kosong. Lihat `pw-test.png` untuk bukti visual.

### Menguji server remote (tanpa network host)
Ganti `const FRONT = 'http://<ip-server>:3001'` dan **hapus** `--network host`. Catatan: FE memanggil
backend di `<ip-server>:8000`, jadi port 8000 harus terbuka (lihat TROUBLESHOOTING.md). Untuk mem-proxy
API saat menguji dari mesin lain, lihat trik `page.route` di repo (opsional).

---

## 4. Checklist uji manual (UI)

**Tab 2 — Analyst** (`/analyst`)
- [ ] Daftar emiten terisi; search memfilter
- [ ] Pilih emiten → candlestick muncul; ganti timeframe (5m/15m/1h/1d/1wk)
- [ ] Toggle indikator (SMA/BB/VWAP/RSI/MACD…) → overlay & panel muncul
- [ ] Ringkasan teknikal (verdict + score) tampil
- [ ] Ticker tape berjalan di footer; status **LIVE**

**Tab 1 — Journal** (`/journal`)
- [ ] Tambah posisi → muncul di tabel + P&L terhitung
- [ ] Tambah transaksi BUY lalu SELL → tab Analisis: win rate, equity curve, dll terisi
- [ ] Edit/hapus posisi & transaksi

**Tab 3 — Watchlist** (`/watchlist`)
- [ ] Preset (Strong Buy, Oversold, dst) → tabel hasil berubah
- [ ] Filter (min skor / RSI / Vol× / >MA200) → Terapkan
- [ ] ★ tambah ke watchlist; klik kode → ke Analyst (chart emiten itu)

---

## 5. (Opsional) Isi data dummy Journal

Skrip Python (pakai urllib, tanpa dependency) untuk mengisi portofolio + transaksi random realistis
ada pola-nya di histori pengembangan; intinya `POST /api/journal/positions` & `/api/journal/transactions`
dengan harga diambil dari `/api/quotes`. Hapus lewat tombol di UI bila ingin reset.

---

## Ringkas perintah cepat

```bash
docker compose ps                                   # service
curl -s localhost:8000/health                       # backend
curl -s "localhost:8000/api/quotes?interval=1d" | grep -o '"symbol"' | wc -l   # data?
docker compose logs --tail=30 ingestion             # poller/yFinance
```
