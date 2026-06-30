"""Koneksi ClickHouse (OHLCV) + PostgreSQL (journal)."""
import threading
import pandas as pd
import clickhouse_connect
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

import config

# ── ClickHouse ────────────────────────────────────────────────────────────────
# clickhouse-connect Client TIDAK thread-safe. FastAPI menjalankan endpoint sync
# di threadpool → request paralel. Pakai client per-thread (thread-local).
_local = threading.local()


def ch():
    c = getattr(_local, "client", None)
    if c is None:
        c = clickhouse_connect.get_client(
            host=config.CH_HOST, port=config.CH_PORT,
            username=config.CH_USER, password=config.CH_PASS, database=config.CH_DB,
        )
        _local.client = c
    return c


def fetch_ohlcv(symbol: str, interval: str, limit: int = 400) -> pd.DataFrame:
    """Ambil OHLCV terbaru dari ClickHouse → DataFrame (index waktu UTC)."""
    sql = """
        SELECT ts, open, high, low, close, volume FROM (
            SELECT ts, open, high, low, close, volume
            FROM market.ohlcv FINAL
            WHERE symbol = {sym:String} AND interval = {iv:String}
            ORDER BY ts DESC
            LIMIT {lim:UInt32}
        ) ORDER BY ts ASC
    """
    try:
        df = ch().query_df(sql, parameters={"sym": symbol, "iv": interval, "lim": limit})
    except Exception as e:
        print(f"[!] ClickHouse query error: {e}", flush=True)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["close"])


def fetch_all_ohlcv(interval: str, per_symbol_limit: int = 260) -> pd.DataFrame:
    """N bar terakhir SEMUA symbol (1 query) → DataFrame utk screener."""
    sql = """
        SELECT symbol, ts, open, high, low, close, volume FROM (
            SELECT symbol, ts, open, high, low, close, volume,
                   row_number() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM market.ohlcv
            WHERE interval = {iv:String}
        ) WHERE rn <= {lim:UInt32}
        ORDER BY symbol, ts ASC
    """
    try:
        df = ch().query_df(sql, parameters={"iv": interval, "lim": per_symbol_limit})
    except Exception as e:
        print(f"[!] fetch_all_ohlcv error: {e}", flush=True)
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# board/name map dari universe CSV (best-effort, fetch sekali)
_board_map: dict | None = None


def board_map() -> dict:
    global _board_map
    if _board_map is not None:
        return _board_map
    import urllib.request, csv, io
    try:
        req = urllib.request.Request(config.UNIVERSE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        m = {}
        for row in csv.DictReader(io.StringIO(text)):
            code = (row.get("code") or "").strip().upper()
            if code:
                m[code] = {"name": (row.get("name") or "").strip(),
                           "board": (row.get("listingBoard") or "").strip()}
        _board_map = m
        print(f"[+] Board map: {len(m)} emiten", flush=True)
    except Exception as e:
        print(f"[!] board_map fetch gagal: {e}", flush=True)
        _board_map = {}
    return _board_map


def ensure_watchlist_table():
    """Buat tabel watchlist bila belum ada (idempoten, utk volume Postgres lama)."""
    with pg_cursor(commit=True) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id          SERIAL PRIMARY KEY,
                symbol      VARCHAR(20) NOT NULL,
                note        TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def list_symbols() -> list[dict]:
    """Semua symbol yang punya data di ClickHouse."""
    try:
        rows = ch().query(
            "SELECT symbol, any(type) AS type, any(sector) AS sector "
            "FROM market.ohlcv GROUP BY symbol ORDER BY symbol"
        ).result_rows
        return [{"symbol": r[0], "type": r[1], "sector": r[2] or None} for r in rows]
    except Exception as e:
        print(f"[!] list_symbols error: {e}", flush=True)
        return []


def fetch_quotes(interval: str) -> list[dict]:
    """Quote ringkas untuk SEMUA symbol — agregasi argMax (ringan, tanpa FINAL).
    change = perubahan sesi (open→close) bar terakhir."""
    sql = """
        SELECT symbol,
               any(sector) AS sector, any(type) AS type,
               argMax(open, ts)   AS o,
               argMax(high, ts)   AS h,
               argMax(low, ts)    AS l,
               argMax(close, ts)  AS c,
               argMax(volume, ts) AS v
        FROM market.ohlcv
        WHERE interval = {iv:String}
        GROUP BY symbol
        ORDER BY symbol
    """
    try:
        rows = ch().query(sql, parameters={"iv": interval}).result_rows
    except Exception as e:
        print(f"[!] fetch_quotes error: {e}", flush=True)
        return []

    out = []
    for sym, sector, typ, o, h, l, c, v in rows:
        o = float(o); c = float(c)
        change = c - o
        pct = (change / o * 100) if o else 0.0
        out.append({
            "symbol": sym, "sector": sector or None, "type": typ,
            "price": round(c, 2), "open": round(o, 2),
            "high": round(float(h), 2), "low": round(float(l), 2),
            "volume": float(v), "change": round(change, 2),
            "change_pct": round(pct, 2),
        })
    return out


# ── PostgreSQL ────────────────────────────────────────────────────────────────
_pool: ThreadedConnectionPool | None = None


def init_pg_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=1, maxconn=10,
            host=config.PG_HOST, port=config.PG_PORT,
            user=config.PG_USER, password=config.PG_PASS, dbname=config.PG_DB,
        )
    return _pool


@contextmanager
def pg_cursor(commit: bool = False):
    pool = init_pg_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
