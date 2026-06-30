"""
Technical indicators — dihitung dari OHLCV dengan pandas/numpy.

Dikelompokkan: Trend, Momentum, Volatility, Volume.
Setiap fungsi menerima DataFrame (index = waktu, kolom: open/high/low/close/volume)
dan mengembalikan Series / dict of Series yang sejajar dengan index.

`compute_all(df, want)` merangkai semuanya jadi payload JSON-ready untuk frontend.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ── Helper konversi ───────────────────────────────────────────────────────────
def _series_to_records(s: pd.Series, times: list[int]) -> list[dict]:
    """Series → [{time, value}] dengan NaN dibuang. `times` = epoch detik sejajar index."""
    out = []
    vals = s.to_numpy()
    for t, v in zip(times, vals):
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            continue
        out.append({"time": int(t), "value": round(float(v), 4)})
    return out


def _wilder(s: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (RMA) = EMA dengan alpha = 1/period."""
    return s.ewm(alpha=1.0 / period, adjust=False).mean()


def _true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


# ══════════════════════════════════════════════════════════════════════════════
# TREND
# ══════════════════════════════════════════════════════════════════════════════
def sma(df, period):
    return df["close"].rolling(window=period, min_periods=period).mean()


def ema(df, period):
    return df["close"].ewm(span=period, adjust=False).mean()


def macd(df, fast=12, slow=26, signal=9):
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "hist": hist}


def adx(df, period=14):
    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    atr = _wilder(_true_range(df), period)
    plus_di = 100 * _wilder(plus_dm, period) / atr
    minus_di = 100 * _wilder(minus_dm, period) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = _wilder(dx, period)
    return {"adx": adx_line, "plus_di": plus_di, "minus_di": minus_di}


def parabolic_sar(df, step=0.02, max_step=0.2):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    n = len(df)
    sar = np.full(n, np.nan)
    if n < 2:
        return pd.Series(sar, index=df.index)

    # Inisialisasi: asumsi uptrend di awal
    trend_up = True
    af = step
    ep = high[0]              # extreme point
    sar[0] = low[0]

    for i in range(1, n):
        prev_sar = sar[i - 1]
        sar[i] = prev_sar + af * (ep - prev_sar)

        if trend_up:
            sar[i] = min(sar[i], low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
            if high[i] > ep:
                ep = high[i]
                af = min(af + step, max_step)
            if low[i] < sar[i]:          # reversal ke downtrend
                trend_up = False
                sar[i] = ep
                ep = low[i]
                af = step
        else:
            sar[i] = max(sar[i], high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
            if low[i] < ep:
                ep = low[i]
                af = min(af + step, max_step)
            if high[i] > sar[i]:         # reversal ke uptrend
                trend_up = True
                sar[i] = ep
                ep = high[i]
                af = step

    return pd.Series(sar, index=df.index)


# ══════════════════════════════════════════════════════════════════════════════
# MOMENTUM
# ══════════════════════════════════════════════════════════════════════════════
def rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _wilder(gain, period)
    avg_loss = _wilder(loss, period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stochastic(df, k_period=14, d_period=3, smooth=3):
    low_min = df["low"].rolling(k_period).min()
    high_max = df["high"].rolling(k_period).max()
    raw_k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    k = raw_k.rolling(smooth).mean()
    d = k.rolling(d_period).mean()
    return {"k": k, "d": d}


def williams_r(df, period=14):
    high_max = df["high"].rolling(period).max()
    low_min = df["low"].rolling(period).min()
    return -100 * (high_max - df["close"]) / (high_max - low_min).replace(0, np.nan)


def cci(df, period=20):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))


# ══════════════════════════════════════════════════════════════════════════════
# VOLATILITY
# ══════════════════════════════════════════════════════════════════════════════
def bollinger(df, period=20, mult=2.0):
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    return {"upper": mid + mult * std, "middle": mid, "lower": mid - mult * std}


def atr(df, period=14):
    return _wilder(_true_range(df), period)


def keltner(df, period=20, mult=2.0, atr_period=10):
    mid = df["close"].ewm(span=period, adjust=False).mean()
    a = atr(df, atr_period)
    return {"upper": mid + mult * a, "middle": mid, "lower": mid - mult * a}


# ══════════════════════════════════════════════════════════════════════════════
# VOLUME
# ══════════════════════════════════════════════════════════════════════════════
def vwap(df, intraday=True):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"]
    if intraday:
        # reset per hari kalender
        day = pd.Series(df.index, index=df.index).dt.normalize()
        grp = day.values
        cum_tpv = (tp * vol).groupby(grp).cumsum()
        cum_vol = vol.groupby(grp).cumsum()
    else:
        cum_tpv = (tp * vol).cumsum()
        cum_vol = vol.cumsum()
    return cum_tpv / cum_vol.replace(0, np.nan)


def obv(df):
    direction = np.sign(df["close"].diff().fillna(0))
    return (direction * df["volume"]).cumsum()


def ad_line(df):
    hl = (df["high"] - df["low"]).replace(0, np.nan)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl
    mfv = mfm.fillna(0) * df["volume"]
    return mfv.cumsum()


def volume_profile(df, bins=24):
    """Histogram volume per level harga. Return bins + POC (point of control)."""
    if df.empty:
        return {"levels": [], "poc": None}
    tp = (df["high"] + df["low"] + df["close"]) / 3
    lo, hi = float(tp.min()), float(tp.max())
    if hi <= lo:
        return {"levels": [], "poc": round(lo, 2)}
    edges = np.linspace(lo, hi, bins + 1)
    idx = np.clip(np.digitize(tp.to_numpy(), edges) - 1, 0, bins - 1)
    vol = df["volume"].to_numpy()
    hist = np.zeros(bins)
    for i, v in zip(idx, vol):
        hist[i] += v
    centers = (edges[:-1] + edges[1:]) / 2
    poc_i = int(np.argmax(hist))
    levels = [{"price": round(float(centers[i]), 2), "volume": round(float(hist[i]), 0)}
              for i in range(bins)]
    return {"levels": levels, "poc": round(float(centers[poc_i]), 2)}


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════════════
DEFAULT_INDICATORS = [
    "sma20", "sma50", "sma200", "ema20", "ema50",
    "bbands", "keltner", "vwap", "sar",
    "macd", "rsi", "stoch", "williams", "cci", "adx",
    "atr", "obv", "ad", "volprofile",
]


def compute_all(df: pd.DataFrame, want: list[str] | None = None, interval: str = "1d") -> dict:
    """Hitung indikator yang diminta. Return dict JSON-ready."""
    if want is None:
        want = DEFAULT_INDICATORS
    want = set(want)
    times = [int(ts.timestamp()) for ts in df.index]
    is_intraday = interval.endswith("m") or interval.endswith("h")
    R = lambda s: _series_to_records(s, times)
    out: dict = {}

    # Trend overlays
    if "sma20" in want:  out["sma20"] = R(sma(df, 20))
    if "sma50" in want:  out["sma50"] = R(sma(df, 50))
    if "sma200" in want: out["sma200"] = R(sma(df, 200))
    if "ema20" in want:  out["ema20"] = R(ema(df, 20))
    if "ema50" in want:  out["ema50"] = R(ema(df, 50))
    if "sar" in want:    out["sar"] = R(parabolic_sar(df))

    if "bbands" in want:
        bb = bollinger(df)
        out["bbands"] = {"upper": R(bb["upper"]), "middle": R(bb["middle"]), "lower": R(bb["lower"])}
    if "keltner" in want:
        kc = keltner(df)
        out["keltner"] = {"upper": R(kc["upper"]), "middle": R(kc["middle"]), "lower": R(kc["lower"])}
    if "vwap" in want:
        out["vwap"] = R(vwap(df, intraday=is_intraday))

    # Oscillators (sub-pane)
    if "macd" in want:
        m = macd(df)
        out["macd"] = {"macd": R(m["macd"]), "signal": R(m["signal"]), "hist": R(m["hist"])}
    if "rsi" in want:    out["rsi"] = R(rsi(df))
    if "stoch" in want:
        st = stochastic(df)
        out["stoch"] = {"k": R(st["k"]), "d": R(st["d"])}
    if "williams" in want: out["williams"] = R(williams_r(df))
    if "cci" in want:      out["cci"] = R(cci(df))
    if "adx" in want:
        a = adx(df)
        out["adx"] = {"adx": R(a["adx"]), "plus_di": R(a["plus_di"]), "minus_di": R(a["minus_di"])}
    if "atr" in want:      out["atr"] = R(atr(df))
    if "obv" in want:      out["obv"] = R(obv(df))
    if "ad" in want:       out["ad"] = R(ad_line(df))
    if "volprofile" in want:
        out["volprofile"] = volume_profile(df)

    return out


def latest_signals(df: pd.DataFrame, interval: str = "1d") -> dict:
    """Ringkasan sinyal terbaru untuk panel 'Technical Summary'."""
    if len(df) < 30:
        return {}
    close = float(df["close"].iloc[-1])
    rsi_v = rsi(df).iloc[-1]
    m = macd(df)
    macd_hist = m["hist"].iloc[-1]
    a = adx(df)
    adx_v = a["adx"].iloc[-1]
    plus_di = a["plus_di"].iloc[-1]
    minus_di = a["minus_di"].iloc[-1]
    sma20_v = sma(df, 20).iloc[-1]
    sma50_v = sma(df, 50).iloc[-1]
    sma200_v = sma(df, 200).iloc[-1] if len(df) >= 200 else None
    bb = bollinger(df)
    atr_v = atr(df).iloc[-1]

    def safe(x):
        return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 2)

    # Skoring sederhana: -100 (strong sell) .. +100 (strong buy)
    score = 0
    if not np.isnan(rsi_v):
        if rsi_v < 30: score += 20
        elif rsi_v > 70: score -= 20
    if not np.isnan(macd_hist):
        score += 15 if macd_hist > 0 else -15
    if not np.isnan(sma20_v):
        score += 15 if close > sma20_v else -15
    if not np.isnan(sma50_v):
        score += 10 if close > sma50_v else -10
    if sma200_v is not None and not np.isnan(sma200_v):
        score += 15 if close > sma200_v else -15
    if not np.isnan(adx_v) and not np.isnan(plus_di) and not np.isnan(minus_di):
        if adx_v > 25:
            score += 10 if plus_di > minus_di else -10
    score = max(-100, min(100, score))

    if score >= 50:    verdict = "STRONG BUY"
    elif score >= 20:  verdict = "BUY"
    elif score <= -50: verdict = "STRONG SELL"
    elif score <= -20: verdict = "SELL"
    else:              verdict = "NEUTRAL"

    return {
        "close": safe(close),
        "rsi": safe(rsi_v),
        "macd_hist": safe(macd_hist),
        "adx": safe(adx_v),
        "plus_di": safe(plus_di),
        "minus_di": safe(minus_di),
        "sma20": safe(sma20_v),
        "sma50": safe(sma50_v),
        "sma200": safe(sma200_v),
        "bb_upper": safe(bb["upper"].iloc[-1]),
        "bb_lower": safe(bb["lower"].iloc[-1]),
        "atr": safe(atr_v),
        "score": score,
        "verdict": verdict,
    }
