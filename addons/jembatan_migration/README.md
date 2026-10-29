# Jembatan: Migrasi Accurate ke Odoo

Mengimpor hasil ETL `etl/pindah_etl` ke Odoo 19: daftar akun, gudang, kontak, produk,
BoM, jurnal saldo awal, faktur piutang/hutang terbuka, dan stok awal.

- Pintu masuk: `jembatan.migration.batch.api_import` dan `api_import_many` (JSON-2 API),
  atau menu **Migrasi > Impor Berkas**.
- Logika per entitas: `models/importer.py`, satu metode `_import_<entitas>`.
- Aman diulang: kode Accurate disimpan di `ir.model.data` dengan modul `jembatan_src`.
- Hak akses: grup **Migrasi Data: Pengelola**.

Aturan yang dirujuk di kode (`BR-...`) ada di `docs/knowledge/domain/`.
