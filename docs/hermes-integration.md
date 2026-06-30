# Hermes Agent — Integrasi dengan Trading App IDX

> **Dokumen:** Cara koneksi Hermes Agent (`bro_analysis`) ke aplikasi trading IDX
> **Profile:** `bro_analysis`
> **Skill:** `stock-technical-fundamental-analysis`
> **Server:** Local / Self-hosted
> **Update:** Juni 2026

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
| Skill SKILL.md | `~/.hermes/profiles/bro_analysis/skills/research/stock-technical-fundamental-analysis/SKILL.md` |
| Script analisa | `.../scripts/analyze_stock.py` |
| Broker summary guide | `.../references/broker-summary.md` |

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

Panggil langsung fungsi Python dari skill Hermes untuk dapat data terstruktur:

```python
# Di backend Python (FastAPI)
import sys
sys.path.append("/home/ubuntu/.hermes/profiles/bro_analysis/skills/research/stock-technical-fundamental-analysis/scripts")
from analyze_stock import technical_analysis, fundamental_analysis

# Data dari ClickHouse → diubah ke DataFrame
hist = get_data_from_clickhouse("BBCA.JK")
ta = technical_analysis(hist)
# Hasil: RSI, MACD, Stochastic, ADX, OBV, dll
```

#### Mode B — Full AI Advisor (dengan LLM)

Kirim prompt ke Hermes untuk analisis naratif:

```bash
# Dari terminal
bro_analysis --skills stock-technical-fundamental-analysis chat -q \
  "Analisa BBCA.JK. Data: RSI 62, MACD bullish, ADX 28. \
   Beri rekomendasi Hold/Sell beserta reasoning-nya."
```

```python
# Dari backend
import subprocess
result = subprocess.run([
    "bro_analysis", "--skills",
    "stock-technical-fundamental-analysis",
    "chat", "-q", prompt_text
], capture_output=True, text=True, timeout=120)
ai_response = result.stdout
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

### 5.2 Start Hermes API Server (opsional)

```bash
python3 /home/ubuntu/documents/analisa_api.py --port 8080 &
```

### 5.3 Stop Semua

```bash
# Stop Docker app
cd /home/ubuntu/tradingApp && sudo docker compose down

# Stop Hermes API
pkill -f analisa_api.py
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

## 8. Integrasi ke Tab 5 (AI Advisor)

### 8.1 Perubahan yang Perlu Dibuat di Backend

Tambahkan file `backend/routers/ai_advisor.py`:

```python
from fastapi import APIRouter, Query
import sys
sys.path.append("/home/ubuntu/.hermes/profiles/bro_analysis/skills/research/stock-technical-fundamental-analysis/scripts")
from analyze_stock import technical_analysis, fundamental_analysis

router = APIRouter(prefix="/api", tags=["ai-advisor"])

@router.get("/ai-analysis")
def ai_analysis(symbol: str = Query(...), period: str = "1y"):
    # 1. Ambil data dari ClickHouse (atau fallback ke yfinance)
    # 2. Jalankan technical_analysis()
    # 3. Jalankan fundamental_analysis()
    # 4. (Optional) Kirim ke Hermes LLM untuk narasi
    # 5. Return JSON
    pass
```

Daftarkan di `backend/main.py`:

```python
from routers import ai_advisor
app.include_router(ai_advisor.router)
```

### 8.2 Perubahan di Frontend (Tab 5)

File: `frontend/app/ai-advisor/page.tsx`

- Panggil `/api/ai-analysis?symbol=BBCA`
- Tampilkan hasil dalam format: bias, ringkasan teknikal, ringkasan fundamental, rekomendasi

---

## 9. Troubleshooting

### 9.1 Docker tidak bisa dijalankan

```bash
# Cek status Docker
sudo systemctl status docker

# Restart Docker
sudo systemctl restart docker

# Cek log container spesifik
sudo docker compose logs -f backend
```

### 9.2 Hermes profile tidak ditemukan

```bash
# Cek profile terdaftar
hermes profile list

# Cek skill terinstall
hermes skills list
```

### 9.3 Data ClickHouse kosong

Data perlu waktu ~5-15 menit pertama untuk terisi dari yFinance.

```bash
# Cek jumlah data
curl -s http://localhost:8123 -u default:tradingch123 \
  --data "SELECT count(), toStartOfDay(timestamp) as day FROM market.ohlcv GROUP BY day ORDER BY day"
```

### 9.4 Yahoo Finance rate limit

Jika sering kena rate limit:
1. Perbesar `POLL_INTERVAL` di `.env` (default 300s → 600s)
2. Kecilkan `CHUNK_SIZE` (default 60 → 30)
3. Atau batasi `MAX_SYMBOLS` ke jumlah kecil

### 9.5 Git push error (autentikasi)

```bash
# Tes koneksi SSH
ssh -T git@github.com

# Harusnya muncul: "Hi raffiainuls! You've successfully authenticated"
```

---

## 10. Quick Reference Commands

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

### API Server (opsional)

| Perintah | Fungsi |
|---|---|
| `python3 /home/ubuntu/documents/analisa_api.py` | Start Hermes API |
| `curl http://localhost:8080/analisa/BBCA.JK` | Test API |

---

> **Catatan:** Dokumen ini akan diperbarui seiring penambahan fitur baru.
> Untuk pertanyaan lebih lanjut, tanyakan langsung ke Hermes Agent 😊
