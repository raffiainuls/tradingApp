# 🛠️ Troubleshooting — Data Tidak Tampil di Frontend

Panduan saat dashboard terbuka tapi **tidak ada data** (ticker "0 emiten", chart "Belum ada data",
tape "Memuat ticker…"), terutama setelah deploy di **server / VPS**.

---

## 🔎 Cara baca gejala dulu

| Yang kamu lihat | Artinya |
|---|---|
| Status **● LIVE** (hijau) | Browser **berhasil** konek ke backend (`ws://<host>:8000`). Port 8000 & backend OK. |
| Status **○ OFFLINE** (merah) | Browser **tidak** bisa menjangkau backend `:8000` (firewall/port/CORS). |
| **0 emiten** + chart kosong + LIVE | Backend OK, tapi **ClickHouse kosong** → pipeline data belum mengisi (biasanya poller/yFinance). |

> Pada kasus "LIVE tapi 0 emiten" → masalahnya **bukan** jaringan FE↔backend, melainkan **pipeline data** (Yahoo → TCP → Kafka → ClickHouse).

---

## 🩺 Diagnosa cepat (jalankan di SERVER, folder `tradingApp`)

```bash
# 1. Semua service jalan & healthy?
docker compose ps

# 2. ClickHouse sudah ada data?
docker compose exec clickhouse clickhouse-client --password tradingch123 \
  --query "SELECT count(), uniqExact(symbol) FROM market.ohlcv"

# 3. Poller — fetch yFinance berhasil atau error/0 bar? (PALING PENTING)
docker compose logs --tail=50 ingestion

# 4. Bridge & Writer — data mengalir ke Kafka & ClickHouse?
docker compose logs --tail=20 tcp-bridge
docker compose logs --tail=20 clickhouse-writer

# 5. Tes backend langsung di server
curl -s "http://localhost:8000/api/quotes?interval=1d" | head -c 200
curl -s "http://localhost:8000/health"

# 6. Cek outbound internet server ke Yahoo & GitHub
docker compose exec ingestion python -c "import urllib.request as u; print('yahoo', u.urlopen('https://query1.finance.yahoo.com',timeout=10).status)"
docker compose exec ingestion python -c "import urllib.request as u; print('github', u.urlopen('https://raw.githubusercontent.com',timeout=10).status)"
```

**Interpretasi:**
- `count()=0` di ClickHouse → pipeline belum mengisi (lanjut cek poller).
- Log ingestion `published 0 bars` berulang / `yf.download error` / HTTP 429 → **yFinance memblok/rate-limit IP server**.
- Log ingestion `Universe fetch gagal … pakai fallback` → server tak bisa akses GitHub (outbound terbatas).
- Step 6 error/timeout → **server tidak punya outbound internet** ke Yahoo/GitHub.

---

## ⛔ Penyebab #1 (paling sering di VPS): yFinance memblok IP datacenter

Yahoo Finance sering **rate-limit / blokir IP cloud (VPS/datacenter)**. Akibatnya `yf.download` balikkan
kosong/429 → poller publish 0 bar → ClickHouse kosong → FE tidak ada data. Di laptop lokal lancar karena
IP rumah/ISP tidak diblok.

**Solusi (pilih salah satu):**

1. **Fetch di mesin lokal, jalankan service lain di server.**
   Jalankan `ingestion` (poller) di mesin yang IP-nya tidak diblok (mis. laptop), arahkan TCP-nya ke
   `tcp-bridge` di server. Set `TCP_HOST` bridge ke host poller. (Pipeline memang sudah terpisah: poller = TCP server.)

2. **Pakai proxy keluar** untuk poller. Tambahkan env proxy di service `ingestion` (docker-compose):
   ```yaml
   ingestion:
     environment:
       HTTPS_PROXY: http://user:pass@proxyhost:port
       HTTP_PROXY:  http://user:pass@proxyhost:port
   ```
   (proxy residential/ber-IP bersih lebih aman dari blokir).

3. **Naikkan jeda & kecilkan beban** agar tidak gampang kena limit (kurangi risiko, bukan solusi total):
   `.env` → `POLL_INTERVAL=600`, `CHUNK_SIZE=30`, batasi `MAX_SYMBOLS=100`.

4. **Self-host sumber data lain** (mis. broker API) — di luar scope sekarang.

> Cek apakah benar terblok: lihat log ingestion. Kalau backfill jalan lalu setelah beberapa chunk
> mulai `0 bars`/429 → itu rate-limit. Kalau dari awal 0 semua → blok total / no internet.

---

## Penyebab lain & fix

### A. Service tidak healthy
`docker compose ps` ada yang `Exit`/`unhealthy`:
```bash
docker compose logs <service>
docker compose up -d --build <service>
```
- **clickhouse unhealthy / "disabling network access"** → pastikan `CLICKHOUSE_PASSWORD` ter-set di service `clickhouse` (`.env`).
- ClickHouse butuh ~30s start (sudah ada `start_period`).

### B. Frontend OFFLINE (browser tak bisa ke backend :8000)
FE menurunkan alamat backend dari `window.location.hostname:8000`. Jadi **port 8000 WAJIB terbuka**
untuk browser, sama seperti 3001.
- **Buka port di firewall / Security Group cloud**: izinkan inbound **3001** (frontend) DAN **8000** (backend).
  - Contoh ufw: `sudo ufw allow 3001 && sudo ufw allow 8000`
  - Cloud (AWS/GCP/Azure/Alibaba): tambah rule inbound 3001 & 8000 di Security Group.
- Tes dari browser: buka `http://<host>:8000/health` → harus `{"status":"ok"}`.

### C. Backfill masih berjalan (baru start)
Backfill awal ~949 emiten butuh beberapa menit. Tunggu, lalu:
```bash
docker compose exec clickhouse clickhouse-client --password tradingch123 --query "SELECT count() FROM market.ohlcv"
```
angka harus naik. Kalau diam di 0 → balik ke Penyebab #1.

### D. Tampilan stale / cache browser
Hard refresh `Ctrl+Shift+R` atau Incognito (dokumen HTML sudah `no-store`).

---

## ✅ Checklist deploy server

- [ ] Port **3001** dan **8000** dibuka di firewall / security group
- [ ] `.env` ada (copy dari `.env.example`), `CLICKHOUSE_PASSWORD` terisi
- [ ] `docker compose up -d --build` → semua service healthy (`docker compose ps`)
- [ ] Server punya outbound internet ke Yahoo & GitHub (step 6) — atau pakai opsi proxy/fetch-lokal
- [ ] `SELECT count() FROM market.ohlcv` > 0 setelah beberapa menit
- [ ] Buka `http://<host>:8000/health` dari browser → ok
- [ ] Buka `http://<host>:3001/analyst`, hard refresh

---

## Ringkas

> **LIVE + 0 emiten = backend OK, ClickHouse kosong.** 90% kasus di VPS = **yFinance keblokir IP server**.
> Pastikan dulu via `docker compose logs ingestion`. Kalau benar keblokir → jalankan poller dari IP bersih
> (laptop/proxy) sambil service lain tetap di server.
