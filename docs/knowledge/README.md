# Pindah-ERP

Alat dan aturan untuk memindahkan data Accurate ke Odoo 19 sampai angkanya terbukti
sama. Baca berkas ini dulu sebelum membuka `domain/`.

## Apa aplikasinya

Perusahaan yang pindah dari Accurate butuh saldo awal yang benar di Odoo. Tanpa itu,
neraca pertama di Odoo tidak bisa dipercaya dan Finance kembali ke Excel.

Pemakainya dua. Developer menjalankan ETL dan memperbaiki galat. Finance memeriksa
laporan validasi dan menandatangani hasil rekonsiliasi.

Yang dipindahkan: daftar akun, kontak, gudang, produk, BoM, saldo akun, faktur yang
belum lunas, dan stok per gudang, semuanya per tanggal cutoff. Yang tidak dipindahkan:
riwayat transaksi sebelum cutoff. Riwayat tetap dibaca di Accurate.

## Daftar isi

| Berkas | Isinya | Status |
|---|---|---|
| `domain/migrasi.md` | Cara data masuk: urutan, jejak sumber, ulang, uji coba | `selesai` |
| `domain/kontak.md` | Pelanggan dan pemasok, NPWP, status PKP | `selesai` |
| `domain/saldo-awal.md` | Jurnal saldo awal dan faktur terbuka | `selesai` |
| `domain/stok-awal.md` | Kuantitas dan nilai persediaan awal | `selesai` |
| `domain/rekonsiliasi.md` | Bukti angka Accurate sama dengan Odoo | `selesai` |

## Pola pikir

Yang mahal dibalik di sini adalah angka yang salah tapi terlihat benar.

- **Saldo awal salah.** Semua laporan sesudah go-live ikut salah, dan selisihnya baru
  ketahuan saat tutup buku. Karena itu angka yang tidak bisa dipercaya menghentikan
  pemuatan, bukan sekadar diberi peringatan.
- **Data ganda.** Faktur terbuka yang masuk dua kali membuat pelanggan ditagih dua
  kali. Karena itu setiap impor aman diulang.
- **NPWP salah.** e-Faktur ditolak Coretax, dan perbaikannya melibatkan pelanggan.
  Karena itu NPWP divalidasi sebelum masuk.

Kesalahan tampilan, nama kategori, atau urutan menu murah dibalik dan tidak diatur ketat.

## Segi fitur

| Segi | Artinya |
|---|---|
| Kebenaran | Angka di Odoo sama dengan sumber, dan itu bisa dibuktikan |
| Keamanan ulang | Menjalankan ulang tidak merusak atau menggandakan data |
| Kejelasan | Finance tahu baris mana yang bermasalah dan kenapa, tanpa membaca kode |
| Kepatuhan | Data pajak siap dipakai e-Faktur Coretax |

## Peran

| Peran | Yang ia lakukan |
|---|---|
| Developer | Menjalankan ETL, memperbaiki pemetaan di `config.toml`, membaca galat batch |
| Finance | Menetapkan cutoff, memperbaiki data di Accurate, memeriksa laporan validasi, menandatangani PDF rekonsiliasi |
| Pengelola Migrasi | Grup Odoo `jembatan_migration.group_migration_manager`. Boleh menjalankan impor dan rekonsiliasi |

## Istilah

| Istilah | Di kode | Arti |
|---|---|---|
| Cutoff | `cutoff_date` | Hari terakhir transaksi dicatat di Accurate |
| Batch | `jembatan.migration.batch` | Satu kali jalan impor untuk satu entitas |
| Jejak sumber | `ir.model.data`, modul `jembatan_src` | Pasangan kode Accurate dan record Odoo |
| Akun penampung | `suspense_account_code` | Lawan saldo awal, harus nol di akhir |
| Faktur terbuka | `opening_receivable`, `opening_payable` | Faktur Accurate yang belum lunas per cutoff |
| Snapshot sumber | `jembatan.source.balance` | Angka Accurate pembanding rekonsiliasi |
| Uji coba | `dry_run` | Impor dijalankan lalu dibatalkan |

## Konvensi API

- Entitas dimuat lewat `POST /json/2/jembatan.migration.batch/api_import` atau
  `api_import_many`, dengan argumen bernama dan API key di header `Authorization: bearer`.
- Bentuk baris tiap entitas adalah keluaran `etl/pindah_etl/transform.py`. Contoh
  lengkapnya ada di `etl/build/normalized/` sesudah `transform`.
- Tanggal dalam format ISO `YYYY-MM-DD`.
- Uang dalam rupiah sebagai angka desimal, dua digit di belakang koma.
- Angka rekonsiliasi memakai tanda debit dikurangi kredit (`BR-REK-01`).
- Galat per baris dikembalikan di `errors` ringkasan batch, tidak dilempar sebagai
  galat HTTP. Galat HTTP berarti permintaannya sendiri salah.

## Belum diputuskan

- Kapan valuasi persediaan diubah ke perpetual sesudah go-live, dan siapa yang
  menyetujui jurnal penyesuaiannya.
- Apakah aset tetap dipindah per aset dengan jadwal penyusutannya, atau cukup saldo akun.
