"""Universe IDX (auto-fetch) + mapping interval yFinance."""
import os
import csv
import io
import urllib.request

UNIVERSE_URL = os.environ.get(
    "UNIVERSE_URL",
    "https://raw.githubusercontent.com/wildangunawan/Dataset-Saham-IDX/master/List%20Emiten/all.csv",
)

# Fallback daftar likuid jika fetch gagal (subset blue-chip).
FALLBACK_STOCKS = [
    "BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ISAT", "EXCL", "ASII", "UNTR",
    "UNVR", "ICBP", "INDF", "MYOR", "AMRT", "MAPI", "KLBF", "SIDO", "GGRM",
    "HMSP", "ADRO", "PTBA", "ITMG", "MEDC", "ANTM", "INCO", "MDKA", "TINS",
    "SMGR", "INTP", "CPIN", "JPFA", "GOTO", "BUKA", "BRPT", "TPIA",
]

# Index IDX (yFinance symbol → kode internal)
IDX_INDICES = {"^JKSE": "IHSG"}

# interval → period history yang di-fetch dari yFinance
INTERVAL_PERIOD = {
    "1m": "5d", "5m": "7d", "15m": "15d", "30m": "1mo",
    "1h": "2mo", "1d": "1y", "1wk": "2y", "1mo": "max",
}


def fetch_universe() -> list[str]:
    """Ambil daftar kode emiten IDX dari sumber publik. Return list kode (tanpa .JK)."""
    try:
        req = urllib.request.Request(UNIVERSE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        codes = []
        for row in reader:
            code = (row.get("code") or "").strip().upper()
            if code and code.isalnum():
                codes.append(code)
        if codes:
            print(f"[+] Universe fetched: {len(codes)} emiten dari {UNIVERSE_URL}", flush=True)
            return codes
    except Exception as e:
        print(f"[!] Universe fetch gagal: {e} — pakai fallback", flush=True)
    print(f"[i] Fallback universe: {len(FALLBACK_STOCKS)} emiten", flush=True)
    return list(FALLBACK_STOCKS)


def yf_ticker(code: str) -> str:
    return code if code.startswith("^") else f"{code}.JK"
