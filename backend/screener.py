"""
Screener / scoring engine — skor komposit teknikal untuk SELURUH universe.

Strategi efisien: 1 query ClickHouse ambil N bar terakhir SEMUA symbol,
lalu hitung indikator per-symbol di pandas (groupby). Hasil di-cache (TTL).
"""
import time
import pandas as pd
import numpy as np

import db
import indicators as ind

_CACHE: dict = {}        # interval -> (monotonic_ts, results)
_TTL = 300               # detik
_PER_SYMBOL = 260        # cukup utk SMA200 + indikator


def _score_group(sym: str, g: pd.DataFrame, interval: str) -> dict | None:
    if len(g) < 30:
        return None
    sig = ind.latest_signals(g, interval=interval)
    if not sig or sig.get("verdict") is None:
        return None

    close = float(g["close"].iloc[-1])
    open_ = float(g["open"].iloc[-1])
    vol = float(g["volume"].iloc[-1] or 0)
    vol_avg = float(g["volume"].tail(20).mean() or 0)
    vol_ratio = (vol / vol_avg) if vol_avg else 0.0
    change_pct = ((close - open_) / open_ * 100) if open_ else 0.0

    sma200 = sig.get("sma200")
    dist_ma200 = ((close - sma200) / sma200 * 100) if sma200 else None

    return {
        "symbol": sym,
        "score": sig["score"],
        "verdict": sig["verdict"],
        "close": round(close, 2),
        "change_pct": round(change_pct, 2),
        "rsi": sig.get("rsi"),
        "macd_hist": sig.get("macd_hist"),
        "adx": sig.get("adx"),
        "sma20": sig.get("sma20"),
        "sma50": sig.get("sma50"),
        "sma200": sma200,
        "above_ma20": (sig.get("sma20") is not None and close > sig["sma20"]),
        "above_ma50": (sig.get("sma50") is not None and close > sig["sma50"]),
        "above_ma200": (sma200 is not None and close > sma200),
        "dist_ma200_pct": round(dist_ma200, 2) if dist_ma200 is not None else None,
        "vol_ratio": round(vol_ratio, 2),
        "volume": vol,
        "atr": sig.get("atr"),
    }


def compute_universe(interval: str) -> list[dict]:
    """Hitung skor untuk semua symbol pada interval (cached)."""
    now = time.monotonic()
    cached = _CACHE.get(interval)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    df = db.fetch_all_ohlcv(interval, per_symbol_limit=_PER_SYMBOL)
    results = []
    if not df.empty:
        for sym, g in df.groupby("symbol", sort=False):
            try:
                r = _score_group(sym, g, interval)
                if r:
                    results.append(r)
            except Exception:
                continue
    results.sort(key=lambda x: x["score"], reverse=True)
    _CACHE[interval] = (now, results)
    return results


def screen(interval: str, filters: dict) -> list[dict]:
    """Terapkan filter ke hasil skoring + enrich dgn board/sektor."""
    rows = compute_universe(interval)
    board_map = db.board_map()

    out = []
    for r in rows:
        info = board_map.get(r["symbol"], {})
        board = info.get("board")
        r = {**r, "board": board, "name": info.get("name")}

        # ── filters ──
        f = filters
        if f.get("min_score") is not None and r["score"] < f["min_score"]:
            continue
        if f.get("max_score") is not None and r["score"] > f["max_score"]:
            continue
        if f.get("min_price") is not None and r["close"] < f["min_price"]:
            continue
        if f.get("max_price") is not None and r["close"] > f["max_price"]:
            continue
        if f.get("min_vol_ratio") is not None and r["vol_ratio"] < f["min_vol_ratio"]:
            continue
        if f.get("rsi_below") is not None and (r["rsi"] is None or r["rsi"] > f["rsi_below"]):
            continue
        if f.get("rsi_above") is not None and (r["rsi"] is None or r["rsi"] < f["rsi_above"]):
            continue
        if f.get("above_ma200") and not r["above_ma200"]:
            continue
        if f.get("verdict") and r["verdict"] != f["verdict"]:
            continue
        if f.get("exclude_special") and board and ("Pemantauan Khusus" in board or "Khusus" in board):
            continue
        out.append(r)

    limit = filters.get("limit") or 50
    return out[:limit]
