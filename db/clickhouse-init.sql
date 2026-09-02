-- ClickHouse schema untuk OHLCV (storage permanen).
-- ReplacingMergeTree → bar dengan (symbol, interval, ts) sama akan di-dedup,
-- menyimpan yang ingested_at terbaru. Idempoten terhadap re-stream/backfill.

CREATE DATABASE IF NOT EXISTS market;

CREATE TABLE IF NOT EXISTS market.ohlcv
(
    symbol      LowCardinality(String),
    type        LowCardinality(String),
    sector      LowCardinality(String),
    interval    LowCardinality(String),
    ts          DateTime,
    open        Float64,
    high        Float64,
    low         Float64,
    close       Float64,
    volume      Float64,
    ingested_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (symbol, interval, ts);

-- EOD resmi IDX langsung dari idx.co.id (BUKAN turunan yFinance) — tabel TERPISAH
-- dari market.ohlcv supaya tidak dedup-silang dgn data yFinance yang sudah dipakai
-- indicators.py (beda sumber, jangan dicampur di satu ORDER BY key). Diisi oleh
-- service idx-official (lihat gotcha CLAUDE.md soal Cloudflare 403 idx.co.id).
CREATE TABLE IF NOT EXISTS market.ohlcv_idx_official
(
    symbol       LowCardinality(String),
    date         Date,
    prev_close   Float64,
    open         Float64,
    high         Float64,
    low          Float64,
    close        Float64,
    volume       Float64,
    value        Float64,
    frequency    Float64,
    foreign_buy  Float64,
    foreign_sell Float64,
    ingested_at  DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (symbol, date);
