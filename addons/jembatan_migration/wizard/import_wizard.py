import base64
import json

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.migration_batch import ENTITIES


class JembatanImportWizard(models.TransientModel):
    """Jalan impor tanpa terminal: unggah satu berkas JSON hasil ETL."""

    _name = "jembatan.import.wizard"
    _description = "Impor berkas hasil ETL"

    entity = fields.Selection(ENTITIES, required=True)
    file = fields.Binary("Berkas JSON", required=True)
    filename = fields.Char()
    dry_run = fields.Boolean(
        "Uji coba dulu", default=True, help="Jalankan tanpa menyimpan, untuk melihat galat lebih awal."
    )

    def action_import(self):
        self.ensure_one()
        try:
            rows = json.loads(base64.b64decode(self.file))
        except (ValueError, TypeError) as exc:
            raise UserError(_("Berkas bukan JSON yang sah: %s", exc)) from exc
        if isinstance(rows, dict):  # berkas ETL berbentuk {"entity": ..., "rows": [...]}
            if rows.get("entity") and rows["entity"] != self.entity:
                raise UserError(
                    _("Berkas ini untuk entitas %(file)s, bukan %(chosen)s.", file=rows["entity"], chosen=self.entity)
                )
            rows = rows.get("rows", [])
        summary = self.env["jembatan.migration.batch"].api_import(self.entity, rows, dry_run=self.dry_run)
        return {
            "type": "ir.actions.act_window",
            "res_model": "jembatan.migration.batch",
            "res_id": summary["batch_id"],
            "view_mode": "form",
            "target": "current",
        }
