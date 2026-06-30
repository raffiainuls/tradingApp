"""
yFinance poller → TCP server (pipe-delimited bars).

Alur: Yahoo Finance → (poller ini, TCP server) → tcp-bridge → Kafka → ClickHouse.

- Auto-fetch universe (~900+ emiten IDX) saat startup.
- Fetch OHLCV per interval secara chunked (hindari rate-limit yFinance).
- Stream bar via TCP ke client yang terkoneksi (tcp-bridge), format pipe-delimited:
    B|code|type|sector|interval|epoch|open|high|low|close|volume\n
- Dedup via last_ts agar pass berikutnya hanya kirim bar baru.
- Re-backfill penuh berkala / saat client baru connect (self-heal; idempoten di ClickHouse).
"""
import os
import socket
import threading
import time
import math

import pandas as pd
import yfinance as yf

from config import fetch_universe, IDX_INDICES, INTERVAL_PERIOD, yf_ticker

TCP_PORT        = int(os.environ.get("TCP_PORT", "9009"))
POLL_INTERVAL   = int(os.environ.get("POLL_INTERVAL", "300"))
CHUNK_SIZE      = int(os.environ.get("CHUNK_SIZE", "60"))
REBACKFILL_HOURS = float(os.environ.get("REBACKFILL_HOURS", "6"))
MAX_SYMBOLS     = int(os.environ.get("MAX_SYMBOLS", "0"))  # 0 = semua
CHART_INTERVALS = [s.strip() for s in os.environ.get("CHART_INTERVALS", "5m,15m,1h,1d,1wk").split(",") if s.strip()]

clients = []
clients_lock = threading.Lock()
force_full = threading.Event()
force_full.set()                      # pass pertama = full backfill
last_ts: dict = {}                    # (code, interval) -> max epoch terkirim


def build_instruments():
    """Return list (yf_ticker, code, type, sector)."""
    codes = fetch_universe()
    if MAX_SYMBOLS > 0:
        codes = codes[:MAX_SYMBOLS]
    insts = [(yf_ticker(c), c, "stock", "") for c in codes]
    for yfsym, code in IDX_INDICES.items():
        insts.append((yfsym, code, "index", ""))
    return insts


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def broadcast(line: str):
    """Kirim satu baris ke semua client TCP. TCP backpressure = flow control alami."""
    raw = (line + "\n").encode("utf-8")
    with clients_lock:
        dead = []
        for c in clients:
            try:
                c.sendall(raw)
            except Exception:
                dead.append(c)
        for c in dead:
            try: c.close()
            except Exception: pass
            clients.remove(c)


def _clean(v):
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def stream_chunk(instruments_chunk, interval, full):
    """Download 1 chunk untuk 1 interval, broadcast bar (baru / semua jika full)."""
    by_ticker = {yfsym: (code, ctype, sector) for yfsym, code, ctype, sector in instruments_chunk}
    tickers = list(by_ticker.keys())
    period = INTERVAL_PERIOD.get(interval, "1mo")

    try:
        data = yf.download(tickers=" ".join(tickers), period=period, interval=interval,
                           group_by="ticker", auto_adjust=False, progress=False, threads=True)
    except Exception as e:
        print(f"[!] yf.download error ({interval}, {len(tickers)} tk): {e}", flush=True)
        return 0
    if data is None or data.empty:
        return 0

    sent = 0
    for yfsym, (code, ctype, sector) in by_ticker.items():
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if yfsym not in data.columns.get_level_values(0):
                    continue
                df = data[yfsym].dropna(how="all")
            else:
                df = data.dropna(how="all")
        except Exception:
            continue

        key = (code, interval)
        prev_max = None if full else last_ts.get(key)
        new_max = last_ts.get(key)

        for ts, row in df.iterrows():
            epoch = int(ts.timestamp())
            if prev_max is not None and epoch <= prev_max:
                continue
            o, h, l, c = _clean(row.get("Open")), _clean(row.get("High")), _clean(row.get("Low")), _clean(row.get("Close"))
            v = _clean(row.get("Volume")) or 0.0
            if c is None or o is None:
                continue
            broadcast(f"B|{code}|{ctype}|{sector}|{interval}|{epoch}|{o}|{h}|{l}|{c}|{v}")
            sent += 1
            if new_max is None or epoch > new_max:
                new_max = epoch
        if new_max is not None:
            last_ts[key] = new_max
    return sent


def run_pass(instruments, full):
    total = 0
    for interval in CHART_INTERVALS:
        for chunk in chunked(instruments, CHUNK_SIZE):
            total += stream_chunk(chunk, interval, full)
        print(f"[i] interval={interval} {'FULL' if full else 'inc'} streamed (cum {total})", flush=True)
    return total


def wait_for_client():
    while True:
        with clients_lock:
            if clients:
                return
        time.sleep(1)


def fetch_loop(instruments):
    last_full = 0.0
    while True:
        wait_for_client()
        full = force_full.is_set()
        if full:
            force_full.clear()
            last_ts.clear()
            print("[*] FULL backfill pass...", flush=True)
        total = run_pass(instruments, full)
        if full:
            last_full = time.monotonic()
        print(f"[i] pass selesai: {total} bar terkirim, {len(clients)} client", flush=True)

        if time.monotonic() - last_full > REBACKFILL_HOURS * 3600:
            force_full.set()
        time.sleep(POLL_INTERVAL)


def handle_client(conn, addr):
    # Handshake: bedakan bridge asli dari healthcheck Docker (yg connect lalu
    # langsung close tanpa kirim apa-apa). Tanpa ini, tiap healthcheck memicu
    # re-backfill terus-menerus.
    try:
        conn.settimeout(5)
        hello = conn.recv(64)
        if not hello or b"HELLO" not in hello:
            conn.close()
            return
        conn.settimeout(None)
    except Exception:
        try: conn.close()
        except Exception: pass
        return

    print(f"[+] Bridge connected: {addr}", flush=True)
    with clients_lock:
        clients.append(conn)
    force_full.set()    # bridge baru → re-backfill (self-heal)
    try:
        while True:
            if not conn.recv(1024):
                break
    except Exception:
        pass
    finally:
        with clients_lock:
            if conn in clients:
                clients.remove(conn)
        try: conn.close()
        except Exception: pass
        print(f"[-] Bridge disconnected: {addr}", flush=True)


def main():
    instruments = build_instruments()
    print(f"[*] Poller: {len(instruments)} instrumen, intervals={CHART_INTERVALS}, "
          f"chunk={CHUNK_SIZE}, poll={POLL_INTERVAL}s", flush=True)

    threading.Thread(target=fetch_loop, args=(instruments,), daemon=True).start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", TCP_PORT))
    srv.listen(8)
    print(f"[*] TCP server listening on 0.0.0.0:{TCP_PORT}", flush=True)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
