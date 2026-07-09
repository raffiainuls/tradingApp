"""Konfigurasi backend."""
import os

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

CH_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CH_PORT = int(os.environ.get("CLICKHOUSE_HTTP_PORT", "8123"))
CH_USER = os.environ.get("CLICKHOUSE_USER", "default")
CH_PASS = os.environ.get("CLICKHOUSE_PASSWORD", "")
CH_DB   = os.environ.get("CLICKHOUSE_DB", "market")

PG_HOST = os.environ.get("POSTGRES_HOST", "localhost")
PG_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
PG_USER = os.environ.get("POSTGRES_USER", "trading")
PG_PASS = os.environ.get("POSTGRES_PASSWORD", "tradingpass123")
PG_DB   = os.environ.get("POSTGRES_DB", "tradingdb")

VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"}

UNIVERSE_URL = os.environ.get(
    "UNIVERSE_URL",
    "https://raw.githubusercontent.com/wildangunawan/Dataset-Saham-IDX/master/List%20Emiten/all.csv",
)

# ── AI Picks (Tab 3) — generate MANUAL via tombol (tanpa auto/TTL) ──
AI_PICKS_TOP_N     = int(os.environ.get("AI_PICKS_TOP_N", "15"))

# ── LLM generik, provider-agnostic (OpenAI-compatible) ──
# Kosongkan LLM_BASE_URL untuk menonaktifkan (AI Picks tetap jalan, rule-based only).
# Arahkan ke Ollama/vLLM/LocalAI/LM Studio self-hosted, mis. http://host:11434/v1
LLM_BASE_URL        = os.environ.get("LLM_BASE_URL", "").strip()   # kosong = nonaktif
LLM_MODEL           = os.environ.get("LLM_MODEL", "llama3.1")
LLM_API_KEY         = os.environ.get("LLM_API_KEY", "").strip()
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))
# Batas token output. Reasoning model (mis. qwen/deepseek/glm) memakai sebagian budget
# untuk "berpikir" → set longgar agar jawaban akhir tidak terpotong/kosong.
LLM_MAX_TOKENS      = int(os.environ.get("LLM_MAX_TOKENS", "1500"))

# ── AI Advisor (Tab 5) — Hermes Agent via bridge HTTP, generate MANUAL via tombol ──
# Hermes (`bro_analysis`) hidup di HOST (luar Docker); backend (dalam container) tidak
# bisa subprocess langsung ke situ. `scripts/hermes_advisor_bridge.py` dijalankan di
# HOST, expose HTTP kecil yang di-subprocess-kan ke Hermes. Kosongkan/unreachable =
# AI Advisor tetap tampilkan data teknikal (ClickHouse), cuma narasi AI yang absen.
HERMES_BRIDGE_URL           = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:8090").strip()
HERMES_BRIDGE_TIMEOUT_SECONDS = int(os.environ.get("HERMES_BRIDGE_TIMEOUT_SECONDS", "150"))
# API key bridge — WAJIB saat bridge diakses lintas mesin (app di laptop, Hermes tetap
# di VPS; lihat docs/hermes-server-migration.md). Isinya harus sama dengan env var
# HERMES_BRIDGE_API_KEY di mesin tempat bridge jalan. Kosong = header tidak dikirim
# (hanya cocok untuk topologi lama: bridge di host yang sama, tanpa auth).
HERMES_BRIDGE_API_KEY       = os.environ.get("HERMES_BRIDGE_API_KEY", "").strip()
# Rekomendasi harian: Hermes SENDIRI yang menyeleksi (bukan cuma komentar) dari
# POOL_SIZE kandidat skor tertinggi (belum difilter bullish) -> pilih maksimal
# DAILY_TOP_N yang genuinely lolos kriteria (lihat ai_advisor.py).
AI_ADVISOR_POOL_SIZE        = int(os.environ.get("AI_ADVISOR_POOL_SIZE", "50"))
AI_ADVISOR_DAILY_TOP_N      = int(os.environ.get("AI_ADVISOR_DAILY_TOP_N", "8"))
