# Hermes Agent — Integrasi dengan Trading App IDX

> **Dokumen:** Cara koneksi Hermes Agent (`bro_analysis`) ke aplikasi trading IDX
> **Profile:** `bro_analysis`
> **Skills:** `stock-technical-fundamental-analysis`, `daily-stock-picks` (referensi
> pengetahuan; TIDAK dimuat via `--skills` di Tab 5 — lihat §9, alasan di §3.2 Mode B)
> **Terintegrasi dengan:** Tab 3 AI Picks (LLM generik via HTTP), Tab 5 AI Advisor
> (Hermes CLI via `scripts/hermes_advisor_bridge.py` — **sudah diimplementasikan**)
> **Server:** Local / Self-hosted
> **Update:** 2026-07-01 — Tab 5 AI Advisor selesai dibangun, lihat §9

---

## 1. Arsitektur Integrasi

### Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     SERVER LOKAL (satu mesin)                     │
│                                                                  │
│  ┌─────────────────────┐    ┌────────────────────────────────┐   │
│  │  Hermes Agent       │    │  Trading App (Docker)           │   │
│  │                     │    │                                │   │
│  │  Profile:           │    │  ┌──────────────────────────┐  │   │
│  │  bro_analysis       │    │  │  Frontend (Next.js)      │  │   │
│  │                     │    │  │  http://localhost:3001    │  │   │
│  │  ┌───────────────┐  │    │  └──────────┬───────────────┘  │   │
│  │  │ Skill:        │  │    │             │                   │   │
│  │  │ stock-technical│ │    │  ┌──────────▼───────────────┐  │   │
│  │  │ -fundamental- │  │    │  │  Backend (FastAPI)       │  │   │
│  │  │ analysis      │  │    │  │  http://localhost:8000   │  │   │
│  │  └───────┬───────┘  │    │  │                          │  │   │
│  │          │           │    │  │  /api/history            │  │   │
│  │  ┌───────▼───────┐  │    │  │  /api/indicators         │  │   │
│  │  │ analyze_stock │  │    │  │  /api/ai-analysis  🆕    │  │   │
│  │  │ .py           │  │    │  └──────────┬───────────────┘  │   │
│  │  │               │  │    │             │                   │   │
│  │  │ • 15+ indikator│  │    │  ┌──────────▼───────────────┐  │   │
│  │  │ • Candlestick │  │    │  │  ClickHouse (OHLCV)       │  │   │
│  │  │ • Bias scoring│  │    │  │  PostgreSQL (Journal)     │  │   │
│  │  │ • Broker      │  │    │  │  Kafka (Streaming)        │  │   │
│  │  │   Summary     │  │    │  └──────────────────────────┘  │   │
│  │  └───────────────┘  │    └────────────────────────────────┘   │
│  └─────────────────────┘                                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Komponen yang Diperlukan

### 2.1 Hermes Agent

| Komponen | Path |
|---|---|
| Profile | `~/.hermes/profiles/bro_analysis/` |
| Skill — Analisis Individu | `.../research/stock-technical-fundamental-analysis/SKILL.md` |
| Skill — Daily Picks | `.../research/daily-stock-picks/SKILL.md` |
| Script analisa | `.../stock-technical-fundamental-analysis/scripts/analyze_stock.py` |
| Broker summary guide | `.../stock-technical-fundamental-analysis/references/broker-summary.md` |

### 2.2 Trading App

| Komponen | Port | Path di Server |
|---|---|---|
| Frontend (Next.js) | `:3001` | `/home/ubuntu/tradingApp/frontend/` |
| Backend (FastAPI) | `:8000` | `/home/ubuntu/tradingApp/backend/` |
| ClickHouse | `:8123` | Docker container |
| PostgreSQL | `:5432` | Docker container |
| Kafka | `:9092` | Docker container |

---

## 3. Cara Kerja Integrasi

### 3.1 Skema Alur Data AI Analysis

```
User klik "AI Analysis" di Tab 5
        │
        ▼
Frontend → GET /api/ai-analysis?symbol=BBCA
        │
        ▼
Backend /api/ai-analysis:
  1. Ambil data OHLCV dari ClickHouse
  2. Ambil indikator dari backend/indicators.py (yang sudah ada)
  3. Panggil Hermes skill analyze_stock.py untuk:
     a. Validasi indikator teknikal (RSI Wilder, MACD, Stochastic, ADX, OBV)
     b. Deteksi candlestick pattern (24 pola)
     c. Hitung bias scoring (Bullish/Neutral/Bearish)
  4. (Optional) Kirim data ke Hermes LLM untuk narasi rekomendasi
  5. Return JSON ke frontend
        │
        ▼
Frontend tampilkan: chart + indikator + AI summary + rekomendasi
```

### 3.2 Dua Mode Integrasi

#### Mode A — Analisis Langsung (tanpa LLM)

> ⚠️ **Update 2026-07-01 (implementasi nyata Tab 5):** pseudocode `sys.path.append(...)`
> di bawah ini **TIDAK JALAN** karena backend Trading App jalan di **Docker container**,
> sedangkan skill Hermes ada di filesystem **HOST** — dua filesystem terpisah, `import`
> lintas itu akan `ModuleNotFoundError`. Yang diimplementasikan: Tab 5 pakai
> `backend/indicators.py` + ClickHouse **langsung** (data sudah ada, sudah jalan di
> Tab 2/3/4, tidak butuh yfinance/Hermes sama sekali untuk angka teknikal). Snippet di
> bawah tetap relevan **kalau** backend suatu saat tidak lagi di-Docker-kan.

Panggil langsung fungsi Python dari skill Hermes untuk dapat data terstruktur:

```python
# Di backend Python (FastAPI) -- HANYA valid kalau backend TIDAK di Docker
import sys
sys.path.append("/home/ubuntu/.hermes/profiles/bro_analysis/skills/research/stock-technical-fundamental-analysis/scripts")
from analyze_stock import technical_analysis, fundamental_analysis

# Data dari ClickHouse → diubah ke DataFrame
hist = get_data_from_clickhouse("BBCA.JK")
ta = technical_analysis(hist)
# Hasil: RSI, MACD, Stochastic, ADX, OBV, dll
```

#### Mode B — Full AI Advisor (dengan LLM)

> ⚠️ **Update 2026-07-01:** implementasi nyata **TIDAK** memuat `--skills`. Skill
> `stock-technical-fundamental-analysis`/`daily-stock-picks` menginstruksikan agent
> fetch data sendiri via `yf.Ticker(...).history()` begitu dimuat — persis yang mau
> dihindari (IP server ini sering 429 dari Yahoo, lihat §10.4). Prompt yang dikirim ke
> Hermes SUDAH menyertakan semua angka teknikal (dari ClickHouse), Hermes cuma diminta
> menulis narasinya. Juga, backend (Docker) tidak bisa `subprocess` langsung ke
> `bro_analysis` (ada di PATH **host**, bukan di container) — dijembatani lewat HTTP,
> lihat `scripts/hermes_advisor_bridge.py` & §5.2b.

Kirim prompt ke Hermes untuk analisis naratif (tanpa `--skills`, data inline di prompt):

```bash
# Dari terminal (host, tempat bro_analysis ada di PATH)
bro_analysis chat -q \
  "Kamu analis teknikal saham IDX. JANGAN fetch data lain -- gunakan HANYA data ini:
   BBCA, RSI 62, MACD bullish, ADX 28, skor 65 (STRONG BUY).
   Beri analisa singkat & bias, akhiri disclaimer bukan saran investasi."
```

```python
# Di scripts/hermes_advisor_bridge.py (HOST, bukan di dalam container backend)
import subprocess
result = subprocess.run(
    ["bro_analysis", "chat", "-q", prompt_text],   # TANPA --skills
    capture_output=True, text=True, timeout=150,
)
# stdout dibungkus box unicode (╭─ ⚕ Hermes ─...─╮), perlu di-parse -- lihat _extract_reply()
```

---

## 4. Endpoint API (yang sudah ada)

### 4.1 Trading App Backend

| Endpoint | Method | Keterangan |
|---|---|---|
| `/health` | GET | Status backend |
| `/api/symbols` | GET | Daftar emiten |
| `/api/history?symbol=BBCA.JK&interval=1d` | GET | Data OHLCV historis |
| `/api/quotes` | GET | Quote terbaru semua emiten |
| `/ws` | WebSocket | Streaming live price |

### 4.2 Hermes API Server (opsional — untuk akses dari luar)

Jalankan API server Hermes:

```bash
python3 /home/ubuntu/documents/analisa_api.py --port 8080 &
```

| Endpoint | Method | Keterangan |
|---|---|---|
| `/health` | GET | Status Hermes API |
| `/analisa/<TICKER>` | GET | Full analysis dari skill |

---

## 5. Cara Mulai & Hentikan

### 5.1 Start Trading App

```bash
cd /home/ubuntu/tradingApp
sudo docker compose up -d
```

Cek status:
```bash
sudo docker ps
```

Akses:
- Frontend: http://localhost:3001
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 5.2 Start Hermes API Server (opsional — utk §8, LLM_BASE_URL Tab 3)

```bash
python3 /home/ubuntu/documents/analisa_api.py --port 8080 &
```

### 5.2b Start Hermes Advisor Bridge (WAJIB utk Tab 5 AI Advisor)

Beda dari 5.2 di atas — ini khusus Tab 5, ada di dalam repo (`scripts/`), subprocess
`bro_analysis chat -q` (tanpa `--skills`), bukan `analyze_stock.py`/yfinance:

```bash
cd /home/ubuntu/tradingApp
python3 scripts/hermes_advisor_bridge.py --port 8090 &
```

Tanpa ini jalan, Tab 5 tetap tampil (data teknikal dari ClickHouse via `/api/ai-advisor/*`),
cuma narasi AI-nya kosong ("Narasi AI tidak tersedia"). Backend (Docker) menjangkau bridge
ini via `http://host.docker.internal:8090` (env `HERMES_BRIDGE_URL`); `extra_hosts` sudah
di-set di `docker-compose.yml` service `backend` supaya nama itu resolve dari container.

### 5.3 Stop Semua

```bash
# Stop Docker app
cd /home/ubuntu/tradingApp && sudo docker compose down

# Stop Hermes API (§5.2) & Advisor Bridge (§5.2b)
pkill -f analisa_api.py
pkill -f hermes_advisor_bridge.py
```

### 5.4 Melihat Log

```bash
# Log Docker
sudo docker compose logs -f backend     # Backend saja
sudo docker compose logs -f frontend    # Frontend saja
sudo docker compose logs -f ingestion   # Data ingestion

# Semua service
sudo docker compose logs -f
```

---

## 6. Penggunaan Profile `bro_analysis`

### 6.1 Cara Panggil Profile

```bash
# Masuk ke sesi chat Hermes dengan profile bro_analysis
bro_analysis

# Atau pake flag
hermes --profile bro_analysis

# Langsung query
bro_analysis chat -q "Analisa BBCA.JK pakai skill stock"
```

### 6.2 Load Skill di Sesi

```bash
# Dari CLI
bro_analysis --skills stock-technical-fundamental-analysis

# Dari dalam sesi chat
/skill stock-technical-fundamental-analysis
```

### 6.3 Melihat Skill yang Terinstall

```bash
bro_analysis skills list
```

---

## 7. Struktur Data Output Hermes Skill

### 7.1 Technical Analysis Output

```python
ta = {
    "major_trend": "UPTREND 📈",
    "price": 10250.0,
    "sma20": 10100.0,
    "sma50": 9850.0,
    "sma200": 9200.0,
    "golden_cross": False,
    "death_cross": False,
    "rsi": 62.5,
    "rsi_signal": "Neutral (62)",
    "rsi_divergence": "None",
    "macd": 45.2,
    "macd_signal": 42.1,
    "macd_cross": "Bullish Crossover ⬆️",
    "stoch_k": 65.0,
    "stoch_d": 58.0,
    "stoch_zone": "Neutral",
    "adx": 28.0,
    "adx_signal": "Trending market",
    "obv_trend": "Up 📈",
    "obv_divergence": "None",
    "bb_upper": 10750.0,
    "bb_lower": 9450.0,
    "bb_signal": "Within bands (normal)",
    "nearest_resistance": 10500.0,
    "nearest_support": 9500.0,
    "volatility_20d": 22.5,
    "candle_patterns": [
        ("2026-06-28", "Bullish Engulfing 🔄"),
        ("2026-06-25", "Hammer 🔨 (bullish reversal)")
    ]
}
```

### 7.2 Fundamental Analysis Output

```python
fa = {
    "valuation": {
        "P/E (TTM)": 18.5,
        "P/B": 2.8,
        "EV/EBITDA": 12.3
    },
    "profitability": {
        "EPS (TTM)": 550.0,
        "Net Margin": 0.32,
        "ROE": 0.19
    },
    "health": {
        "Debt/Equity": 0.6,
        "Current Ratio": 1.8
    },
    "growth": {
        "Revenue Growth (YoY)": 0.12,
        "Dividend Yield": 0.032
    }
}
```

---

## 8. Integrasi AI Picks (Tab 3) — LLM Provider

### 8.1 Tentang AI Picks Tab 3

Tab 3 (Watchlist) sudah memiliki fitur **AI Picks** — mesin scoring yang menghasilkan top-15 saham bullish setiap hari. Fitur ini sudah aktif secara **rule-based** (tanpa LLM). Untuk menambahkan **narasi/reasoning** dari AI, cukup set 2 env variable:

| Variable | Contoh | Keterangan |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:8080/v1` atau `http://192.168.1.100:11434/v1` | URL OpenAI-compatible API |
| `LLM_MODEL` | `deepseek-v4-flash` atau `llama3` | Nama model |

### 8.2 Arahkan ke Hermes API Server

```bash
# 1. Start Hermes API server di port 8080
python3 /home/ubuntu/documents/analisa_api.py --port 8080 &

# 2. Set di .env trading app
LLM_BASE_URL=http://localhost:8080/v1
LLM_MODEL=deepseek-v4-flash
```

### 8.3 Arahkan ke Ollama (alternatif)

```bash
# 1. Install & start Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3
ollama serve &

# 2. Set di .env
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3
```

### 8.4 Verifikasi

```bash
# Test dari backend
curl -X POST http://localhost:8000/api/ai-picks/generate

# Cek hasil
curl http://localhost:8000/api/ai-picks
```

> **Catatan:** Jika `LLM_BASE_URL` kosong, AI Picks tetap jalan rule-based tanpa reasoning LLM.

---

## 9. Integrasi ke Tab 5 (AI Advisor) — SUDAH DIIMPLEMENTASIKAN (2026-07-01)

Rencana awal di bawah (sys.path import, fetch yfinance/saham-mcp) berubah setelah
verifikasi empiris: real-time yfinance/saham-mcp 429 dari IP server ini, histori GitHub
dataset saham-mcp beku sejak Feb 2025 (lebih basi dari ClickHouse sendiri), dan backend
Docker tidak bisa akses `bro_analysis` (PATH host) langsung. Arsitektur final:

```
Frontend (/advisor) ──POST──▶ backend/routers/ai_advisor.py (Docker)
                                        │
                         ┌──────────────┴───────────────┐
                         ▼                               ▼
              backend/indicators.py            backend/hermes_bridge.py
              + ClickHouse (data teknikal,             │ HTTP POST /advise
                sama seperti Tab 2/3/4)                 ▼
                         │              scripts/hermes_advisor_bridge.py (HOST)
                         │                       │ subprocess (TANPA --skills)
                         │                       ▼
                         │                 bro_analysis chat -q "<prompt+data>"
                         ▼                       │
                  gabung jadi 1 respons ◀─────────┘ (narasi teks, atau null kalau gagal)
```

### 9.1 Backend

- **`backend/ai_advisor.py`** — `analyze_symbol(symbol)`: `db.fetch_ohlcv` → `indicators.latest_signals`
  → hitung entry/target/cutloss dari ATR (rumus sama persis dgn `ai_picks._levels`, sengaja
  di-mirror bukan di-import lintas modul) → bangun prompt (data inline, larang fetch lain)
  → `hermes_bridge.ask_hermes(prompt)`. `daily_recommendations(top_n)`: **Hermes sendiri yang
  menyeleksi** (bukan cuma komentar, lihat §9.4) dari `_candidate_pool()` (top skor, verdict
  apa pun, exclude Pemantauan Khusus) — 1 prompt berisi seluruh pool + kriteria seleksi →
  Hermes putuskan sendiri mana yang lolos, parsing simbol pilihan via `_parse_picks()`.
- **`backend/hermes_bridge.py`** — `ask_hermes(prompt) -> str | None`, httpx ke
  `HERMES_BRIDGE_URL`, NEVER raise (pola sama dgn `llm_client.call_llm`).
- **`backend/routers/ai_advisor.py`** — `POST /api/ai-advisor/analysis?symbol=`,
  `POST /api/ai-advisor/daily-picks`. Sinkron (bukan BackgroundTasks) krn cuma 1 panggilan
  Hermes per request, bukan batch — frontend tinggal tunggu dgn spinner.
- **`scripts/hermes_advisor_bridge.py`** — HTTP stdlib-only di **HOST**, `POST /advise`
  → `subprocess.run(["bro_analysis","chat","-q",prompt])` (TANPA `--skills`) → parse box
  unicode output → `{"text": ...}`. Jalankan manual: `python3 scripts/hermes_advisor_bridge.py --port 8090 &`
- **`docker-compose.yml`** — `extra_hosts: ["host.docker.internal:host-gateway"]` di
  service `backend`, supaya container bisa `httpx.post("http://host.docker.internal:8090/advise")`.

### 9.2 Frontend

File: `frontend/app/advisor/page.tsx` — form 1 simbol (baca `?symbol=` dari URL, konsisten
dgn Analyst) + tombol "Analisa dengan AI" (panggil `POST /api/ai-advisor/analysis`), render
pakai `TechnicalSummary` (component shared dgn Analyst, tipe `Signals`) + kartu entry/target/
cutloss + blok narasi Hermes. Section kedua "Rekomendasi Hari Ini" — tombol
`POST /api/ai-advisor/daily-picks` → grid kandidat **hasil seleksi Hermes** (reuse `VerdictBadge`)
+ 1 blok penjelasan lengkap Hermes (evaluasi tiap kandidat + kenapa yang lain tidak lolos).

### 9.3 Kenapa TIDAK ada tabel Postgres baru

Hasil AI Advisor **ephemeral** (tidak disimpan) — beda dari AI Picks yang persist ke
tabel `ai_picks` (utk konvergensi cross-tab + TTL). Tab 5 sinkron 1x per klik, tidak perlu
riwayat; regenerate setiap kali user klik tombol.

### 9.4 "Rekomendasi Hari Ini" — revisi desain (2026-07-01): Hermes SENDIRI memilih

Desain awal (sebelum revisi ini) kirim top-N bullish yang **sudah kita filter** (sama
persis logika `ai_picks._pick_candidates`) ke Hermes, minta 1 komentar naratif di atasnya.
User menilai ini terlalu mirip AI Picks (Tab 3) — cuma beda satu prompt gabungan vs banyak
prompt. Revisi: Hermes **benar-benar melakukan seleksi**, bukan sekadar menulis komentar.

**Alur baru:**
1. `_candidate_pool(AI_ADVISOR_POOL_SIZE)` — ambil top-skor **verdict apa pun** (BUKAN
   pra-filter bullish), exclude papan Pemantauan Khusus (filter kualitas data, bukan
   filter seleksi — itu tugas Hermes).
2. Prompt berisi SELURUH pool + kriteria eksplisit dari skill `daily-stock-picks`
   (Momentum Breakout: harga>SMA20 & RSI 50-70 & ADX>20 & MACD bullish; Oversold Bounce:
   RSI<35 & dekat SMA200; Trend Continuation: harga>SMA50 & >SMA200 & ADX>25) — deskripsi
   kriteria ditulis inline di prompt, BUKAN via `--skills` (tetap menghindari fetch yfinance).
3. Instruksi: evaluasi SETIAP kandidat, pilih maksimal `AI_ADVISOR_DAILY_TOP_N` yang
   genuinely lolos (**boleh 0 s.d. N, TIDAK dipaksa penuh** — kalau pool lemah semua,
   Hermes boleh bilang tidak ada yang layak).
4. Respons WAJIB diakhiri baris `PILIHAN: SIMBOL1,SIMBOL2,...` — di-parse oleh
   `ai_advisor._parse_picks()` (regex ambil semua setelah `PILIHAN:`, per-token dibersihkan
   dari karakter non-alfanumerik, lalu **divalidasi harus ada di pool** — token yang bukan
   simbol pool/halusinasi dibuang diam-diam, tidak pernah dipercaya mentah-mentah).
5. **Angka yang ditampilkan tetap 100% dari sistem** — `_parse_picks` mengembalikan objek
   dari `pool` kita sendiri (bukan angka yang ditulis Hermes di teksnya), Hermes cuma
   menentukan SIMBOL mana yang lolos. Prinsip "AI tidak boleh mengarang angka" (sama seperti
   AI Picks Tab 3) tetap dipegang, hanya perannya diperluas dari "menulis" jadi "memilih".
6. Fallback kalau parsing gagal / bridge tidak terjangkau: `pool[:max_picks]` (top-N pool
   by score, deterministik) — UI tidak pernah blank.

**Trade-off yang disadari & diterima:** latency naik (~30-50 detik vs ~10-20 detik
sebelumnya, krn Hermes mengevaluasi 40-50 baris bukan cuma menulis komentar atas 8-10),
dan hasil TIDAK 100% deterministik antar generate (sifat LLM) — beda dari AI Picks Tab 3
yang selalu identik untuk data yang sama.

---

## 10. Troubleshooting

### 10.1 Docker tidak bisa dijalankan

```bash
# Cek status Docker
sudo systemctl status docker

# Restart Docker
sudo systemctl restart docker

# Cek log container spesifik
sudo docker compose logs -f backend
```

### 10.2 Hermes profile tidak ditemukan

```bash
# Cek profile terdaftar
hermes profile list

# Cek skill terinstall
hermes skills list
```

### 10.3 Data ClickHouse kosong

Data perlu waktu ~5-15 menit pertama untuk terisi dari yFinance.

```bash
# Cek jumlah data
curl -s http://localhost:8123 -u default:tradingch123 \
  --data "SELECT count(), toStartOfDay(timestamp) as day FROM market.ohlcv GROUP BY day ORDER BY day"
```

### 10.4 Yahoo Finance rate limit

Jika sering kena rate limit:
1. Perbesar `POLL_INTERVAL` di `.env` (default 300s → 600s)
2. Kecilkan `CHUNK_SIZE` (default 60 → 30)
3. Atau batasi `MAX_SYMBOLS` ke jumlah kecil

### 10.5 Git push error (autentikasi)

```bash
# Tes koneksi SSH
ssh -T git@github.com

# Harusnya muncul: "Hi raffiainuls! You've successfully authenticated"
```

---

## 11. Quick Reference Commands

### Docker

| Perintah | Fungsi |
|---|---|
| `sudo docker compose up -d` | Start semua service |
| `sudo docker compose down` | Stop semua service |
| `sudo docker compose logs -f` | Lihat log semua service |
| `sudo docker compose build --no-cache backend` | Re-build backend |
| `sudo docker ps` | Daftar container running |

### Git

| Perintah | Fungsi |
|---|---|
| `git pull` | Ambil perubahan dari GitHub |
| `git add .` | Stage semua perubahan |
| `git commit -m "pesan"` | Commit perubahan |
| `git push` | Kirim ke GitHub |

### Hermes

| Perintah | Fungsi |
|---|---|
| `bro_analysis` | Masuk sesi Hermes profile bro_analysis |
| `bro_analysis chat -q "..."` | Query langsung |
| `hermes profile list` | Lihat semua profile |

### 6.4 Skill — List Lengkap di Profile

Profile `bro_analysis` memiliki **2 skill** untuk AI analysis:

| Skill | Fungsi | Cara Pakai |
|---|---|---|
| **`stock-technical-fundamental-analysis`** | Analisis individu per saham (RSI, MACD, ADX, dll + fundamental) | `/skill stock-technical-fundamental-analysis` |
| **`daily-stock-picks`** | Screening & rekomendasi saham harian IDX | `/skill daily-stock-picks` |

```bash
# Load skill langsung dari CLI
bro_analysis --skills stock-technical-fundamental-analysis chat -q "Analisa BBCA.JK"
bro_analysis --skills daily-stock-picks chat -q "Top picks hari ini"
```

### API Server (opsional)

| Perintah | Fungsi |
|---|---|
| `python3 /home/ubuntu/documents/analisa_api.py` | Start Hermes API |
| `curl http://localhost:8080/analisa/BBCA.JK` | Test API |

---

> **Catatan:** Dokumen ini akan diperbarui seiring penambahan fitur baru.
> Untuk pertanyaan lebih lanjut, tanyakan langsung ke Hermes Agent 😊
