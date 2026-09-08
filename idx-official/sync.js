// Sync EOD OHLCV resmi IDX (idx.co.id/primary/TradingSummary/GetStockSummary) ke
// ClickHouse tabel `market.ohlcv_idx_official`. Sumber independen dari yFinance
// (lihat CLAUDE.md gotcha "AI Advisor/OHLCV — Cloudflare 403 idx.co.id").
//
// idx.co.id di depan Cloudflare Bot Management: request HTTP polos (curl/fetch)
// ke halaman/endpoint APAPUN kena 403, TERMASUK reuse cookie hasil browser (cek
// TLS/JS fingerprint tiap request, bukan cuma cookie). Satu-satunya cara yang
// terbukti lolos: jalankan fetch() dari DALAM browser Chromium sungguhan
// (Playwright) — halaman utama tetap 403, tapi cookie __cf_bm yang di-set tetap
// cukup buat endpoint JSON lolos 200 selama masih di sesi browser yang sama.
// Endpoint ini juga mengabaikan parameter `length` — selalu balikin semua ~963
// saham sekali fetch, jadi tidak perlu chunking seperti pipeline yFinance.

const { chromium } = require('playwright');

const CH_HOST = process.env.CLICKHOUSE_HOST || 'clickhouse';
const CH_PORT = process.env.CLICKHOUSE_HTTP_PORT || '8123';
const CH_USER = process.env.CLICKHOUSE_USER || 'default';
const CH_PASSWORD = process.env.CLICKHOUSE_PASSWORD || '';
const CH_DB = process.env.CLICKHOUSE_DB || 'market';

const RUN_HOUR_WIB = 16; // jalan 16:30 WIB, setelah closing 15:50 + buffer finalisasi data
const RUN_MINUTE_WIB = 30;
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 5 * 60 * 1000;

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36';

function log(...args) {
  console.log(`[${new Date().toISOString()}]`, ...args);
}

function jakartaNow() {
  // WIB = UTC+7, tanpa DST — cukup offset manual, tidak bergantung tzdata container.
  return new Date(Date.now() + 7 * 3600 * 1000);
}

function todayStr(d) {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return { compact: `${y}${m}${day}`, iso: `${y}-${m}-${day}` };
}

async function fetchStockSummary(dateCompact) {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled'],
  });
  try {
    const context = await browser.newContext({ userAgent: UA, locale: 'id-ID' });
    const page = await context.newPage();

    // Warmup: halaman ini SELALU 403 (Cloudflare "Attention Required"), tapi efek
    // sampingnya (cookie __cf_bm) yang kita butuh — jangan anggap 403 di sini sbg gagal.
    await page.goto('https://www.idx.co.id/id', { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(3000);

    const url = `https://www.idx.co.id/primary/TradingSummary/GetStockSummary?length=9999&start=0&date=${dateCompact}`;
    const result = await page.evaluate(async (u) => {
      const r = await fetch(u, { credentials: 'include' });
      const text = await r.text();
      return { status: r.status, text };
    }, url);

    if (result.status !== 200) {
      throw new Error(`GetStockSummary balas HTTP ${result.status}`);
    }
    const parsed = JSON.parse(result.text);
    return parsed.data || [];
  } finally {
    await browser.close();
  }
}

function toRows(data, dateIso) {
  return data
    .filter((r) => r.StockCode)
    .map((r) => ({
      symbol: r.StockCode,
      date: dateIso,
      prev_close: r.Previous ?? 0,
      open: r.OpenPrice ?? 0,
      high: r.High ?? 0,
      low: r.Low ?? 0,
      close: r.Close ?? 0,
      volume: r.Volume ?? 0,
      value: r.Value ?? 0,
      frequency: r.Frequency ?? 0,
      foreign_buy: r.ForeignBuy ?? 0,
      foreign_sell: r.ForeignSell ?? 0,
    }));
}

async function chInsert(query, body) {
  const url = `http://${CH_HOST}:${CH_PORT}/?query=${encodeURIComponent(query)}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'X-ClickHouse-User': CH_USER,
      'X-ClickHouse-Key': CH_PASSWORD,
      'Content-Type': 'text/plain',
    },
    body,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`ClickHouse insert gagal HTTP ${res.status}: ${errText.slice(0, 500)}`);
  }
}

async function insertRows(rows) {
  if (rows.length === 0) return;
  const body = rows.map((r) => JSON.stringify(r)).join('\n');
  await chInsert(`INSERT INTO ${CH_DB}.ohlcv_idx_official FORMAT JSONEachRow`, body);
}

// Fallback: tulis data IDX ke market.ohlcv (tabel utama yFinance) dengan format
// kompatibel — ts = midnight UTC tanggal bursa (sesuai konvensi yFinance 1d IDX).
// ReplacingMergeTree(ingested_at) otomatis dedup: kalau yFinance sudah isi hari itu
// dengan ingested_at lebih baru, data IDX ini akan tersingkir saat optimize/merge;
// kalau yFinance gagal (429), data IDX menjadi satu-satunya baris untuk hari itu.
async function insertToOhlcv(rows) {
  if (rows.length === 0) return;
  const ohlcvRows = rows
    .filter((r) => r.close > 0)
    .map((r) => ({
      symbol: r.symbol,
      type: 'stock',
      sector: '',
      interval: '1d',
      ts: `${r.date} 00:00:00`,
      open: r.open,
      high: r.high,
      low: r.low,
      close: r.close,
      volume: r.volume,
    }));
  if (ohlcvRows.length === 0) return;
  const body = ohlcvRows.map((r) => JSON.stringify(r)).join('\n');
  await chInsert(`INSERT INTO ${CH_DB}.ohlcv FORMAT JSONEachRow`, body);
}

function dateOverrideFromArgv() {
  const arg = process.argv.find((a) => a.startsWith('--date='));
  if (!arg) return null;
  const compact = arg.slice('--date='.length); // YYYYMMDD
  const iso = `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}`;
  return { compact, iso };
}

async function runOnce() {
  const { compact, iso } = dateOverrideFromArgv() || todayStr(jakartaNow());
  log(`Fetch GetStockSummary tanggal ${iso} (${compact})...`);
  const data = await fetchStockSummary(compact);
  log(`Dapat ${data.length} baris dari idx.co.id.`);
  if (data.length === 0) return;
  const rows = toRows(data, iso);
  await insertRows(rows);
  log(`Insert ${rows.length} baris ke ${CH_DB}.ohlcv_idx_official selesai.`);
  await insertToOhlcv(rows);
  log(`Insert ${rows.filter((r) => r.close > 0).length} baris ke ${CH_DB}.ohlcv (1d fallback) selesai.`);
}

async function runWithRetry() {
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      await runOnce();
      return;
    } catch (err) {
      log(`Attempt ${attempt}/${MAX_RETRIES} gagal:`, err.message);
      if (attempt < MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
      } else {
        log('Semua retry gagal, skip sampai jadwal berikutnya.');
      }
    }
  }
}

function msUntilNextRun() {
  const now = jakartaNow();
  const target = new Date(now);
  target.setUTCHours(RUN_HOUR_WIB, RUN_MINUTE_WIB, 0, 0);
  if (target <= now) {
    target.setUTCDate(target.getUTCDate() + 1);
  }
  // skip Sabtu(6)/Minggu(0) — market IDX tutup
  while ([0, 6].includes(target.getUTCDay())) {
    target.setUTCDate(target.getUTCDate() + 1);
  }
  return target.getTime() - now.getTime();
}

async function main() {
  if (process.argv.includes('--once')) {
    await runWithRetry();
    return;
  }
  log('idx-official sync service jalan. Jadwal: tiap hari bursa 16:30 WIB.');
  for (;;) {
    const delay = msUntilNextRun();
    log(`Tunggu ${Math.round(delay / 60000)} menit sampai run berikutnya.`);
    await new Promise((r) => setTimeout(r, delay));
    await runWithRetry();
  }
}

main().catch((err) => {
  log('FATAL', err);
  process.exit(1);
});
