# Setup Lokal

Panduan dari clone sampai rekonsiliasi pertama di laptop sendiri. Waktu yang dibutuhkan
sekitar 15 menit, sebagian besar untuk mengunduh image Docker.

## Yang perlu dipasang

| Alat | Versi | Cek dengan |
|---|---|---|
| Docker Desktop, atau Docker Engine + Compose v2 | terbaru | `docker compose version` |
| Python | 3.11 atau lebih baru | `python --version` |
| Git | apa saja | `git --version` |

RAM 8 GB cukup. Di Windows, aktifkan WSL 2 saat memasang Docker Desktop.

ETL hanya memakai pustaka standar Python. Untuk menjalankannya tidak perlu `pip install`.
Paket di `etl/requirements-dev.txt` hanya untuk test dan lint.

## Cara cepat: satu perintah

Di Linux, macOS, atau **Git Bash** di Windows:

```bash
git clone https://github.com/mfadlikurniawann-webdev/Pindah-ERP.git
cd Pindah-ERP
./scripts/setup.sh
```

Skrip itu menjalankan langkah 1 sampai 6 di bawah. Kalau berhasil, lanjut ke
[Migrasi data contoh](#migrasi-data-contoh).

## Cara manual, langkah demi langkah

Perintahnya sama di Bash dan PowerShell, kecuali yang ditandai.

### 1. Siapkan berkas rahasia

```bash
cp .env.example .env
cp config/odoo.conf.example config/odoo.conf
```

Di PowerShell pakai `Copy-Item .env.example .env` dan
`Copy-Item config/odoo.conf.example config/odoo.conf`.

Buka `.env`, ganti `DB_PASSWORD`. Buka `config/odoo.conf`, ganti `admin_passwd`.
Kedua berkas ini ada di `.gitignore`, jadi tidak akan ikut ter-commit.

### 2. Nyalakan PostgreSQL dan buat database

```bash
docker compose up -d db
docker compose run --rm odoo odoo -d pindah -i base --stop-after-init
```

### 3. Atur perusahaan sebelum memasang akuntansi

```bash
docker compose run --rm odoo bash /mnt/scripts/run_in_shell.sh /mnt/scripts/setup_company.py
```

Urutan ini penting. Odoo memilih bagan akun saat modul Accounting dipasang, berdasarkan
negara perusahaan. Kalau negaranya sudah Indonesia, yang terpasang adalah `l10n_id`
dengan mata uang IDR.

### 4. Pasang modul

```bash
docker compose run --rm odoo odoo -d pindah -i jembatan_reconcile --stop-after-init
```

Perintah ini ikut memasang `jembatan_migration`, Accounting, Inventory, Manufacturing,
Sales, Purchase, dan `l10n_id_efaktur_coretax`.

### 5. Buat API key untuk ETL

```bash
docker compose run --rm -T odoo bash /mnt/scripts/run_in_shell.sh /mnt/scripts/create_api_key.py
```

Salin baris `ODOO_API_KEY=...` dari keluarannya ke `.env`. Kunci hanya tampil sekali dan
berlaku 90 hari. Cara lain lewat layar: avatar > Preferensi Saya > Keamanan Akun >
API Keys.

### 6. Nyalakan Odoo

```bash
docker compose up -d odoo
```

Buka http://localhost:8069, login `admin` / `admin`, lalu ganti password lewat
Preferensi Saya.

## Migrasi data contoh

```bash
cd etl
python -m pindah_etl transform
python -m pindah_etl load --dry-run
python -m pindah_etl load
python -m pindah_etl reconcile
```

Di Windows, bila `python` tidak dikenal, pakai `py`.

Hasil yang diharapkan:

| Langkah | Hasil |
|---|---|
| `transform` | fatal 0, ditolak 1, dibetulkan 3, info 2 |
| `load` | 9 entitas berstatus `done` |
| `reconcile` | `MATCH`, cocok 42, tidak cocok 0 |

Baris yang ditolak adalah pelanggan `C-0004` dengan NPWP salah ketik. Itu disengaja,
untuk menunjukkan cara ETL menangani data kotor. Rinciannya ada di
`etl/build/laporan_validasi.md`.

Sesudahnya buka menu **Migrasi** di Odoo: Ringkasan Migrasi, Batch Migrasi, dan
Rekonsiliasi (tombol Cetak PDF).

## Mencoba selisih

Untuk melihat rekonsiliasi menangkap kesalahan, ubah satu angka di Odoo, misalnya
batalkan satu faktur di jurnal Saldo Awal Piutang. Lalu jalankan ulang
`python -m pindah_etl reconcile`. Hasilnya `MISMATCH` beserta baris yang berbeda.

Untuk mengulang dari nol:

```bash
docker compose down -v      # -v menghapus volume database
./scripts/setup.sh
```

## Pengembangan

```bash
pip install -r etl/requirements-dev.txt pre-commit
pre-commit install
python -m pytest -q         # test ETL
make test-odoo              # test modul Odoo di database pindah_test
```

Sesudah mengubah kode modul, perbarui modulnya lalu restart:

```bash
docker compose run --rm odoo odoo -d pindah -u jembatan_migration,jembatan_reconcile --stop-after-init
docker compose restart odoo
```

## Masalah yang sering muncul

| Gejala | Penyebab dan jalan keluar |
|---|---|
| `Isi DB_PASSWORD di berkas .env` | Berkas `.env` belum dibuat. Ulangi langkah 1 |
| `Port 8069 is in use` | Ada Odoo lain berjalan. Matikan, atau ganti `ODOO_PORT` di `.env` dan `ODOO_URL` mengikutinya |
| ETL: `Tidak bisa menghubungi Odoo` | Kontainer `odoo` belum menyala. Cek `docker compose ps` |
| ETL: `401` atau `Invalid apikey` | API key salah atau kedaluwarsa. Ulangi langkah 5 |
| Bagan akun bukan Indonesia | Langkah 3 terlewat sebelum langkah 4. Ulangi dari nol |
| `image odoo:19.0 not found` atau tidak cocok arsitektur | Cek tag yang tersedia di Docker Hub, lalu sesuaikan `docker-compose.yml` |
