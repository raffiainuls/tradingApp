"""AI Advisor (Tab 5) — analisa single-stock & rekomendasi harian via Hermes Agent.

Beda mekanisme dari Tab 3 AI Picks (batch, HTTP ke gateway LLM generik): di sini
SATU permintaan sekaligus (single-stock atau satu batch seleksi harian) via Hermes
CLI subprocess, dijembatani lewat hermes_bridge.py (lihat docs/hermes-integration.md).

Data teknikal 100% dari ClickHouse kita sendiri (backend/indicators.py) — BUKAN
yfinance/saham-mcp (real-time-nya 429 dari IP server ini; histori saham-mcp beku
sejak Feb 2025). Hermes dipanggil TANPA --skills supaya tidak diam-diam fetch data
sendiri lewat yfinance -- prompt sudah menyertakan semua angka yang perlu.

Rekomendasi harian: Hermes SENDIRI yang menyeleksi (genuinely AI-driven), BUKAN
cuma menulis komentar di atas daftar yang sudah kita filter -- supaya beda betulan
dari mekanisme AI Picks (Tab 3, sort-by-score). Dikirim POOL lebih luas (top skor,
verdict apa pun) + kriteria dari skill daily-stock-picks (Momentum Breakout/Oversold
Bounce/Trend Continuation), Hermes yang putuskan mana yang genuinely layak & kenapa.
Simbol pilihannya di-parse dari respons & divalidasi terhadap pool (anti halusinasi
ticker) -- tapi ANGKA yang ditampilkan tetap 100% dari sistem kita, bukan dari teks
yang ditulis Hermes.
"""
import re

import config
import db
import screener
import indicators as ind
from hermes_bridge import ask_hermes

_SYSTEM_PREAMBLE = (
    "Kamu adalah analis teknikal saham IDX (Bursa Efek Indonesia). JANGAN mencari "
    "atau fetch data apa pun dari internet/yfinance/tool lain -- gunakan HANYA data "
    "yang sudah dihitung sistem dan disertakan di bawah ini. Data berasal dari "
    "candle historis, BUKAN harga real-time (ada delay)."
)


def _atr_levels(close: float, atr: float | None) -> tuple[float, float, float]:
    """entry/target/cutloss deterministik dari ATR -- sengaja mirror rumus ai_picks._levels
    (target close+2xATR, cutloss close-1.5xATR) supaya konsisten di seluruh app."""
    a = atr if atr else close * 0.02
    return round(close, 2), round(close + 2 * a, 2), round(close - 1.5 * a, 2)


def _board_info(symbol: str) -> dict:
    info = db.board_map().get(symbol, {})
    return {"name": info.get("name"), "board": info.get("board") or None}


def analyze_symbol(symbol: str) -> dict:
    df = db.fetch_ohlcv(symbol, "1d", limit=400)
    if df.empty:
        return {"error": "no_data"}

    sig = ind.latest_signals(df, interval="1d")
    if not sig or sig.get("verdict") is None:
        return {"error": "insufficient_data"}

    data_as_of = str(df.index[-1].date())
    entry, target, cutloss = _atr_levels(sig["close"], sig.get("atr"))
    binfo = _board_info(symbol)

    prompt = (
        f"{_SYSTEM_PREAMBLE}\n\n"
        f"Saham: {symbol} ({binfo['name'] or '-'}, papan: {binfo['board'] or '-'})\n"
        f"Data per: {data_as_of}\n"
        f"Harga close: {sig['close']}\n"
        f"Skor komposit: {sig['score']} (verdict: {sig['verdict']})\n"
        f"RSI(14): {sig.get('rsi')}\n"
        f"MACD histogram: {sig.get('macd_hist')}\n"
        f"ADX(14): {sig.get('adx')} (+DI {sig.get('plus_di')} / -DI {sig.get('minus_di')})\n"
        f"SMA20: {sig.get('sma20')} | SMA50: {sig.get('sma50')} | SMA200: {sig.get('sma200')}\n"
        f"Bollinger Bands: upper {sig.get('bb_upper')} / lower {sig.get('bb_lower')}\n"
        f"ATR(14): {sig.get('atr')}\n\n"
        "Tugas: tulis analisa 3-5 kalimat gaya market commentary dalam Bahasa Indonesia. "
        "Sebutkan bias (bullish/bearish/netral) dan alasan utama dari data di atas. "
        "JANGAN menyebut harga target/entry/cutloss spesifik (sudah dihitung sistem "
        "terpisah). Akhiri dengan disclaimer singkat bahwa ini bukan saran investasi."
    )
    narrative = ask_hermes(prompt)

    return {
        "symbol": symbol,
        "name": binfo["name"],
        "board": binfo["board"],
        "data_as_of": data_as_of,
        "technical": {**sig, "entry_price": entry, "target_price": target, "cutloss_price": cutloss},
        "ai_narrative": narrative,
    }


def _candidate_pool(pool_size: int) -> list[dict]:
    """Pool kandidat LEBIH LUAS (skor tertinggi, verdict apa pun -- TIDAK pra-filter
    bullish) untuk dievaluasi ULANG oleh Hermes sendiri. Exclude papan Pemantauan
    Khusus (filter kualitas data, bukan filter seleksi -- itu tugas Hermes)."""
    rows = sorted(screener.compute_universe("1d"), key=lambda r: r["score"], reverse=True)
    board_map = db.board_map()
    out = []
    for r in rows:
        info = board_map.get(r["symbol"], {})
        board = info.get("board") or ""
        if "Khusus" in board:
            continue
        out.append({**r, "board": board or None, "name": info.get("name")})
        if len(out) >= pool_size:
            break
    return out


_PICK_LINE_RE = re.compile(r"PILIHAN\s*:\s*(.+)", re.IGNORECASE)


def _parse_picks(commentary: str | None, pool: list[dict], max_picks: int) -> list[dict]:
    """Ekstrak simbol dari baris 'PILIHAN: ...' yang diminta di prompt, validasi
    terhadap pool (cegah ticker halusinasi -- token yang tidak ada di pool dibuang
    diam-diam). Fallback ke top-N pool by score kalau parsing gagal/kosong, supaya
    UI tidak pernah blank walau format respons Hermes berubah-ubah."""
    pool_by_symbol = {c["symbol"]: c for c in pool}
    if commentary:
        m = _PICK_LINE_RE.search(commentary)
        if m:
            picked = []
            for tok in m.group(1).split(","):
                sym = re.sub(r"[^A-Z0-9]", "", tok.upper())
                c = pool_by_symbol.get(sym)
                if c and c not in picked:
                    picked.append(c)
            if picked:
                return picked[:max_picks]
    return pool[:max_picks]


def daily_recommendations(top_n: int | None = None) -> dict:
    n = top_n or config.AI_ADVISOR_DAILY_TOP_N
    pool = _candidate_pool(config.AI_ADVISOR_POOL_SIZE)
    data_as_of = db.latest_bar_date("1d")

    if not pool:
        return {"data_as_of": data_as_of, "candidates": [], "ai_commentary": None}

    listing = "\n".join(
        f"{i+1}. {c['symbol']} ({c.get('name') or '-'}) - close {c['close']}, "
        f"chg {c.get('change_pct')}%, skor sistem {c['score']} ({c['verdict']}), "
        f"RSI {c.get('rsi')}, MACD histogram {c.get('macd_hist')}, ADX {c.get('adx')}, "
        f"vs SMA20/50/200: {c.get('above_ma20')}/{c.get('above_ma50')}/{c.get('above_ma200')}, "
        f"vol ratio {c.get('vol_ratio')}x"
        for i, c in enumerate(pool)
    )
    prompt = (
        f"{_SYSTEM_PREAMBLE}\n\n"
        f"Data per: {data_as_of}\n"
        f"Berikut {len(pool)} saham IDX dengan data teknikal lengkap -- ini BUKAN "
        "daftar yang sudah difilter bullish, ada yang netral/lemah, KAMU yang menilai:\n\n"
        f"{listing}\n\n"
        "Tugas: evaluasi SETIAP saham di atas terhadap kriteria berikut:\n"
        "- Momentum Breakout: harga di atas SMA20, RSI 50-70, ADX>20, MACD histogram positif\n"
        "- Oversold Bounce: RSI<35, harga dekat SMA200 (support)\n"
        "- Trend Continuation: harga di atas SMA50 DAN SMA200, ADX>25\n\n"
        f"Pilih MAKSIMAL {n} saham dari daftar di atas yang PALING layak direkomendasikan "
        "hari ini (boleh lebih sedikit kalau memang tidak ada yang cukup layak -- JANGAN "
        "memaksakan pilihan). JANGAN pilih saham di luar daftar ini. Untuk tiap saham "
        "terpilih, beri 1-2 kalimat alasan berbasis kriteria di atas. Tutup dengan "
        "disclaimer singkat bahwa ini bukan saran investasi.\n\n"
        "PENTING -- setelah disclaimer, di baris PALING AKHIR tulis PERSIS format ini "
        "(simbol dipisah koma, tanpa tanda kurung/spasi ekstra, tanpa teks lain di baris "
        "itu, dan JANGAN menulis apa pun setelah baris ini):\n"
        "PILIHAN: SIMBOL1,SIMBOL2,SIMBOL3"
    )
    commentary = ask_hermes(prompt)
    candidates = _parse_picks(commentary, pool, n)

    # Hitung entry/target/cutloss per kandidat dan simpan batch ke DB
    for c in candidates:
        entry, target, cutloss = _atr_levels(c["close"], c.get("atr"))
        c.setdefault("entry_price", entry)
        c.setdefault("target_price", target)
        c.setdefault("cutloss_price", cutloss)
    try:
        db.save_ai_advisor_picks(candidates, commentary, data_as_of)
    except Exception as e:
        print(f"[!] save_ai_advisor_picks error: {e}", flush=True)

    return {"data_as_of": data_as_of, "candidates": candidates, "ai_commentary": commentary}
