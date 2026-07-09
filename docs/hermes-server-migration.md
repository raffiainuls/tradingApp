# Migrasi App ke Laptop, Hermes Tetap di Server — Rencana Integrasi (2026-07-04)

> Status: **perubahan sisi kode repo SUDAH diimplementasi (2026-07-09, dikerjakan di laptop)**.
> Sisa pekerjaan: langkah operasional di server VPS (Tailscale/API key/jalankan bridge) dan
> pengisian `.env` di laptop — lihat checklist di bawah. Ditulis dari diskusi soal mengatasi
> 429 Yahoo Finance dengan memindahkan app ke IP residential, sementara Hermes Agent tetap
> di server VPS.

## Konteks & Tujuan

IP server ini (`43.134.129.64`, AS132203 Tencent Cloud Singapore) berulang kali kena rate-limit/
block dari berbagai layanan (Yahoo Finance 429, `jsr.io` 403, `idx.co.id` Cloudflare challenge —
lihat `docs/enhancement.md` & memori proyek). Root cause: IP datacenter punya reputasi buruk di
sistem anti-bot berbasis ASN, beda dengan IP residential yang jauh lebih dipercaya.

**Rencana:** pindahkan **seluruh app** (Docker Compose stack: frontend, backend, ClickHouse,
Kafka, Postgres, ingestion, dst) ke **laptop pribadi** (IP residential) — supaya pipeline
`ingestion/poller.py` (yFinance) tidak kena 429 lagi. **Hermes Agent (`bro_analysis`) tetap di
server VPS ini** — tidak ikut pindah.

Ini membalik topologi integrasi Tab 5 (AI Advisor) yang sudah dibangun: sebelumnya app dan
Hermes di mesin yang sama (beda container vs host), sekarang app dan Hermes di **mesin yang
benar-benar berbeda**, terhubung lewat jaringan (bukan cuma Docker↔host).

---

## Yang Sudah Benar dari Desain Sekarang (tidak perlu diubah besar)

Arsitektur `scripts/hermes_advisor_bridge.py` + `backend/hermes_bridge.py` sudah HTTP-based dari
awal — justru karena backend (Docker) & Hermes (host) sudah "terpisah" secara filesystem sejak
awal, jadi pola ini **sudah siap digeneralisasi** ke mesin yang benar-benar beda. Yang berubah
cuma **alamat tujuan**, bukan pola integrasinya:

```
Sekarang:      App (Docker, VPS ini)    → http://host.docker.internal:8090 → bridge (HOST, mesin sama)
Rencana baru:  App (Docker, LAPTOP)     → http://<IP/Tailscale VPS>:8090   → bridge (HOST VPS, mesin lain)
```

`ask_hermes()` di `hermes_bridge.py` sudah **NEVER raise** (fallback ke `None` kalau bridge tidak
terjangkau) — jadi kalau nanti koneksi laptop↔VPS putus-putus, AI Advisor tetap tampil data
teknikal, cuma narasi/seleksi AI-nya yang absen. Tidak perlu kode tambahan utk ini.

---

## Yang WAJIB Ditambahkan: Keamanan

Sekarang `hermes_advisor_bridge.py` **tanpa autentikasi sama sekali** — aman karena cuma bisa
diakses dari mesin yang sama (`host.docker.internal` tidak nyampe dari luar). Begitu port 8090
dibuka supaya laptop bisa akses dari jauh, **siapa pun yang tahu IP+port bisa nyuruh Hermes
jalanin prompt apa saja** (biaya token, potensi abuse). Ini jadi wajib, bukan opsional lagi.

### Opsi jaringan — Tailscale (rekomendasi)

Laptop akan pindah-pindah jaringan (rumah, kafe, hotspot HP) → IP publiknya berubah-ubah & biasa
di balik NAT (tidak bisa port-forward gampang). **Tailscale** pas untuk situasi ini:

- Kasih IP privat stabil (`100.x.x.x`) ke laptop & VPS, apa pun jaringan aslinya masing-masing.
- Enkripsi otomatis (WireGuard) — bridge HTTP polos tetap aman krn trafik tidak lewat internet
  publik sama sekali.
- Tidak perlu urus ulang firewall/port-forwarding tiap kali laptop ganti jaringan.

Alternatif tanpa Tailscale: buka port 8090 di security group Tencent Cloud VPS ini secara publik
+ WAJIB tambah API key (lihat bawah) + idealnya IP-allowlist juga (tapi laptop ber-IP dinamis
bikin ini merepotkan, kurang cocok tanpa Tailscale/VPN sejenis).

### Opsi aplikasi — API key di bridge

Terlepas dari pakai Tailscale atau tidak, tambahkan lapisan auth di level aplikasi (defense in
depth):

- `scripts/hermes_advisor_bridge.py`: cek header `Authorization: Bearer <key>` di `/advise`,
  tolak (401) kalau tidak cocok dengan env var `HERMES_BRIDGE_API_KEY` yang di-set di server VPS.
- `backend/hermes_bridge.py::ask_hermes()`: kirim header itu di setiap request, key-nya dari
  `config.HERMES_BRIDGE_API_KEY` (env var baru di `.env` laptop, sama isinya dgn punya server).
- `GET /health` boleh tetap tanpa auth (endpoint informatif doang, bukan yang mahal/berisiko).

---

## Checklist Perubahan Konkret

**Di server VPS ini (tempat Hermes & bridge tetap jalan):**
- [ ] Install & konfigurasi Tailscale (atau siapkan API key + buka port 8090 di security group
      Tencent Cloud kalau skip Tailscale).
- [ ] Set env var `HERMES_BRIDGE_API_KEY` sebelum jalankan `hermes_advisor_bridge.py`.
- [ ] Jalankan bridge dgn `--host 0.0.0.0` (sudah default) supaya listen ke semua interface,
      termasuk Tailscale interface.

**Di kode repo (SELESAI 2026-07-09):**
- [x] Tambah pengecekan `Authorization: Bearer <key>` di `scripts/hermes_advisor_bridge.py`
      (`/advise` saja; `/health` tetap tanpa auth; `hmac.compare_digest`; env
      `HERMES_BRIDGE_API_KEY` kosong = auth nonaktif → backward-compatible topologi lama,
      dengan warning saat startup).
- [x] Tambah `HERMES_BRIDGE_API_KEY` ke `backend/config.py`, dikirim di header oleh
      `backend/hermes_bridge.py` (header hanya dikirim bila key non-kosong).
- [x] Update `.env.example` dgn `HERMES_BRIDGE_API_KEY=` + dokumentasi dua topologi.
- [x] `docker-compose.yml`: `extra_hosts` DIBIARKAN (tidak mengganggu; masih dipakai bila
      suatu saat balik ke topologi satu-mesin), komentarnya diperjelas.

**Di laptop:**
- [x] Clone repo (sudah ada di `d:\project\tradingApp`); `.env` lama dilengkapi section
      AI Picks/LLM + AI Advisor (2026-07-09).
- [ ] Isi `HERMES_BRIDGE_URL` di `.env` = `http://<IP Tailscale atau publik VPS>:8090`
      (sekarang sengaja dikosongkan → Tab 5 jalan tanpa narasi AI sampai diisi).
- [ ] Isi `HERMES_BRIDGE_API_KEY` di `.env` = sama dgn yang di-set di server VPS.
- [ ] `docker compose up -d --build` seperti biasa.

---

## Efek Samping yang Perlu Diantisipasi (di luar soal Hermes)

- **Akses dashboard app ikut pindah** — `frontend`/`backend` yang sekarang bisa diakses dari IP
  VPS (`43.134.129.64:3001`) nanti cuma bisa diakses dari laptop (atau via Tailscale juga kalau
  mau akses dari HP/device lain — makin satu alasan lagi buat pakai Tailscale sekalian).
- **Laptop harus nyala terus** kalau mau pipeline data (`ingestion`) jalan kontinu — beda dari
  VPS yang always-on. Laptop tertutup/sleep/mati = data berhenti masuk (mirip downtime, tapi
  bukan krn di-block — cuma krn mesinnya mati).
- **Resource laptop** — seluruh stack (Kafka + ClickHouse + Postgres + semua service) lumayan
  berat kalau laptop juga dipakai buat kerja lain bersamaan. Belum diukur kebutuhan RAM/CPU
  pasti di proyek ini.

---

## Kenapa Ini BUKAN Sekadar "Ganti URL" — Ringkasan

| Aspek | Sekarang (1 server) | Rencana (2 mesin) |
|---|---|---|
| Alamat bridge | `host.docker.internal:8090` | IP Tailscale/publik VPS |
| Autentikasi bridge | Tidak ada (aman krn lokal) | **Wajib** (API key minimal) |
| Enkripsi transit | Tidak perlu (lokal) | Perlu (Tailscale otomatis, atau TLS manual) |
| `extra_hosts` di compose | Perlu | Tidak perlu lagi |
| Graceful degradation kalau Hermes tak terjangkau | Sudah ada, tidak berubah | Sudah ada, tidak berubah |
| Akses dashboard | Dari IP VPS | Dari laptop (+ Tailscale kalau mau remote) |

Inti pesan: **pola integrasi (HTTP bridge) sudah benar dari awal**, migrasinya kebanyakan soal
jaringan & keamanan, bukan redesign arsitektur.
