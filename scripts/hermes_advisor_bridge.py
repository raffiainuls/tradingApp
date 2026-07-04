#!/usr/bin/env python3
"""
Hermes Advisor Bridge — jembatan HTTP kecil (zero-dependency) supaya backend
Trading App (di dalam Docker) bisa minta narasi dari Hermes Agent (`bro_analysis`,
di HOST, luar Docker) tanpa saling mount filesystem/binary antar container & host.

Jalan di HOST (bukan di dalam Docker), karena `bro_analysis` cuma ada di PATH host.

Usage:
    python3 scripts/hermes_advisor_bridge.py              # port 8090 default
    python3 scripts/hermes_advisor_bridge.py --port 9090

Endpoints:
    GET  /health          Health check
    POST /advise           {"prompt": "..."} -> {"text": "..."} atau {"error": "..."}

Catatan penting: prompt yang dikirim ke sini SENGAJA tidak memuat --skills Hermes
(stock-technical-fundamental-analysis / daily-stock-picks) karena skill itu akan
membuat Hermes coba fetch data sendiri lewat yfinance -- yang di server ini sering
kena rate-limit 429. Data teknikal HARUS sudah dihitung & disertakan di dalam prompt
oleh backend (dari ClickHouse), Hermes di sini HANYA dipakai untuk menulis narasinya.
"""
import json
import re
import subprocess
import sys
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler

HERMES_BIN = "bro_analysis"
DEFAULT_TIMEOUT = 150  # detik; longgar krn ada overhead init agent + LLM call

_BOX_RE = re.compile(r"^╭[^\n]*\n(.*?)\n╰", re.DOTALL | re.MULTILINE)


def _extract_reply(stdout: str) -> str | None:
    """Hermes CLI bungkus jawaban dalam box unicode (╭─...─╮ / ╰─...─╯), tiap
    baris di-indent 4 spasi. Ekstrak isinya, buang bungkus & footer sesi."""
    m = _BOX_RE.search(stdout)
    if not m:
        return None
    lines = [ln[4:] if ln.startswith("    ") else ln.lstrip() for ln in m.group(1).split("\n")]
    text = "\n".join(lines).strip()
    return text or None


def ask_hermes(prompt: str, timeout: int) -> tuple[str | None, str | None]:
    """Return (text, error). NEVER raise -- caller (bridge handler) selalu dapat jawaban terstruktur."""
    try:
        r = subprocess.run(
            [HERMES_BIN, "chat", "-q", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return None, f"'{HERMES_BIN}' tidak ditemukan di PATH host"
    except subprocess.TimeoutExpired:
        return None, f"timeout setelah {timeout}s"
    except Exception as e:
        return None, str(e)

    if r.returncode != 0:
        return None, f"exit code {r.returncode}: {(r.stderr or '').strip()[:300]}"
    text = _extract_reply(r.stdout)
    if text is None:
        return None, "gagal parse output Hermes (format tidak dikenali)"
    return text, None


class BridgeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            return self._json({"status": "ok", "server": "Hermes Advisor Bridge"})
        self._json({"error": "Not found. Try GET /health or POST /advise"}, 404)

    def do_POST(self):
        if self.path.rstrip("/") != "/advise":
            return self._json({"error": "Not found. Try POST /advise"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"error": "invalid JSON body"}, 400)

        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            return self._json({"error": "field 'prompt' wajib diisi"}, 400)
        timeout = int(body.get("timeout") or DEFAULT_TIMEOUT)

        text, error = ask_hermes(prompt, timeout)
        if error:
            return self._json({"error": error}, 502)
        self._json({"text": text})

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[hermes-bridge] {self.client_address[0]} - {args[0]} {args[1]}\n")


def main():
    ap = argparse.ArgumentParser(description="Hermes Advisor Bridge")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    srv = HTTPServer((args.host, args.port), BridgeHandler)
    print(f"🚀 Hermes Advisor Bridge @ http://{args.host}:{args.port}", flush=True)
    print(f"   GET  /health", flush=True)
    print(f"   POST /advise   body: {{\"prompt\": \"...\"}}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Stopped.", flush=True)
        srv.server_close()


if __name__ == "__main__":
    main()
