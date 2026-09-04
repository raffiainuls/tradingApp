#!/usr/bin/env python3
"""
Broker Summary per-saham (IndexAlpha, pihak ketiga berbayar) → ClickHouse.

IDX resmi (idx.co.id) CUMA punya broker summary agregat market-wide (lihat
gotcha CLAUDE.md), bukan breakdown per-saham per-broker. indexalpha.id satu-
satunya sumber yang sudah tervalidasi kasih data ini (avg harga broker
konsisten sama OHLC resmi dari idx-official).

MANUAL trigger saja (spt AI Picks) — SENGAJA TIDAK dijadikan cron otomatis,
krn quota indexalpha.id terbatas & berbayar (free tier cuma 5 request/hari).
Zero-dependency (stdlib only) spt scripts/hermes_advisor_bridge.py.

Usage:
    python3 scripts/broker_summary_sync.py --symbols BBCA,BBRI,TLKM
    python3 scripts/broker_summary_sync.py --symbols BBCA --date 2026-09-01
    python3 scripts/broker_summary_sync.py   # pakai INDEXALPHA_SYMBOLS dari .env

Env yang dipakai:
    INDEXALPHA_API_KEY   wajib
    INDEXALPHA_SYMBOLS   default kalau --symbols tidak dikasih (comma-separated)
    CLICKHOUSE_HOST/HTTP_PORT/USER/PASSWORD/DB
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import date

API_BASE = "https://api.indexalpha.id"
BATCH_MAX_TICKERS = 50  # batas API

CH_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CH_PORT = os.environ.get("CLICKHOUSE_HTTP_PORT", "8123")
CH_USER = os.environ.get("CLICKHOUSE_USER", "default")
CH_PASS = os.environ.get("CLICKHOUSE_PASSWORD", "")
CH_DB = os.environ.get("CLICKHOUSE_DB", "market")


def fetch_batch(api_key: str, tickers: list, date_str: str, investor: str, market: str) -> dict:
    payload = json.dumps({
        "tickers": tickers,
        "from": date_str,
        "to": date_str,
        "investor": investor,
        "market": market,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/stocks/broker-summary/batch",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"IndexAlpha HTTP {e.code}: {detail}") from e

    if not body.get("success"):
        raise RuntimeError(f"IndexAlpha balas success=false: {body.get('error')}")
    return body.get("data") or {}


def to_rows(data_by_ticker: dict, date_str: str, investor: str) -> list:
    rows = []
    for symbol, entries in data_by_ticker.items():
        for e in entries:
            rows.append({
                "symbol": symbol,
                "date": date_str,
                "investor": investor,
                "broker_code": e.get("code", ""),
                "buy_freq": e.get("buy_freq", 0) or 0,
                "buy_volume": e.get("buy_volume", 0) or 0,
                "buy_value": e.get("buy_value", 0) or 0,
                "sell_freq": e.get("sell_freq", 0) or 0,
                "sell_volume": e.get("sell_volume", 0) or 0,
                "sell_value": e.get("sell_value", 0) or 0,
                "buy_avg": e.get("buy_avg", 0) or 0,
                "sell_avg": e.get("sell_avg", 0) or 0,
            })
    return rows


def insert_rows(rows: list):
    if not rows:
        return
    body = "\n".join(json.dumps(r) for r in rows).encode("utf-8")
    query = f"INSERT INTO {CH_DB}.broker_summary FORMAT JSONEachRow"
    url = f"http://{CH_HOST}:{CH_PORT}/?query={urllib.parse.quote(query)}"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "X-ClickHouse-User": CH_USER,
            "X-ClickHouse-Key": CH_PASS,
            "Content-Type": "text/plain",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ClickHouse insert gagal HTTP {e.code}: {detail}") from e


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", help="comma-separated, mis. BBCA,BBRI,TLKM")
    parser.add_argument("--date", help="YYYY-MM-DD, default hari ini")
    parser.add_argument("--investor", default="all", choices=["all", "f", "d", "or"])
    parser.add_argument("--market", default="RG", choices=["ALL", "RG", "NG"])
    args = parser.parse_args()

    api_key = os.environ.get("INDEXALPHA_API_KEY", "").strip()
    if not api_key:
        print("[!] INDEXALPHA_API_KEY belum di-set di env/.env", file=sys.stderr)
        sys.exit(1)

    symbols_raw = args.symbols or os.environ.get("INDEXALPHA_SYMBOLS", "")
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
    if not symbols:
        print("[!] Tidak ada simbol (kasih --symbols atau set INDEXALPHA_SYMBOLS di .env)", file=sys.stderr)
        sys.exit(1)

    date_str = args.date or date.today().isoformat()

    print(f"[*] Fetch broker summary {len(symbols)} simbol, tanggal {date_str}, "
          f"investor={args.investor}, market={args.market}")
    print(f"[i] Tiap simbol = 1 quota IndexAlpha (batch cuma hemat HTTP round-trip, bukan quota)")

    total_rows = 0
    for chunk in chunked(symbols, BATCH_MAX_TICKERS):
        data = fetch_batch(api_key, chunk, date_str, args.investor, args.market)
        rows = to_rows(data, date_str, args.investor)
        insert_rows(rows)
        total_rows += len(rows)
        print(f"[i] chunk {len(chunk)} simbol -> {len(rows)} baris broker ter-insert")

    print(f"[*] Selesai: {total_rows} baris masuk ke {CH_DB}.broker_summary")


if __name__ == "__main__":
    main()
