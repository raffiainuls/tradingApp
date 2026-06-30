"""
Kafka `raw-ohlcv` → ClickHouse (batch INSERT) + forward ke `ohlc-live` untuk WS.

Baris masuk (pipe-delimited): B|code|type|sector|interval|epoch|open|high|low|close|volume
"""
import os
import json
import time
from datetime import datetime, timezone

import clickhouse_connect
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
CH_HOST = os.environ.get("CLICKHOUSE_HOST", "clickhouse")
CH_PORT = int(os.environ.get("CLICKHOUSE_HTTP_PORT", "8123"))
CH_USER = os.environ.get("CLICKHOUSE_USER", "default")
CH_PASS = os.environ.get("CLICKHOUSE_PASSWORD", "")
CH_DB   = os.environ.get("CLICKHOUSE_DB", "market")

RAW_TOPIC  = "raw-ohlcv"
LIVE_TOPIC = "ohlc-live"
COLS = ["symbol", "type", "sector", "interval", "ts", "open", "high", "low", "close", "volume"]
BATCH = 2000
FLUSH_SECONDS = 2.0


def wait_kafka():
    while True:
        try:
            KafkaConsumer(bootstrap_servers=KAFKA_BOOTSTRAP).close()
            return
        except NoBrokersAvailable:
            print("[*] Waiting for Kafka...", flush=True)
            time.sleep(5)


def get_ch():
    while True:
        try:
            c = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER,
                                              password=CH_PASS, database=CH_DB)
            c.query("SELECT 1")
            print("[+] ClickHouse connected", flush=True)
            return c
        except Exception as e:
            print(f"[*] Waiting for ClickHouse: {e}", flush=True)
            time.sleep(5)


def parse(line: str):
    p = line.split("|")
    if len(p) != 11 or p[0] != "B":
        return None
    try:
        epoch = int(p[5])
        return {
            "symbol": p[1], "type": p[2], "sector": p[3], "interval": p[4],
            "epoch": epoch, "ts": datetime.fromtimestamp(epoch, tz=timezone.utc),
            "open": float(p[6]), "high": float(p[7]), "low": float(p[8]),
            "close": float(p[9]), "volume": float(p[10]),
        }
    except (ValueError, IndexError):
        return None


def main():
    wait_kafka()
    ch = get_ch()
    consumer = KafkaConsumer(
        RAW_TOPIC, bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest", enable_auto_commit=True,
        group_id="clickhouse-writer",
        value_deserializer=lambda m: m.decode("utf-8", errors="ignore"),
        max_poll_records=2000, fetch_max_wait_ms=500,
    )
    producer = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP,
                             value_serializer=lambda m: json.dumps(m).encode("utf-8"), linger_ms=100)
    print("[+] Writer running: raw-ohlcv → ClickHouse + ohlc-live", flush=True)

    batch, total, last_flush = [], 0, time.monotonic()

    def flush():
        nonlocal batch, total
        if not batch:
            return
        try:
            ch.insert(f"{CH_DB}.ohlcv", [[r[c] for c in COLS] for r in batch], column_names=COLS)
            total += len(batch)
            print(f"[i] inserted {len(batch)} (total {total})", flush=True)
        except Exception as e:
            print(f"[!] ClickHouse insert error: {e}", flush=True)
        batch = []

    while True:
        records = consumer.poll(timeout_ms=1000, max_records=2000)
        for _tp, msgs in records.items():
            for m in msgs:
                row = parse(m.value)
                if not row:
                    continue
                batch.append(row)
                producer.send(LIVE_TOPIC, value={
                    "symbol": row["symbol"], "type": row["type"], "sector": row["sector"],
                    "interval": row["interval"], "epoch": row["epoch"],
                    "timestamp": row["ts"].isoformat(),
                    "open": row["open"], "high": row["high"], "low": row["low"],
                    "close": row["close"], "volume": row["volume"],
                })
        now = time.monotonic()
        if len(batch) >= BATCH or (batch and now - last_flush >= FLUSH_SECONDS):
            flush()
            last_flush = now


if __name__ == "__main__":
    main()
