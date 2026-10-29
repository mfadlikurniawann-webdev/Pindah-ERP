# Rencana

## Urutan pengerjaan

| # | Bagian | Kenapa di posisi ini |
|:--:|---|---|
| 1 | `migrasi` | Semua bagian lain memakai jejak sumber, batch, dan uji coba dari sini |
| 2 | `kontak` | Faktur terbuka butuh kontak yang sudah ada |
| 3 | `saldo-awal` | Inti migrasi; butuh akun dan kontak |
| 4 | `stok-awal` | Butuh produk, gudang, dan jurnal saldo awal untuk nilainya |
| 5 | `rekonsiliasi` | Memeriksa hasil semua bagian di atas |

## Yang belum digali

| Calon | Yang sudah diketahui | Kapan pantas dibuka |
|---|---|---|
| `aset-tetap` | Saat ini aset hanya pindah sebagai saldo akun | Bila perusahaan memakai modul aset Odoo |
| `faktur-pajak` | Modul `l10n_id_efaktur_coretax` ada di Community dan menghasilkan XML | Sesudah go-live, saat faktur pertama di Odoo |
| `laporan-faktur` | Format faktur Indonesia dengan terbilang | Saat Finance meminta tata letak sendiri |
