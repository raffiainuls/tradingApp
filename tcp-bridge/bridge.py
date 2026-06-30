"""
TCP → Kafka bridge.

Konek ke poller (ingestion:9009), baca stream baris pipe-delimited,
produce tiap baris ke Kafka topic `raw-ohlcv`. Auto-reconnect.
"""
import os
import socket
import time

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

TCP_HOST = os.environ.get("TCP_HOST", "ingestion")
TCP_PORT = int(os.environ.get("TCP_PORT", "9009"))
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
RAW_TOPIC = "raw-ohlcv"


def make_producer() -> KafkaProducer:
    while True:
        try:
            p = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda m: m.encode("utf-8"),
                linger_ms=100,
                batch_size=64 * 1024,
                retries=5,
            )
            print("[+] Kafka producer connected", flush=True)
            return p
        except NoBrokersAvailable:
            print("[*] Waiting for Kafka...", flush=True)
            time.sleep(5)


def stream(producer):
    print(f"[*] Connecting TCP {TCP_HOST}:{TCP_PORT} ...", flush=True)
    sock = socket.create_connection((TCP_HOST, TCP_PORT), timeout=30)
    sock.sendall(b"HELLO\n")   # handshake → poller tahu ini bridge asli, bukan healthcheck
    sock.settimeout(None)
    print("[+] TCP connected, forwarding to Kafka...", flush=True)
    buf = b""
    count = 0
    while True:
        data = sock.recv(65536)
        if not data:
            raise ConnectionError("TCP closed by poller")
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            producer.send(RAW_TOPIC, value=line.decode("utf-8", errors="ignore"))
            count += 1
            if count % 2000 == 0:
                producer.flush()
                print(f"[i] forwarded {count} bars", flush=True)


def main():
    producer = make_producer()
    while True:
        try:
            stream(producer)
        except Exception as e:
            print(f"[!] TCP error: {e} — reconnect in 5s", flush=True)
            try: producer.flush()
            except Exception: pass
            time.sleep(5)


if __name__ == "__main__":
    main()
