from odoo import fields, models


class JembatanMigrationLog(models.Model):
    _name = "jembatan.migration.log"
    _description = "Catatan baris migrasi"
    _order = "id"

    batch_id = fields.Many2one("jembatan.migration.batch", required=True, ondelete="cascade", index=True)
    level = fields.Selection(
        [("info", "Info"), ("warning", "Peringatan"), ("error", "Galat")],
        required=True,
        default="info",
    )
    source_ref = fields.Char("Kode sumber", help="Kode baris di ekspor Accurate")
    message = fields.Text(required=True)
