"""AI Picks (Tab 3) — orkestrasi top-N bullish + reasoning LLM (batch, HTTP).

Mirip gaya screener.py. State generasi disimpan sebagai module-level global (pola
realtime.py — connected_ws/latest_quote); aman karena backend jalan 1 worker uvicorn.

Beda mekanisme dari Tab 5 AI Advisor (single-stock, Hermes CLI subprocess) — di sini
batch banyak saham via HTTP OpenAI-compatible (llm_client.call_llm).
Level entry/target/cutloss dihitung deterministik dari ATR, BUKAN dari LLM.
"""
import threading
import time
from datetime import datetime, timezone

import config
import db
import screener
from llm_client import call_llm

_lock = threading.Lock()
_generating = False
_last_generated_at: float | None = None


def is_generating() -> bool:
    return _generating


def last_generated_at() -> float | None:
    return _last_generated_at


def _pick_candidates(top_n: int) -> list[dict]:
    """Top-N bullish (BUY/STRONG BUY) by score desc, exclude papan Pemantauan Khusus."""
    rows = screener.compute_universe("1d")
    board_map = db.board_map()
    bullish = sorted(
        [r for r in rows if r["verdict"] in ("BUY", "STRONG BUY")],
        key=lambda r: r["score"], reverse=True,
    )
    out = []
    for r in bullish:
        info = board_map.get(r["symbol"], {})
        board = info.get("board") or ""
        if "Khusus" in board:
            continue
        out.append({**r, "board": board, "sector": r.get("sector") or info.get("sector")})
        if len(out) >= top_n:
            break
    return out


def _build_prompt(c: dict) -> str:
    return (
        f"Analisa saham {c['symbol']} (papan: {c.get('board') or '-'}). "
        f"Data teknikal: skor komposit {c['score']} (verdict {c['verdict']}), "
        f"RSI {c.get('rsi')}, MACD histogram {c.get('macd_hist')}, ADX {c.get('adx')}, "
        f"harga close {c['close']}. Beri reasoning singkat 2-3 kalimat dalam Bahasa "
        "Indonesia mengapa saham ini layak masuk watchlist hari ini, tanpa menyebut "
        "harga target/entry/cutloss spesifik (sudah dihitung sistem secara terpisah)."
    )


def _levels(close: float, atr: float | None) -> tuple[float, float, float, float, float]:
    """Return (entry, tp1, tp2, tp3, cutloss). ATR fallback = 2% close."""
    a = atr if atr else close * 0.02
    entry = round(close, 2)
    return entry, round(entry + a, 2), round(entry + 2 * a, 2), round(entry + 3 * a, 2), round(entry - 1.5 * a, 2)


def generate(top_n: int | None = None):
    """Jalan via BackgroundTasks. Lock cegah generate paralel (TTL-check vs tombol manual)."""
    global _generating, _last_generated_at
    if not _lock.acquire(blocking=False):
        return
    _generating = True
    try:
        n = top_n or config.AI_PICKS_TOP_N
        candidates = _pick_candidates(n)
        batch_at = datetime.now(timezone.utc)
        saved = 0
        for c in candidates:
            try:
                reasoning = call_llm(_build_prompt(c))
            except Exception as llm_err:
                # LLM gagal untuk satu stock: skip, jangan batalkan seluruh batch
                print(f"[!] LLM gagal untuk {c['symbol']}: {llm_err}", flush=True)
                reasoning = None
            levels = compute_area_levels(
                c["close"], c.get("atr"),
                swing_low=c.get("swing_low"),
                swing_high=c.get("swing_high"),
                bb_lower=c.get("bb_lower"),
                bb_upper=c.get("bb_upper"),
            )
            row = (
                c["symbol"], c.get("sector"), c["verdict"], c["score"],
                c.get("rsi"), c.get("macd_hist"), c.get("adx"), c.get("atr"),
                c["close"],
                levels["entry_price"], levels["target_price"], levels["cutloss_price"],
                levels["buy_area_low"], levels["buy_area_high"],
                levels["tp1"], levels["tp2"], levels["tp3"],
                levels["cutloss_area_low"], levels["cutloss_area_high"],
                levels["entry_status"],
                reasoning, batch_at,
            )
            # Simpan per-pick langsung supaya partial batch tetap tersimpan walau LLM gagal di tengah
            with db.pg_cursor(commit=True) as cur:
                cur.execute("""INSERT INTO ai_picks
                    (symbol, sector, verdict, score, rsi, macd_hist, adx, atr,
                     close_price, entry_price, target_price, cutloss_price,
                     buy_area_low, buy_area_high,
                     tp1, tp2, tp3,
                     cutloss_area_low, cutloss_area_high,
                     entry_status, reasoning, batch_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", row)
            saved += 1
        _last_generated_at = time.time()
        print(f"[+] AI Picks batch generated: {saved}/{len(candidates)} symbols", flush=True)
    except Exception as e:
        print(f"[!] AI Picks generation failed: {e}", flush=True)
    finally:
        _generating = False
        _lock.release()


def latest_batch() -> list[dict]:
    with db.pg_cursor() as cur:
        cur.execute("""SELECT * FROM ai_picks
                        WHERE batch_at = (SELECT max(batch_at) FROM ai_picks)
                        ORDER BY score DESC""")
        return cur.fetchall()


def history_batches() -> list[dict]:
    """Semua batch historis dengan P/L aktual dari ClickHouse.

    Untuk tiap pick: query CH untuk max(high), min(low), current close sejak batch_at.
    Status & pnl_pct dihitung di sini supaya frontend cukup render.
    """
    with db.pg_cursor() as cur:
        cur.execute("""
            SELECT id, symbol, sector, verdict, score, atr,
                   close_price, entry_price, target_price, cutloss_price,
                   tp1, tp2, tp3, reasoning, batch_at
            FROM ai_picks
            ORDER BY batch_at DESC, score DESC
        """)
        picks = cur.fetchall()

    if not picks:
        return []

    # Kumpulkan simbol unik → satu query ClickHouse per simbol
    symbols = list({p["symbol"] for p in picks})
    ch_client = db.ch()

    # max_high, min_low, current_close per simbol sejak awal data 1d
    try:
        agg_rows = ch_client.query(
            "SELECT symbol, max(high) AS max_high, min(low) AS min_low, argMax(close, ts) AS current_close "
            "FROM market.ohlcv WHERE interval = '1d' AND symbol IN %(syms)s "
            "GROUP BY symbol",
            parameters={"syms": symbols},
        ).named_results()
        agg = {r["symbol"]: r for r in agg_rows}
    except Exception as e:
        print(f"[!] history_batches CH query error: {e}", flush=True)
        agg = {}

    batches: dict[str, list[dict]] = {}
    for p in picks:
        sym = p["symbol"]
        ch = agg.get(sym, {})
        entry = float(p["entry_price"])
        cutloss = float(p["cutloss_price"])
        tp1 = float(p["tp1"]) if p["tp1"] else float(p["target_price"])
        tp2 = float(p["tp2"]) if p["tp2"] else float(p["target_price"])
        tp3 = float(p["tp3"]) if p["tp3"] else float(p["target_price"])
        max_high = float(ch["max_high"]) if ch.get("max_high") else None
        min_low = float(ch["min_low"]) if ch.get("min_low") else None
        current_close = float(ch["current_close"]) if ch.get("current_close") else None

        # Tentukan status & pnl_pct
        if min_low is not None and min_low <= cutloss:
            status = "CUT_LOSS"
            pnl_pct = round((cutloss - entry) / entry * 100, 2)
        elif max_high is not None and max_high >= tp3:
            status = "HIT_TP3"
            pnl_pct = round((max_high - entry) / entry * 100, 2)
        elif max_high is not None and max_high >= tp2:
            status = "HIT_TP2"
            pnl_pct = round((max_high - entry) / entry * 100, 2)
        elif max_high is not None and max_high >= tp1:
            status = "HIT_TP1"
            pnl_pct = round((max_high - entry) / entry * 100, 2)
        else:
            status = "STILL_OPEN"
            pnl_pct = round((current_close - entry) / entry * 100, 2) if current_close else None

        pick_dict = {
            "id": p["id"],
            "symbol": sym,
            "sector": p["sector"],
            "verdict": p["verdict"],
            "score": p["score"],
            "atr": float(p["atr"]) if p["atr"] else None,
            "close_price": float(p["close_price"]),
            "entry_price": entry,
            "target_price": float(p["target_price"]),
            "cutloss_price": cutloss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "reasoning": p["reasoning"],
            "batch_at": p["batch_at"].isoformat(),
            "max_high": max_high,
            "min_low": min_low,
            "current_close": current_close,
            "status": status,
            "pnl_pct": pnl_pct,
        }
        key = p["batch_at"].isoformat()
        batches.setdefault(key, []).append(pick_dict)

    return [{"batch_at": k, "picks": v} for k, v in batches.items()]
