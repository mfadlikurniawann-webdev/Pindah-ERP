# Panduan Migrasi

Cara memakai Pindah-ERP untuk data Accurate sungguhan, bukan data contoh. Ditulis untuk
developer yang menjalankan ETL dan Finance yang memeriksa angkanya.

## Ringkasnya

1. Tetapkan tanggal cutoff bersama Finance.
2. Ekspor sepuluh berkas dari Accurate per tanggal cutoff.
3. Jalankan `transform`, perbaiki temuan sampai tidak ada yang fatal.
4. Jalankan `load --dry-run` di database uji, lalu `load` dan `reconcile`.
5. Finance memeriksa dan menandatangani PDF rekonsiliasi.
6. Ulangi langkah 2 sampai 5 di database produksi pada hari go-live.

## 1. Tanggal cutoff

Cutoff adalah hari terakhir transaksi dicatat di Accurate. Esok harinya semua transaksi
masuk ke Odoo. Pilih akhir bulan, supaya PPN dan tutup buku bulan itu selesai di Accurate.

Isi tanggalnya di `etl/config.toml`, kunci `company.cutoff_date`.

## 2. Berkas ekspor

Simpan di satu folder, lalu arahkan `source.folder` di `config.toml` ke folder itu.
Simpan dari Excel sebagai **CSV UTF-8**, dengan pemisah titik koma.

| Berkas | Isi | Kolom wajib |
|---|---|---|
| `daftar_akun.csv` | Daftar akun | No. Akun, Nama Akun, Tipe Akun |
| `pelanggan.csv` | Pelanggan | No. Pelanggan, Nama, NPWP, PKP, Alamat, Kota, Telepon, Email |
| `pemasok.csv` | Pemasok | No. Pemasok, dan kolom yang sama dengan pelanggan |
| `gudang.csv` | Gudang | Kode, Nama Gudang |
| `barang.csv` | Barang dan jasa | No. Barang, Nama Barang, Kategori, Satuan, Harga Jual, Jenis Barang |
| `bom.csv` | Bill of Materials | No. Barang Jadi, Kuantitas, Satuan, No. Bahan, Kuantitas Bahan, Satuan Bahan |
| `neraca_saldo.csv` | Neraca saldo per cutoff | No. Akun, Nama Akun, Debit, Kredit |
| `piutang_outstanding.csv` | Faktur penjualan belum lunas | No. Faktur, Tanggal, Jatuh Tempo, No. Pelanggan, Sisa |
| `hutang_outstanding.csv` | Faktur pembelian belum lunas | No. Faktur, Tanggal, Jatuh Tempo, No. Pemasok, Sisa |
| `stok_awal.csv` | Kuantitas dan nilai per barang per gudang | No. Barang, Gudang, Kuantitas, Nilai |

Contoh tiap berkas ada di `sample_data/accurate_export/`. Nama kolom di Accurate bisa
sedikit berbeda menurut versi; samakan judul kolomnya dengan contoh.

Angka boleh tetap berformat Indonesia (`1.250.000,00`). Tanggal berformat `dd/mm/yyyy`;
format lain diatur di `source.date_format`. Retur atau kelebihan bayar ditulis negatif
di kolom Sisa.

## 3. Transform dan laporan validasi

```bash
cd etl
python -m pindah_etl transform
```

Buka `etl/build/laporan_validasi.md`. Setiap temuan punya tingkat:

| Tingkat | Artinya | Yang dilakukan |
|---|---|---|
| `fatal` | Angka tidak bisa dipercaya | Wajib diperbaiki. `load` menolak berjalan |
| `rejected` | Satu baris tidak ikut dimuat | Perbaiki di Accurate atau CSV, lalu ulangi |
| `fixed` | Dibetulkan otomatis | Periksa sekilas bahwa hasilnya benar |
| `info` | Catatan | Tidak perlu tindakan |

Temuan fatal yang paling sering:

| Pesan | Biasanya karena |
|---|---|
| Neraca saldo tidak seimbang | Ekspor terpotong, atau ada akun yang disaring |
| Total faktur terbuka tidak sama dengan saldo akun | Ada jurnal umum langsung ke akun piutang/hutang di Accurate |
| Nilai stok awal tidak sama dengan saldo akun persediaan | Ekspor stok tidak per tanggal cutoff, atau ada jurnal manual ke akun persediaan |
| Tipe Akun belum dipetakan | Tipe Akun di Accurate belum ada di bagian `[account_types]` config |
| Stok minus | Ada barang keluar sebelum barang masuk dicatat. Selesaikan di Accurate |

## 4. Muat dan rekonsiliasi

Selalu coba di database uji dulu.

```bash
python -m pindah_etl load --dry-run   # semua entitas, lalu dibatalkan
python -m pindah_etl load
python -m pindah_etl reconcile
```

Kalau `load` berhenti karena galat, perbaiki penyebabnya lalu jalankan ulang perintah
yang sama. Data yang sudah masuk diperbarui atau dilewati, tidak digandakan.

Tanpa terminal, Finance bisa mengunggah berkas dari `etl/build/normalized/` satu per
satu lewat menu **Migrasi > Impor Berkas**, sesuai urutan nomor di nama berkas.

Arti status rekonsiliasi per baris:

| Status | Artinya |
|---|---|
| Cocok | Angka Accurate sama dengan Odoo |
| Selisih | Ada di keduanya, angkanya berbeda |
| Tidak ada di Odoo | Ada di Accurate, belum dimigrasi |
| Tidak ada di Accurate | Ada di Odoo dengan nilai bukan nol. Contoh: akun penampung yang belum kembali nol |

Semua angka memakai tanda debit dikurangi kredit. Hutang, modal, dan pendapatan karena
itu tampil negatif.

## 5. Tanda tangan Finance

Buka **Migrasi > Rekonsiliasi**, pilih hasil terakhir, klik **Cetak PDF**. Go-live baru
boleh dilakukan bila statusnya Cocok dan PDF sudah ditandatangani.

## 6. Hari go-live

1. Kunci periode di Accurate per tanggal cutoff.
2. Ekspor ulang sepuluh berkas.
3. Jalankan langkah 3 sampai 5 di database produksi.
4. Atur lock date Odoo per tanggal cutoff, supaya saldo awal tidak bisa diubah.
5. Mulai mencatat transaksi di Odoo.

## Mengulang saldo awal

Jurnal saldo awal hanya dibuat sekali. Bila neraca saldo Accurate berubah sesudah
dimuat, batalkan dan hapus jurnal di jurnal **Saldo Awal Migrasi**, lalu jalankan ulang
`load --only opening_balance`. Faktur terbuka dan stok awal diperlakukan sama: hapus
dokumennya di Odoo dulu, baru muat ulang.
