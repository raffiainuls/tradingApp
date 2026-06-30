"""
FastAPI backend — Trading App.

- Tab 2 (market): symbols, history+indicators, quotes, WebSocket live.
- Tab 1 (journal): portfolio, transaksi, analitik.
- Kafka consumer thread mengonsumsi `ohlc-live` → push ke WS + update cache quote.
"""
import json
import time
import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

import config
import db
import realtime
from routers import market, journal, watchlist

LIVE_TOPIC = "ohlc-live"


def kafka_thread():
    while True:
        try:
            consumer = KafkaConsumer(
                LIVE_TOPIC,
                bootstrap_servers=config.KAFKA_BOOTSTRAP,
                auto_offset_reset="latest",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                fetch_min_bytes=1,
                fetch_max_wait_ms=100,
            )
            print("[+] Backend Kafka consumer connected", flush=True)
            for message in consumer:
                d = message.value
                sym = d.get("symbol")
                if not sym:
                    continue
                # cache quote terbaru (interval harian sebagai default tampilan)
                realtime.latest_quote[sym] = {
                    "symbol": sym,
                    "type": d.get("type", "stock"),
                    "sector": d.get("sector"),
                    "interval": d.get("interval"),
                    "close": d.get("close"),
                    "open": d.get("open"),
                    "high": d.get("high"),
                    "low": d.get("low"),
                    "volume": d.get("volume"),
                    "timestamp": d.get("timestamp"),
                }
                realtime.push_from_thread({"type": "bar", "data": d})
        except NoBrokersAvailable:
            print("[*] Waiting for Kafka in backend...", flush=True)
            time.sleep(5)
        except Exception as e:
            print(f"[!] Kafka consumer error: {e}", flush=True)
            time.sleep(5)


async def heartbeat_loop():
    while True:
        await asyncio.sleep(30)
        await realtime.broadcast({"type": "ping"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    realtime.main_loop = asyncio.get_event_loop()
    try:
        db.init_pg_pool()
        db.ensure_watchlist_table()
        print("[+] Postgres pool ready", flush=True)
    except Exception as e:
        print(f"[!] Postgres pool init failed: {e}", flush=True)
    threading.Thread(target=kafka_thread, daemon=True).start()
    asyncio.create_task(heartbeat_loop())
    yield


app = FastAPI(title="Trading App API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(market.router)
app.include_router(journal.router)
app.include_router(watchlist.router)


@app.get("/health")
def health():
    return {"status": "ok", "ws_clients": len(realtime.connected_ws)}
