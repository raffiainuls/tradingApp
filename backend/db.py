"""Koneksi ClickHouse (OHLCV) + PostgreSQL (journal)."""
import threading
from datetime import date as _date
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


def latest_bar_date(interval: str) -> str | None:
    """Tanggal bar terbaru di seluruh universe (transparansi freshness utk AI Advisor)."""
    try:
        rows = ch().query(
            "SELECT max(ts) FROM market.ohlcv WHERE interval = {iv:String}",
            parameters={"iv": interval},
        ).result_rows
        ts = rows[0][0] if rows else None
        return str(ts.date()) if ts else None
    except Exception as e:
        print(f"[!] latest_bar_date error: {e}", flush=True)
        return None


def fetch_broker_summary(symbol: str, date_str: str, investor: str = "all") -> list[dict]:
    """Baca cache broker_summary dari ClickHouse (isi oleh sync IndexAlpha, lihat
    broker_summary.py). Return [] kalau belum pernah di-sync utk symbol+date ini
    -- caller yang putuskan mau fetch live (konsumsi quota) atau tidak."""
    sql = """
        SELECT broker_code, buy_freq, buy_volume, buy_value,
               sell_freq, sell_volume, sell_value, buy_avg, sell_avg
        FROM market.broker_summary FINAL
        WHERE symbol = {sym:String} AND date = {d:Date} AND investor = {inv:String}
        ORDER BY (buy_value - sell_value) DESC
    """
    try:
        rows = ch().query(sql, parameters={"sym": symbol, "d": date_str, "inv": investor}).result_rows
    except Exception as e:
        print(f"[!] fetch_broker_summary error: {e}", flush=True)
        return []
    cols = ["broker_code", "buy_freq", "buy_volume", "buy_value",
            "sell_freq", "sell_volume", "sell_value", "buy_avg", "sell_avg"]
    return [dict(zip(cols, r)) for r in rows]


def insert_broker_summary(symbol: str, date_str: str, investor: str, rows: list[dict]):
    if not rows:
        return
    cols = ["symbol", "date", "investor", "broker_code", "buy_freq", "buy_volume",
            "buy_value", "sell_freq", "sell_volume", "sell_value", "buy_avg", "sell_avg"]
    d = _date.fromisoformat(date_str)
    data = [[symbol, d, investor, r.get("broker_code", ""),
              r.get("buy_freq", 0) or 0, r.get("buy_volume", 0) or 0, r.get("buy_value", 0) or 0,
              r.get("sell_freq", 0) or 0, r.get("sell_volume", 0) or 0, r.get("sell_value", 0) or 0,
              r.get("buy_avg", 0) or 0, r.get("sell_avg", 0) or 0]
             for r in rows]
    ch().insert("broker_summary", data, column_names=cols, database=config.CH_DB)


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


def ensure_ai_picks_table():
    """Buat tabel ai_picks bila belum ada (idempoten, utk volume Postgres lama)."""
    with pg_cursor(commit=True) as cur:
        cur.execute("""
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
                tp1           NUMERIC(14,2),
                tp2           NUMERIC(14,2),
                tp3           NUMERIC(14,2),
                reasoning     TEXT,
                batch_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_picks_batch_at ON ai_picks(batch_at)")
        # Migrasi: tambah kolom tp1/tp2/tp3 ke tabel yang sudah ada
        for col, typ in [("tp1", "NUMERIC(14,2)"), ("tp2", "NUMERIC(14,2)"), ("tp3", "NUMERIC(14,2)")]:
            cur.execute(f"""
                ALTER TABLE ai_picks ADD COLUMN IF NOT EXISTS {col} {typ}
            """)


def ensure_ai_advisor_picks_table():
    """Tabel persistensi hasil daily_recommendations() AI Advisor (Tab 5)."""
    with pg_cursor(commit=True) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_advisor_daily_picks (
                id            SERIAL PRIMARY KEY,
                symbol        VARCHAR(20)   NOT NULL,
                name          VARCHAR(100),
                board         VARCHAR(50),
                verdict       VARCHAR(20),
                score         INTEGER,
                close_price   NUMERIC(14,2),
                entry_price   NUMERIC(14,2),
                target_price  NUMERIC(14,2),
                cutloss_price NUMERIC(14,2),
                rsi           NUMERIC(6,2),
                macd_hist     NUMERIC(12,4),
                adx           NUMERIC(6,2),
                atr           NUMERIC(12,4),
                data_as_of    DATE,
                ai_commentary TEXT,
                status        VARCHAR(30),
                pnl_pct       NUMERIC(8,4),
                batch_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_adv_picks_batch_at ON ai_advisor_daily_picks(batch_at)"
        )


def save_ai_advisor_picks(
    candidates: list[dict],
    commentary: str | None,
    data_as_of: str | None,
    batch_at=None,
):
    """Simpan satu batch hasil AI Advisor daily picks ke DB."""
    if not candidates:
        return
    import datetime as _dt
    batch_at_val = batch_at or _dt.datetime.now(_dt.timezone.utc)
    with pg_cursor(commit=True) as cur:
        for c in candidates:
            cur.execute("""
                INSERT INTO ai_advisor_daily_picks
                    (symbol, name, board, verdict, score,
                     close_price, entry_price, target_price, cutloss_price,
                     rsi, macd_hist, adx, atr, data_as_of, ai_commentary, status, pnl_pct, batch_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                c.get("symbol"), c.get("name"), c.get("board"),
                c.get("verdict"), c.get("score"),
                c.get("close"), c.get("entry_price"), c.get("target_price"), c.get("cutloss_price"),
                c.get("rsi"), c.get("macd_hist"), c.get("adx"), c.get("atr"),
                data_as_of, commentary, c.get("status"), c.get("pnl_pct"), batch_at_val,
            ))


def get_ai_advisor_history() -> list[dict]:
    """Semua batch AI Advisor daily picks, dikelompok per batch_at.

    Untuk setiap simbol yang belum punya pnl_pct tersimpan, lookup harga
    terkini dari ClickHouse (ohlcv + ohlcv_idx_official) untuk menghitung
    current_close dan P&L secara real-time — sama seperti AI Picks Tab 3.
    """
    with pg_cursor() as cur:
        cur.execute("""
            SELECT id, symbol, name, board, verdict, score,
                   close_price, entry_price, target_price, cutloss_price,
                   rsi, macd_hist, adx, atr, data_as_of, ai_commentary,
                   status, pnl_pct, batch_at
            FROM ai_advisor_daily_picks
            ORDER BY batch_at DESC, score DESC NULLS LAST
        """)
        rows = cur.fetchall()

    if not rows:
        return []

    # Lookup current_close dari ClickHouse untuk semua simbol sekaligus
    symbols = list({r["symbol"] for r in rows})
    current_prices: dict[str, float] = {}
    try:
        ch_client = ch()
        # Coba ohlcv (yFinance, lebih real-time) dulu
        yf_rows = ch_client.query(
            "SELECT symbol, argMax(close, ts) AS cur FROM market.ohlcv "
            "WHERE interval = '1d' AND symbol IN %(s)s GROUP BY symbol",
            parameters={"s": symbols},
        ).named_results()
        current_prices = {r["symbol"]: float(r["cur"]) for r in yf_rows if r.get("cur")}

        # Tambah dari ohlcv_idx_official untuk simbol yang belum ada
        missing = [s for s in symbols if s not in current_prices]
        if missing:
            idx_rows = ch_client.query(
                "SELECT symbol, argMax(close, date) AS cur FROM market.ohlcv_idx_official "
                "WHERE symbol IN %(s)s GROUP BY symbol",
                parameters={"s": missing},
            ).named_results()
            for r in idx_rows:
                if r.get("cur"):
                    current_prices[r["symbol"]] = float(r["cur"])
    except Exception as e:
        print(f"[!] get_ai_advisor_history CH lookup error: {e}", flush=True)

    batches: dict = {}
    for r in rows:
        key = r["batch_at"].isoformat()
        entry = float(r["entry_price"]) if r["entry_price"] else None
        target = float(r["target_price"]) if r["target_price"] else None
        cutloss = float(r["cutloss_price"]) if r["cutloss_price"] else None
        stored_pnl = float(r["pnl_pct"]) if r["pnl_pct"] is not None else None
        stored_status = r["status"]
        current_close = current_prices.get(r["symbol"])

        # Hitung P&L real-time hanya untuk picks baru (belum ada pnl_pct tersimpan)
        if stored_pnl is None and entry and current_close:
            pnl_pct = round((current_close - entry) / entry * 100, 2)
        else:
            pnl_pct = stored_pnl

        # Tentukan status real-time kalau belum ada status tersimpan
        if stored_status is None and entry and cutloss and current_close:
            if current_close <= cutloss:
                stored_status = "CUT LOSS"
            elif target and current_close >= target:
                stored_status = "HIT TP1"
            else:
                stored_status = "STILL OPEN"

        batches.setdefault(key, {
            "batch_at": key,
            "data_as_of": str(r["data_as_of"]) if r["data_as_of"] else None,
            "ai_commentary": r["ai_commentary"],
            "picks": [],
        })["picks"].append({
            "id": r["id"],
            "symbol": r["symbol"],
            "name": r["name"],
            "board": r["board"],
            "verdict": r["verdict"],
            "score": r["score"],
            "close_price": float(r["close_price"]) if r["close_price"] else None,
            "entry_price": entry,
            "target_price": target,
            "cutloss_price": cutloss,
            "rsi": float(r["rsi"]) if r["rsi"] else None,
            "atr": float(r["atr"]) if r["atr"] else None,
            "status": stored_status,
            "pnl_pct": pnl_pct,
            "current_close": current_close,
        })
    return list(batches.values())


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
