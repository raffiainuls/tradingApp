# Plan — Pisah Watchlist/Screener + AI Picks (Tab 3)

> Status: **rencana, belum diimplementasi**. Tulisan ini dibuat sebelum coding dimulai, sesuai permintaan.

## Context

Saat ini `/watchlist` adalah satu halaman gabungan: kolom kiri watchlist manual, kolom kanan
screener rule-based (preset + filter + tabel ranking 949 emiten). Endpoint backend-nya pun
sama-sama tinggal di `backend/routers/watchlist.py`.

Ini mau dipisah balik sesuai PRD asli (`prd-tradingApp.md`): **Tab 3 = Watchlist** (manual + AI
Picks), **Tab 4 = Screener** (rule-based, sudah ada slot-nya di Sidebar tapi masih `ComingSoon`).
Sekaligus menambahkan fitur baru **AI Picks**: setiap hari (atau saat halaman dibuka/TTL lewat),
sistem ambil **top-15 saham bullish** dari mesin skoring yang sudah ada (`backend/screener.py`),
lalu minta **LLM** kasih reasoning singkat per saham. Level entry/target/cutloss dihitung
deterministik dari ATR (bukan dari LLM, supaya angka tidak "ngarang").

**Keputusan penting soal LLM** (revisi dari diskusi sebelumnya): AI Picks (Tab 3, proses banyak
saham sekaligus/batch) pakai **HTTP OpenAI-compatible** via `LLM_BASE_URL`/`LLM_MODEL` —
provider-agnostic, bisa diarahkan ke Ollama/vLLM/LocalAI self-hosted, BUKAN Hermes CLI. Alasan:
batch 15 saham × subprocess CLI per saham bakal lambat; HTTP jauh lebih cepat & portable.
**Hermes CLI subprocess** (`docs/hermes-integration.md`) tetap dipakai khusus nanti untuk
**Tab 5 (AI Advisor)** — tanya satu saham sekaligus, beda use-case. Kedua dokumen tidak lagi
saling tumpang tindih setelah ini.

Kalau `LLM_BASE_URL` tidak diisi (default), AI Picks tetap jalan — tampil 15 kartu rule-based
tanpa reasoning ("Reasoning AI tidak tersedia"), tidak error.

---

## Keputusan yang sudah dikonfirmasi user

1. Pisah halaman: Watchlist manual tetap di `/watchlist`; Screener pindah ke `/screener`
   (ganti `ComingSoon`). Tombol ★ "tambah ke watchlist" di tabel screener **tetap ada**.
2. AI Picks hidup di dalam halaman Watchlist (`/watchlist`), bukan halaman terpisah.
3. AI Picks: **top 15 bullish saja** (verdict `BUY`/`STRONG BUY`, skor tertinggi), exclude
   papan "Pemantauan Khusus".
4. Trigger generate: **otomatis saat halaman dibuka, berbasis TTL** (default 6 jam) — request
   `GET /api/ai-picks` tidak boleh blocking; pakai FastAPI `BackgroundTasks` + polling status
   dari frontend. Plus tombol manual "Refresh".
5. LLM integration: **HTTP `LLM_BASE_URL`** (lihat di atas) — bukan Hermes CLI.
6. Entry/target/cutloss dihitung dari `close` + `ATR` (2×ATR untuk target, 1.5×ATR untuk
   cutloss) — deterministik, bukan dari LLM.

---

## Backend

### 1. `backend/routers/watchlist.py` — trim ke CRUD manual saja
Hapus endpoint `screen()` dan `presets()` (pindah ke file baru). `import screener` tetap
dipakai (untuk enrich skor di `GET /api/watchlist`). Hapus helper `_vi()` dari file ini (pindah
ke `routers/screener.py`).

### 2. `backend/routers/screener.py` (BARU)
Pindahkan endpoint `GET /api/screener` dan `GET /api/screener/presets` persis seperti
sekarang (tanpa ubah logika), tetap memanggil `backend/screener.py`'s `screen()` /
`compute_universe()`. URL path **tidak berubah** — jadi frontend yang sudah ada (Screener
table) tidak perlu ubah cara panggil API.

### 3. `backend/llm_client.py` (BARU) — klien LLM generik, provider-agnostic
```python
"""Klien LLM generik (OpenAI-compatible chat completions).
Arahkan ke Ollama/vLLM/LocalAI/LM Studio self-hosted via LLM_BASE_URL.
Kosongkan LLM_BASE_URL untuk menonaktifkan (AI Picks tetap jalan, rule-based only)."""
import httpx
import config

def call_llm(prompt: str, system: str | None = None) -> str | None:
    if not config.LLM_BASE_URL:
        return None          # tidak dikonfigurasi -> no-op instan, tanpa network call
    try:
        headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"} if config.LLM_API_KEY else {}
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        resp = httpx.post(
            f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
            json={"model": config.LLM_MODEL, "messages": messages,
                  "temperature": 0.4, "max_tokens": 250},
            headers=headers, timeout=config.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content.strip() or None
    except Exception as e:
        print(f"[!] LLM call failed: {e}", flush=True)
        return None          # NEVER raise — 1 saham gagal tidak boleh gagalkan batch
```

### 4. `backend/ai_picks.py` (BARU) — orkestrasi AI Picks
Mirip gaya `backend/screener.py`. State generasi disimpan sebagai **module-level global**
(pola yang sudah ada di `backend/realtime.py` — `connected_ws`/`latest_quote`), aman karena
backend jalan 1 worker uvicorn (lihat Dockerfile CMD, tanpa `--workers`).

```python
import threading, time
from datetime import datetime, timezone
import config, db, screener
from llm_client import call_llm

_lock = threading.Lock()
_generating = False
_last_generated_at: float | None = None

def is_generating() -> bool: return _generating
def last_generated_at() -> float | None: return _last_generated_at

def _pick_candidates(top_n: int) -> list[dict]:
    """Top-N bullish (BUY/STRONG BUY) by score desc, exclude papan Pemantauan Khusus."""
    rows = screener.compute_universe("1d")
    board_map = db.board_map()
    bullish = sorted(
        [r for r in rows if r["verdict"] in ("BUY", "STRONG BUY")],
        key=lambda r: r["score"], reverse=True,
    )
    out = []
    for r in bullish:
        board = (board_map.get(r["symbol"], {}).get("board") or "")
        if "Khusus" in board:
            continue
        out.append({**r, "board": board})
        if len(out) >= top_n:
            break
    return out

def _build_prompt(c: dict) -> str:
    return (
        f"Analisa saham {c['symbol']} (papan: {c.get('board') or '-'}). "
        f"Data teknikal: skor komposit {c['score']} (verdict {c['verdict']}), "
        f"RSI {c.get('rsi')}, MACD histogram {c.get('macd_hist')}, ADX {c.get('adx')}, "
        f"harga close {c['close']}. Beri reasoning singkat 2-3 kalimat dalam Bahasa "
        "Indonesia mengapa saham ini layak masuk watchlist hari ini, tanpa menyebut "
        "harga target/entry/cutloss spesifik (sudah dihitung sistem secara terpisah)."
    )

def _levels(close: float, atr: float | None) -> tuple[float, float, float]:
    a = atr if atr else close * 0.02     # fallback ~2% kalau ATR tidak ada
    return round(close, 2), round(close + 2 * a, 2), round(close - 1.5 * a, 2)

def generate(top_n: int | None = None):
    """Jalan via BackgroundTasks. Lock cegah generate paralel (TTL-check vs tombol manual)."""
    global _generating, _last_generated_at
    if not _lock.acquire(blocking=False):
        return
    _generating = True
    try:
        n = top_n or config.AI_PICKS_TOP_N
        candidates = _pick_candidates(n)
        batch_at = datetime.now(timezone.utc)
        rows = []
        for c in candidates:
            reasoning = call_llm(_build_prompt(c))
            entry, target, cutloss = _levels(c["close"], c.get("atr"))
            rows.append((c["symbol"], c.get("sector"), c["verdict"], c["score"],
                         c.get("rsi"), c.get("macd_hist"), c.get("adx"), c.get("atr"),
                         c["close"], entry, target, cutloss, reasoning, batch_at))
        with db.pg_cursor(commit=True) as cur:
            for r in rows:
                cur.execute("""INSERT INTO ai_picks
                    (symbol, sector, verdict, score, rsi, macd_hist, adx, atr,
                     close_price, entry_price, target_price, cutloss_price, reasoning, batch_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", r)
        _last_generated_at = time.time()
        print(f"[+] AI Picks batch generated: {len(rows)} symbols", flush=True)
    except Exception as e:
        print(f"[!] AI Picks generation failed: {e}", flush=True)
    finally:
        _generating = False
        _lock.release()

def latest_batch() -> list[dict]:
    with db.pg_cursor() as cur:
        cur.execute("""SELECT * FROM ai_picks
                        WHERE batch_at = (SELECT max(batch_at) FROM ai_picks)
                        ORDER BY score DESC""")
        return cur.fetchall()

def is_stale(ttl_hours: float) -> bool:
    with db.pg_cursor() as cur:
        cur.execute("SELECT max(batch_at) AS m FROM ai_picks")
        row = cur.fetchone()
    if not row or not row["m"]:
        return True
    age_h = (datetime.now(timezone.utc) - row["m"]).total_seconds() / 3600
    return age_h >= ttl_hours
```

`is_stale()` query langsung ke Postgres (bukan baca state in-memory) — supaya tetap benar
setelah backend restart (in-memory `_last_generated_at` reset ke `None`, tapi DB tetap source
of truth).

### 5. `backend/routers/ai_picks.py` (BARU)
```python
from fastapi import APIRouter, BackgroundTasks
import ai_picks, config

router = APIRouter(prefix="/api")

def _maybe_trigger(bg: BackgroundTasks):
    if ai_picks.is_stale(config.AI_PICKS_TTL_HOURS) and not ai_picks.is_generating():
        bg.add_task(ai_picks.generate)

@router.get("/ai-picks")
def get_ai_picks(bg: BackgroundTasks):
    _maybe_trigger(bg)
    return {"picks": ai_picks.latest_batch()}

@router.get("/ai-picks/status")
def get_ai_picks_status():
    return {"generating": ai_picks.is_generating(), "last_generated_at": ai_picks.last_generated_at()}

@router.post("/ai-picks/generate")
def trigger_ai_picks(bg: BackgroundTasks):
    if ai_picks.is_generating():
        return {"started": False, "reason": "already_generating"}
    bg.add_task(ai_picks.generate)
    return {"started": True}
```
`BackgroundTasks.add_task` dijalankan Starlette **setelah** response dikirim — jadi
`GET /api/ai-picks` selalu cepat walau itu memicu generate batch di belakang.

### 6. `db/init.sql` — tambah tabel `ai_picks`
```sql
CREATE TABLE IF NOT EXISTS ai_picks (
    id            SERIAL PRIMARY KEY,
    symbol        VARCHAR(20)   NOT NULL,
    sector        VARCHAR(50),
    verdict       VARCHAR(20)   NOT NULL,
    score         INTEGER       NOT NULL,
    rsi           NUMERIC(6,2),
    macd_hist     NUMERIC(12,4),
    adx           NUMERIC(6,2),
    atr           NUMERIC(12,4),
    close_price   NUMERIC(14,2) NOT NULL,
    entry_price   NUMERIC(14,2) NOT NULL,
    target_price  NUMERIC(14,2) NOT NULL,
    cutloss_price NUMERIC(14,2) NOT NULL,
    reasoning     TEXT,                    -- NULL kalau LLM tidak dikonfigurasi/gagal
    batch_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ai_picks_batch_at ON ai_picks(batch_at);
```

### 7. `backend/db.py` — tambah `ensure_ai_picks_table()`
Sama persis pola `ensure_watchlist_table()` (idempoten, `CREATE TABLE IF NOT EXISTS`) —
supaya deployment lama (volume Postgres sudah ada) tetap dapat tabel baru tanpa migrasi manual.

### 8. `backend/config.py` — env vars baru
```python
# ── AI Picks (Tab 3) ──
AI_PICKS_TOP_N     = int(os.environ.get("AI_PICKS_TOP_N", "15"))
AI_PICKS_TTL_HOURS = float(os.environ.get("AI_PICKS_TTL_HOURS", "6"))

# ── LLM generik, provider-agnostic (OpenAI-compatible) ──
LLM_BASE_URL       = os.environ.get("LLM_BASE_URL", "").strip()   # kosong = nonaktif
LLM_MODEL          = os.environ.get("LLM_MODEL", "llama3.1")
LLM_API_KEY        = os.environ.get("LLM_API_KEY", "").strip()
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))
```

### 9. `backend/main.py`
```python
from routers import market, journal, watchlist, screener, ai_picks   # +screener, +ai_picks
...
db.init_pg_pool()
db.ensure_watchlist_table()
db.ensure_ai_picks_table()          # baru
...
app.include_router(watchlist.router)
app.include_router(screener.router)   # baru
app.include_router(ai_picks.router)   # baru
```

### 10. `backend/requirements.txt`
Tambah `httpx>=0.27,<1` (klien HTTP untuk `llm_client.py`).

---

## Frontend

### 1. `frontend/lib/types.ts` — tambah type
```typescript
export interface AiPick {
  id: number; symbol: string; sector: string | null; verdict: string; score: number;
  rsi: number | null; macd_hist: number | null; adx: number | null; atr: number | null;
  close_price: number; entry_price: number; target_price: number; cutloss_price: number;
  reasoning: string | null; batch_at: string;
}
export interface AiPicksStatus { generating: boolean; last_generated_at: number | null; }
```

### 2. `frontend/lib/api.ts` — tambah method (pola `get<T>()`/`send<T>()` yang sudah ada)
```typescript
aiPicks: () => get<{ picks: AiPick[] }>("/api/ai-picks"),
aiPicksStatus: () => get<AiPicksStatus>("/api/ai-picks/status"),
generateAiPicks: () => send<{ started: boolean }>("POST", "/api/ai-picks/generate"),
```

### 3. `frontend/lib/format.ts` — tambah `scoreColor` (pindahan dari inline)
```typescript
export const scoreColor = (s: number) =>
  s >= 50 ? "text-up" : s >= 20 ? "text-up/80" :
  s <= -50 ? "text-down" : s <= -20 ? "text-down/80" : "text-dim";
```

### 4. `frontend/components/VerdictBadge.tsx` (BARU) — extract dari inline component
Logika & markup identik dengan `VerdictBadge` yang sekarang inline di `watchlist/page.tsx` —
dipindah supaya dipakai bersama oleh halaman Screener & section AI Picks di Watchlist.

### 5. `frontend/app/screener/page.tsx` — ganti `<ComingSoon>` dengan UI screener
Pindahkan state + JSX preset/filter/tabel hasil dari halaman gabungan saat ini (apa adanya,
tanpa ubah logika). Tetap butuh `watchSet` (cek simbol sudah di watchlist) + `add()` untuk
tombol ★ — fetch `api.watchlist()` sekali saat mount khusus untuk itu (read-only, halaman ini
TIDAK menampilkan/mengelola list watchlist manual).

### 6. `frontend/app/watchlist/page.tsx` — sederhanakan + tambah section AI Picks
Hapus semua state/handler/JSX screener. Tambah:
- State `aiPicks`, `aiStatus` + polling status tiap 4 detik **selama** `generating: true`
  (mulai polling baik dari hasil refresh manual MAUPUN dari deteksi saat mount bahwa server
  lagi generate karena TTL — supaya semua tab browser ikut update begitu selesai).
- Card grid 15 AI Picks: simbol, `VerdictBadge`, skor (`scoreColor`), entry/target/cutloss,
  reasoning (atau italic "Reasoning AI tidak tersedia"), tombol ★ tambah ke watchlist (re-use
  `api.addWatchlist`).
- Baris status: "Digenerate X menit lalu" / "Sedang generate AI Picks…" + tombol "↻ Refresh".

Detail penting: setelah `loadAiPicks()` saat mount, **juga** panggil `aiPicksStatus()` sekali
untuk tahu apakah TTL auto-trigger sedang jalan di background (supaya UI langsung mulai
polling, bukan baru sadar saat reload manual berikutnya).

### 7. `frontend/components/Sidebar.tsx` — satu baris
```diff
- { href: "/screener", label: "Screener", icon: "🔎", n: 4, ready: false },
+ { href: "/screener", label: "Screener", icon: "🔎", n: 4, ready: true },
```

---

## Dokumentasi

- **`.env.example`** — tambah section AI Picks + LLM generik (lihat env vars di atas #8).
- **`CLAUDE.md`** — update status Tab 3/4, file structure list (+`ai_picks.py`,
  `routers/screener.py`, `routers/ai_picks.py`, `llm_client.py`), gotchas: jelaskan
  `LLM_BASE_URL` kosong = no-op instan (beda dari Hermes CLI yang catch `FileNotFoundError`),
  TTL/BackgroundTasks/lock pattern, dan **tegaskan AI Picks (Tab 3, batch, HTTP) berbeda
  mekanisme dari Tab 5 AI Advisor (single-stock, Hermes CLI subprocess, lihat
  `docs/hermes-integration.md`)** — supaya tidak tertukar lagi ke depannya.
- **`README.md`** — pisah baris fitur Tab 3 (Watchlist + AI Picks) dan Tab 4 (Screener),
  tambah section "🤖 AI Picks", tambah env var & API table, update roadmap.
- **`TESTING.md`** — tambah smoke-test `curl /api/ai-picks` + `/api/ai-picks/status`, checklist
  manual untuk Tab 3 AI Picks dan Tab 4 Screener (lihat Verifikasi di bawah).

---

## Verifikasi

**A. Screener pindah tanpa regresi**
1. `docker compose up -d --build backend frontend`
2. `curl localhost:8000/api/screener/presets` & `/api/screener?min_score=50&above_ma200=true` →
   sama seperti sebelum pindah (path URL tidak berubah).
3. Buka `/screener` → preset, filter, tabel jalan; ★ menambah ke watchlist (cek via
   `curl localhost:8000/api/watchlist`); klik simbol → ke `/analyst?symbol=...`.
4. Buka `/watchlist` → screener (preset/filter/tabel) **sudah tidak ada** di halaman ini.
5. Sidebar: "Screener" sudah bisa diklik (bukan chip "soon" lagi).

**B. AI Picks degrade dengan baik tanpa `LLM_BASE_URL` (kondisi default)**
1. Pastikan `.env` tidak mengisi `LLM_BASE_URL` (default kosong).
2. `curl -X POST localhost:8000/api/ai-picks/generate` → `{"started": true}` cepat.
3. Poll `curl localhost:8000/api/ai-picks/status` → `generating: true` lalu `false` —
   **cepat selesai** karena `call_llm()` return `None` instan (tidak ada network call sama
   sekali saat `LLM_BASE_URL` kosong, beda dari Hermes CLI yang masih spawn subprocess).
4. `curl localhost:8000/api/ai-picks` → 15 baris (atau kurang kalau kandidat bullish < 15),
   semua `reasoning: null`, dan `target_price > close_price > cutloss_price` di setiap baris.
5. Buka `/watchlist` → 15 kartu tampil dengan badge/skor/level harga + teks italic "Reasoning
   AI tidak tersedia" — tidak ada error console (cek via Playwright pola di `TESTING.md`).

**C. TTL + background task tidak blocking**
1. `docker compose exec postgres psql -U trading -d tradingdb -c "DELETE FROM ai_picks;"`
   (simulasi belum pernah generate).
2. `curl -s -w "\n%{time_total}s\n" -o /dev/null localhost:8000/api/ai-picks` → response time
   harus jauh di bawah 1 detik walau ini memicu generate di background.
3. Poll status sampai `generating: false`, lalu `GET /api/ai-picks` lagi → `batch_at` baru
   muncul, beda dari sebelumnya.
4. Trigger 2x `POST /api/ai-picks/generate` berurutan cepat → cek log backend, harus cuma
   ada satu baris `[+] AI Picks batch generated` (lock cegah overlap).

**D. Setelah `LLM_BASE_URL` benar-benar diisi** (opsional, kalau user sudah punya Ollama/vLLM)
1. Set `LLM_BASE_URL=http://<host>:11434/v1` + `LLM_MODEL=<nama model>` di `.env`, restart backend.
2. Generate ulang → `reasoning` di tabel `ai_picks` sekarang terisi teks Bahasa Indonesia 2-3
   kalimat per saham (bukan `null`).

---

## Catatan tambahan (tidak menghalangi, sekadar diketahui)

`Sidebar.tsx` saat ini hanya punya 5 slot nav (`n:1..5`: Journal, Analyst, Watchlist, Screener,
AI Advisor) — **tidak ada entry "Fundamental Analyst"** sama sekali di nav. Ini gap yang sudah
ada sebelum plan ini, tidak diperbaiki di sini (di luar scope). Kalau nanti Tab Fundamental mau
dibangun, perlu nomor slot baru.
