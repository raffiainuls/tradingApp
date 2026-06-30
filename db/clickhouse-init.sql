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
