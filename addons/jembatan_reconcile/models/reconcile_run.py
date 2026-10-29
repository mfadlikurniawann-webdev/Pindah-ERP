from collections import defaultdict

from odoo import _, api, fields, models
from odoo.tools import float_is_zero

from .source_balance import KINDS

STOCK_KINDS = {"stock_qty"}
QTY_PRECISION = 4


class JembatanReconcileRun(models.Model):
    _name = "jembatan.reconcile.run"
    _description = "Rekonsiliasi migrasi"
    _order = "id desc"

    name = fields.Char(required=True, default=lambda self: _("Rekonsiliasi"))
    date = fields.Date("Tanggal cutoff", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    line_ids = fields.One2many("jembatan.reconcile.line", "run_id", readonly=True)
    state = fields.Selection(
        [("draft", "Belum dihitung"), ("match", "Cocok"), ("mismatch", "Ada selisih")],
        default="draft",
        required=True,
        readonly=True,
    )
    mismatch_count = fields.Integer(compute="_compute_counts", store=True)
    match_count = fields.Integer(compute="_compute_counts", store=True)

    @api.depends("line_ids.status")
    def _compute_counts(self):
        for run in self:
            run.match_count = len(run.line_ids.filtered(lambda line: line.status == "match"))
            run.mismatch_count = len(run.line_ids) - run.match_count

    # ------------------------------------------------------------------
    # Angka dari Odoo, semuanya debit dikurangi kredit (BR-REK-01)
    # ------------------------------------------------------------------
    def _odoo_values(self):
        self.ensure_one()
        values = {}
        labels = {}
        MoveLine = self.env["account.move.line"]
        base_domain = [
            ("parent_state", "=", "posted"),
            ("date", "<=", self.date),
            ("company_id", "=", self.company_id.id),
        ]
        for account, balance in MoveLine._read_group(base_domain, ["account_id"], ["balance:sum"]):
            values[("account", account.code)] = balance
            labels[("account", account.code)] = account.name

        for kind, account_type in (("receivable", "asset_receivable"), ("payable", "liability_payable")):
            groups = MoveLine._read_group(
                [*base_domain, ("account_id.account_type", "=", account_type)],
                ["partner_id"],
                ["amount_residual:sum"],
            )
            for partner, residual in groups:
                key = partner.ref or f"ID:{partner.id}"
                values[(kind, key)] = values.get((kind, key), 0.0) + residual
                labels[(kind, key)] = partner.name

        quants = self.env["stock.quant"].search(
            [
                ("location_id.usage", "=", "internal"),
                ("company_id", "=", self.company_id.id),
            ]
        )
        product_qty = defaultdict(float)
        for quant in quants:
            product = quant.product_id
            code = product.default_code or f"ID:{product.id}"
            warehouse = quant.location_id.warehouse_id
            key = f"{code}@{warehouse.code or 'TANPA-GUDANG'}"
            values[("stock_qty", key)] = values.get(("stock_qty", key), 0.0) + quant.quantity
            labels[("stock_qty", key)] = product.display_name
            product_qty[product] += quant.quantity
        for product, qty in product_qty.items():
            key = ("stock_value", product.default_code or f"ID:{product.id}")
            values[key] = self.currency_id.round(qty * product.standard_price)
            labels[key] = product.display_name
        return values, labels

    def _source_values(self):
        self.ensure_one()
        values, labels = {}, {}
        for row in self.env["jembatan.source.balance"].search([("company_id", "=", self.company_id.id)]):
            values[(row.kind, row.key)] = row.amount
            labels[(row.kind, row.key)] = row.label
        return values, labels

    def _is_zero(self, kind, amount):
        if kind in STOCK_KINDS:
            return float_is_zero(amount, precision_digits=QTY_PRECISION)
        return self.currency_id.is_zero(amount)

    def action_compute(self):
        for run in self:
            odoo, odoo_labels = run._odoo_values()
            source, source_labels = run._source_values()
            commands = [fields.Command.clear()]
            for kind, key in sorted(set(odoo) | set(source)):
                in_odoo, in_source = (kind, key) in odoo, (kind, key) in source
                odoo_amount = odoo.get((kind, key), 0.0)
                source_amount = source.get((kind, key), 0.0)
                difference = odoo_amount - source_amount
                if run._is_zero(kind, difference):
                    status = "match"
                elif not in_odoo:
                    status = "missing_odoo"
                elif not in_source:
                    status = "missing_source"
                else:
                    status = "diff"
                commands.append(
                    fields.Command.create(
                        {
                            "kind": kind,
                            "key": key,
                            "label": source_labels.get((kind, key)) or odoo_labels.get((kind, key)),
                            "source_amount": source_amount,
                            "odoo_amount": odoo_amount,
                            "difference": difference,
                            "status": status,
                        }
                    )
                )
            run.line_ids = commands
            run.state = "match" if not run.line_ids.filtered(lambda line: line.status != "match") else "mismatch"
        return True

    def action_print(self):
        return self.env.ref("jembatan_reconcile.action_report_reconcile").report_action(self)

    @api.model
    def api_run(self, date):
        """Buat dan hitung rekonsiliasi; dipanggil ETL lewat JSON-2."""
        run = self.create({"date": date, "name": _("Rekonsiliasi per %s", date)})
        run.action_compute()
        return {
            "run_id": run.id,
            "state": run.state,
            "match": run.match_count,
            "mismatch": run.mismatch_count,
            "lines": [
                {
                    "kind": line.kind,
                    "key": line.key,
                    "source": line.source_amount,
                    "odoo": line.odoo_amount,
                    "difference": line.difference,
                    "status": line.status,
                }
                for line in run.line_ids.filtered(lambda line: line.status != "match")
            ],
        }

    def get_report_summary(self):
        """Ringkasan per jenis, dipakai laporan PDF dan dashboard."""
        self.ensure_one()
        summary = []
        for kind, label in KINDS:
            lines = self.line_ids.filtered(lambda line, kind=kind: line.kind == kind)
            if lines:
                summary.append(
                    {
                        "kind": kind,
                        "label": label,
                        "total": len(lines),
                        "mismatch": len(lines.filtered(lambda line: line.status != "match")),
                        "difference": sum(lines.mapped("difference")),
                    }
                )
        return summary

    @api.model
    def get_dashboard_data(self):
        """Ringkasan rekonsiliasi terakhir untuk dashboard OWL."""
        run = self.search([("company_id", "=", self.env.company.id), ("state", "!=", "draft")], limit=1)
        Batch = self.env["jembatan.migration.batch"]
        entity_labels = dict(Batch._fields["entity"].selection)
        state_labels = dict(Batch._fields["state"].selection)
        last_by_entity = {}
        for batch in Batch.search_read([("dry_run", "=", False)], ["entity", "state", "error_count"], limit=100):
            last_by_entity.setdefault(
                batch["entity"],
                {
                    **batch,
                    "entity_label": entity_labels[batch["entity"]],
                    "state_label": state_labels[batch["state"]],
                },
            )
        # Urutkan sesuai urutan migrasi, bukan urutan waktu.
        batches = [last_by_entity[entity] for entity in entity_labels if entity in last_by_entity]
        if not run:
            return {"run": False, "kinds": [], "batches": batches}
        return {
            "run": {"id": run.id, "name": run.name, "date": run.date, "state": run.state},
            "kinds": run.get_report_summary(),
            "batches": batches,
        }


class JembatanReconcileLine(models.Model):
    _name = "jembatan.reconcile.line"
    _description = "Baris rekonsiliasi"
    _order = "kind, status desc, key"

    run_id = fields.Many2one("jembatan.reconcile.run", required=True, ondelete="cascade", index=True)
    kind = fields.Selection(KINDS, required=True)
    key = fields.Char(required=True)
    label = fields.Char()
    source_amount = fields.Float("Accurate", digits=(16, 2))
    odoo_amount = fields.Float("Odoo", digits=(16, 2))
    difference = fields.Float("Selisih", digits=(16, 2))
    status = fields.Selection(
        [
            ("match", "Cocok"),
            ("diff", "Selisih"),
            ("missing_odoo", "Tidak ada di Odoo"),
            ("missing_source", "Tidak ada di Accurate"),
        ],
        required=True,
    )
