# Repo knowledge Pindah-ERP

Rancangan Pindah-ERP: apa yang dibangun dan kenapa. Kode di `addons/` dan `etl/` merujuk
aturan di sini lewat ID `BR-...`. Isinya hanya yang berlaku sekarang. Perubahan aturan
mendarat di sini lebih dulu, baru di kode.

Semua pekerjaan di folder ini lewat `/knowledge`. Cara kerja dan bentuk tiap berkas ada di
`.claude/skills/knowledge/SKILL.md`.

## Prefix aturan

| Berkas | Prefix |
|---|---|
| `domain/migrasi.md` | `BR-MIG` |
| `domain/kontak.md` | `BR-KONTAK` |
| `domain/saldo-awal.md` | `BR-SALDO` |
| `domain/stok-awal.md` | `BR-STOK` |
| `domain/rekonsiliasi.md` | `BR-REK` |

## Sudah dipatok, jangan ditanya ulang

- Sumber Accurate, tujuan Odoo 19 Community. Tidak memakai fitur Enterprise.
- Satu perusahaan, satu mata uang (IDR).
- Kode akun Accurate dipertahankan di Odoo.
- Cutoff di akhir bulan. Saldo laba rugi tahun berjalan ikut dipindah.
- Valuasi persediaan periodik selama migrasi.
- ETL hanya memakai pustaka standar Python dan memanggil Odoo lewat JSON-2 API.
