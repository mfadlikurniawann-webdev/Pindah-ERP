# Jembatan: Rekonsiliasi Migrasi

Membandingkan angka Accurate per tanggal cutoff dengan angka Odoo: saldo per akun,
piutang dan hutang per kontak, kuantitas stok per gudang, dan nilai persediaan per produk.

- Snapshot Accurate: `jembatan.source.balance.api_load`, diisi ETL.
- Perhitungan: `jembatan.reconcile.run.action_compute`, atau `api_run` lewat JSON-2.
- Laporan PDF (QWeb): `report/reconcile_report.xml`.
- Dashboard (OWL): `static/src/dashboard/`, menu **Migrasi > Ringkasan Migrasi**.

Konvensi tanda dan toleransi: `docs/knowledge/domain/rekonsiliasi.md`.
