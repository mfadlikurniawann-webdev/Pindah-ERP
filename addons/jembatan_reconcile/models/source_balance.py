from odoo import _, api, fields, models
from odoo.exceptions import UserError

KINDS = [
    ("account", "Saldo akun"),
    ("receivable", "Piutang per pelanggan"),
    ("payable", "Hutang per pemasok"),
    ("stock_qty", "Kuantitas stok per gudang"),
    ("stock_value", "Nilai persediaan per produk"),
]


class JembatanSourceBalance(models.Model):
    """Angka pembanding dari Accurate per tanggal cutoff.

    Semua angka uang memakai tanda debit dikurangi kredit (BR-REK-01):
    piutang positif, hutang negatif, modal negatif.
    """

    _name = "jembatan.source.balance"
    _description = "Saldo sumber (Accurate) untuk rekonsiliasi"
    _order = "kind, key"

    kind = fields.Selection(KINDS, required=True, index=True)
    key = fields.Char(required=True, index=True, help="Kode akun, kode kontak, kode produk, atau produk@gudang")
    label = fields.Char()
    amount = fields.Float(required=True, digits=(16, 4))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    _key_unique = models.Constraint(
        "unique(company_id, kind, key)",
        "Satu kunci hanya boleh muncul sekali per jenis.",
    )

    @api.model
    def api_load(self, rows):
        """Ganti seluruh snapshot untuk jenis yang dikirim, lalu kembalikan jumlah baris.

        Dipanggil lewat ``POST /json/2/jembatan.source.balance/api_load``.
        """
        kinds = {row.get("kind") for row in rows}
        unknown = kinds - set(dict(KINDS))
        if unknown:
            raise UserError(_("Jenis tidak dikenal: %s", ", ".join(map(str, unknown))))
        self.search([("kind", "in", list(kinds)), ("company_id", "=", self.env.company.id)]).unlink()
        self.create(
            [
                {
                    "kind": row["kind"],
                    "key": row["key"],
                    "label": row.get("label"),
                    "amount": row["amount"],
                }
                for row in rows
            ]
        )
        return {"loaded": len(rows), "kinds": sorted(kinds)}
