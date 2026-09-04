"""Broker Summary per-saham (IndexAlpha, pihak ketiga berbayar) -- Tab 5 AI Advisor.

IDX resmi cuma punya broker summary AGREGAT market-wide (lihat gotcha CLAUDE.md),
BUKAN breakdown per-saham per-broker. IndexAlpha (api.indexalpha.id) satu-satunya
sumber tervalidasi utk ini. Quota terbatas & berbayar -> SELALU cek cache ClickHouse
dulu (gratis, diisi sync hari sebelumnya), baru fetch live (1 quota) kalau memang
belum ada utk symbol+date ini -- klik ulang di hari yang sama TIDAK makan quota lagi.

Framework interpretasi (akumulasi/distribusi ala Dow Theory) diadaptasi dari skill
Hermes stock-technical-fundamental-analysis/references/broker-summary.md -- tapi
angka top buy/sell/net dihitung DETERMINISTIK di sini, Hermes cuma diminta menulis
narasi interpretasinya (pola sama seperti ai_advisor.py -- AI tidak boleh mengarang
angka).
"""
from datetime import date

import httpx

import config
import db
from hermes_bridge import ask_hermes

TOP_N = 5


def _fetch_live(symbol: str, date_str: str, investor: str = "all") -> list[dict] | None:
    """Panggil IndexAlpha (1 quota). Return None kalau gagal/quota habis -- NEVER raise."""
    try:
        resp = httpx.post(
            f"{config.INDEXALPHA_BASE_URL}/stocks/broker-summary/batch",
            json={"tickers": [symbol], "from": date_str, "to": date_str, "investor": investor},
            headers={"Authorization": f"Bearer {config.INDEXALPHA_API_KEY}"},
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            print(f"[!] IndexAlpha balas success=false: {body.get('error')}", flush=True)
            return None
        rows = (body.get("data") or {}).get(symbol, [])
        return [{
            "broker_code": r.get("code", ""),
            "buy_freq": r.get("buy_freq", 0) or 0, "buy_volume": r.get("buy_volume", 0) or 0,
            "buy_value": r.get("buy_value", 0) or 0,
            "sell_freq": r.get("sell_freq", 0) or 0, "sell_volume": r.get("sell_volume", 0) or 0,
            "sell_value": r.get("sell_value", 0) or 0,
            "buy_avg": r.get("buy_avg", 0) or 0, "sell_avg": r.get("sell_avg", 0) or 0,
        } for r in rows]
    except Exception as e:
        print(f"[!] IndexAlpha call gagal: {e}", flush=True)
        return None


def get_broker_summary(symbol: str, date_str: str, investor: str = "all") -> dict:
    """Cache-first: ClickHouse dulu (gratis), fetch live (1 quota) cuma kalau belum
    ada. Return {"rows", "source": 'cache'|'live'|None, "error": str|None}."""
    cached = db.fetch_broker_summary(symbol, date_str, investor)
    if cached:
        return {"rows": cached, "source": "cache", "error": None}

    if not config.INDEXALPHA_API_KEY:
        return {"rows": [], "source": None, "error": "belum_dikonfigurasi"}

    live = _fetch_live(symbol, date_str, investor)
    if live is None:
        return {"rows": [], "source": None, "error": "indexalpha_gagal_atau_quota_habis"}
    if live:
        db.insert_broker_summary(symbol, date_str, investor, live)
    return {"rows": live, "source": "live", "error": None}


def _net(r: dict) -> float:
    return r["buy_value"] - r["sell_value"]


def _summarize(rows: list[dict]) -> dict:
    top_buy = sorted((r for r in rows if _net(r) > 0), key=_net, reverse=True)[:TOP_N]
    top_sell = sorted((r for r in rows if _net(r) < 0), key=_net)[:TOP_N]
    total_buy = sum(r["buy_value"] for r in rows)
    total_sell = sum(r["sell_value"] for r in rows)
    return {
        "top_buy": top_buy, "top_sell": top_sell,
        "total_buy_value": total_buy, "total_sell_value": total_sell,
        "net_value": total_buy - total_sell,
    }


_PREAMBLE = (
    "Kamu adalah analis broker summary saham IDX (Bursa Efek Indonesia). JANGAN "
    "fetch data apa pun dari internet/tool lain -- gunakan HANYA data broker yang "
    "sudah dihitung sistem di bawah ini."
)


def analyze(symbol: str, date_str: str | None = None) -> dict:
    date_str = date_str or date.today().isoformat()
    result = get_broker_summary(symbol, date_str)
    if result["error"]:
        return {"error": result["error"]}
    rows = result["rows"]
    if not rows:
        return {"error": "no_data"}

    s = _summarize(rows)
    buy_lines = "\n".join(
        f"- {r['broker_code']}: net buy Rp {_net(r):,.0f} "
        f"(vol {r['buy_volume']:,.0f} lembar, avg {r['buy_avg']:,.0f})"
        for r in s["top_buy"]
    ) or "(tidak ada broker net-buy signifikan)"
    sell_lines = "\n".join(
        f"- {r['broker_code']}: net sell Rp {abs(_net(r)):,.0f} "
        f"(vol {r['sell_volume']:,.0f} lembar, avg {r['sell_avg']:,.0f})"
        for r in s["top_sell"]
    ) or "(tidak ada broker net-sell signifikan)"

    prompt = (
        f"{_PREAMBLE}\n\n"
        f"Saham: {symbol}, tanggal: {date_str}\n"
        f"Total broker aktif: {len(rows)}\n"
        f"Net value keseluruhan pasar: Rp {s['net_value']:,.0f} "
        f"({'net buy' if s['net_value'] >= 0 else 'net sell'})\n\n"
        f"Top {TOP_N} broker NET BUY:\n{buy_lines}\n\n"
        f"Top {TOP_N} broker NET SELL:\n{sell_lines}\n\n"
        "Tugas: interpretasikan pola ini pakai framework akumulasi/distribusi Dow "
        "Theory (fase Akumulasi = smart money net-buy diam-diam saat harga "
        "sideways/turun; fase Distribusi = smart money net-sell saat harga naik/"
        "euforia). Kalau kamu kenali broker net-buy/net-sell teratas, sebutkan "
        "apakah tergolong institusional atau retail-heavy. Tulis 3-5 kalimat "
        "Bahasa Indonesia, akhiri disclaimer singkat bahwa ini bukan saran investasi."
    )
    narrative = ask_hermes(prompt)

    return {
        "symbol": symbol, "date": date_str,
        "broker_count": len(rows), "source": result["source"],
        "top_buy": s["top_buy"], "top_sell": s["top_sell"],
        "total_buy_value": s["total_buy_value"], "total_sell_value": s["total_sell_value"],
        "net_value": s["net_value"],
        "ai_narrative": narrative,
    }
