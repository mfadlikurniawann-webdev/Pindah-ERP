"""Batch migrasi: satu kali jalan impor untuk satu entitas.

Pintu masuk ada dua, dan keduanya berakhir di ``_run``:

* ETL di luar Odoo memanggil ``api_import`` lewat JSON-2 API.
* User Finance mengunggah berkas JSON hasil ETL lewat wizard.
"""

import copy
import logging
from contextlib import contextmanager

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

ENTITIES = [
    ("account", "Akun (COA)"),
    ("warehouse", "Gudang"),
    ("partner", "Kontak"),
    ("product", "Produk"),
    ("bom", "Bill of Materials"),
    ("opening_balance", "Saldo Awal Akun"),
    ("opening_receivable", "Saldo Awal Piutang"),
    ("opening_payable", "Saldo Awal Hutang"),
    ("opening_stock", "Stok Awal"),
]

# Entitas dokumen: semua baris membentuk satu dokumen, jadi semua atau tidak sama sekali.
DOCUMENT_ENTITIES = {"opening_balance"}


class _DryRunRollback(Exception):
    """Dilempar untuk membatalkan savepoint saat dry run."""


@contextmanager
def _rolled_back(env):
    """Jalankan isi blok lalu batalkan semuanya, termasuk hook postcommit.

    Savepoint Odoo membatalkan data dan hook precommit, tapi hook postcommit
    yang didaftarkan di dalamnya tetap tinggal. Contohnya ``account`` yang
    menaikkan ``customer_rank`` sesudah commit. Hook itu lalu menyentuh record
    yang sudah dibatalkan dan menggagalkan seluruh request. Karena itu antrean
    postcommit dikembalikan ke keadaan sebelum blok.
    """
    postcommit = env.cr.postcommit
    funcs, data = list(postcommit._funcs), {key: copy.copy(value) for key, value in postcommit.data.items()}
    try:
        with env.cr.savepoint():
            yield
            raise _DryRunRollback()
    except _DryRunRollback:
        pass
    finally:
        postcommit.clear()
        postcommit._funcs.extend(funcs)
        postcommit.data.update(data)
        env.invalidate_all()


class JembatanMigrationBatch(models.Model):
    _name = "jembatan.migration.batch"
    _description = "Batch migrasi data"
    _order = "id desc"

    name = fields.Char(required=True, readonly=True, default=lambda self: _("Baru"))
    entity = fields.Selection(ENTITIES, required=True, readonly=True)
    state = fields.Selection(
        [("draft", "Draf"), ("done", "Selesai"), ("partial", "Sebagian galat"), ("failed", "Gagal")],
        default="draft",
        required=True,
        readonly=True,
    )
    dry_run = fields.Boolean(readonly=True, help="Uji coba: semua perubahan dibatalkan di akhir.")
    row_count = fields.Integer("Baris", readonly=True)
    created_count = fields.Integer("Dibuat", readonly=True)
    updated_count = fields.Integer("Diperbarui", readonly=True)
    skipped_count = fields.Integer("Dilewati", readonly=True)
    error_count = fields.Integer("Galat", readonly=True)
    log_ids = fields.One2many("jembatan.migration.log", "batch_id", readonly=True)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Baru")) == _("Baru"):
                label = dict(ENTITIES).get(vals.get("entity"), "")
                vals["name"] = f"{label} / {fields.Datetime.now():%Y-%m-%d %H:%M:%S}"
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # API publik
    # ------------------------------------------------------------------
    @api.model
    def api_import(self, entity, rows, dry_run=False):
        """Impor ``rows`` (daftar dict hasil ETL) untuk ``entity``.

        Dipanggil lewat ``POST /json/2/jembatan.migration.batch/api_import``.
        Mengembalikan ringkasan agar ETL bisa mencetak hasil tanpa membaca log.
        """
        if entity not in dict(ENTITIES):
            raise UserError(_("Entitas tidak dikenal: %s", entity))
        if not isinstance(rows, list):
            raise UserError(_("rows harus berupa daftar."))
        batch = self.create({"entity": entity, "dry_run": dry_run, "row_count": len(rows)})
        batch._run(rows)
        return batch._summary()

    @api.model
    def api_import_many(self, payloads, dry_run=False, keep_going=False):
        """Impor beberapa entitas berurutan, misalnya seluruh migrasi sekaligus.

        ``payloads`` berbentuk ``[{"entity": ..., "rows": [...]}, ...]``.
        Dengan ``dry_run``, semua entitas dijalankan dalam satu transaksi lalu
        dibatalkan bersama, sehingga entitas belakang bisa memakai hasil
        entitas depan (BR-MIG-05). Yang tersisa hanya catatan batchnya.
        """
        if not dry_run:
            summaries = []
            for payload in payloads:
                summaries.append(self.api_import(payload["entity"], payload["rows"]))
                if summaries[-1]["state"] in ("failed", "partial") and not keep_going:
                    break
            return summaries

        records = []
        with _rolled_back(self.env):
            for payload in payloads:
                batch = self.create({"entity": payload["entity"], "row_count": len(payload["rows"])})
                batch._run(payload["rows"])
                records.append(batch._snapshot_vals())
                if batch.state in ("failed", "partial") and not keep_going:
                    break
        return [self.create({**vals, "dry_run": True})._summary() for vals in records]

    def _snapshot_vals(self):
        self.ensure_one()
        return {
            "entity": self.entity,
            "state": self.state,
            "row_count": self.row_count,
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "log_ids": [
                fields.Command.create({"level": log.level, "source_ref": log.source_ref, "message": log.message})
                for log in self.log_ids
            ],
        }

    # ------------------------------------------------------------------
    # Jalannya impor
    # ------------------------------------------------------------------
    def _run(self, rows):
        self.ensure_one()
        importer = self.env["jembatan.importer"].with_company(self.company_id)
        counters = {"created": 0, "updated": 0, "skipped": 0, "error": 0}
        logs = []

        def run_rows():
            if self.entity in DOCUMENT_ENTITIES:
                self._run_document(importer, rows, counters, logs)
            else:
                for row in rows:
                    self._run_row(importer, row, counters, logs)

        if self.dry_run:
            with _rolled_back(self.env):
                run_rows()
        else:
            run_rows()

        if counters["error"] and not (counters["created"] or counters["updated"] or counters["skipped"]):
            state = "failed"
        elif counters["error"]:
            state = "partial"
        else:
            state = "done"
        self.write(
            {
                "state": state,
                "created_count": counters["created"],
                "updated_count": counters["updated"],
                "skipped_count": counters["skipped"],
                "error_count": counters["error"],
                "log_ids": [fields.Command.create(log) for log in logs],
            }
        )
        _logger.info("Batch %s selesai: %s", self.name, counters)

    def _run_row(self, importer, row, counters, logs):
        method = getattr(importer, f"_import_{self.entity}")
        ref = str(row.get("code") or row.get("number") or row.get("product_code") or "")
        try:
            with self.env.cr.savepoint():
                status, message = method(row)
        except (UserError, ValidationError) as exc:
            self.env.invalidate_all()
            counters["error"] += 1
            logs.append({"level": "error", "source_ref": ref, "message": str(exc.args[0] if exc.args else exc)})
            return
        counters[status] += 1
        if message:
            logs.append({"level": "info", "source_ref": ref, "message": message})

    def _run_document(self, importer, rows, counters, logs):
        method = getattr(importer, f"_import_{self.entity}")
        try:
            with self.env.cr.savepoint():
                status, message = method(rows)
        except (UserError, ValidationError) as exc:
            self.env.invalidate_all()
            counters["error"] += 1
            logs.append({"level": "error", "source_ref": self.entity, "message": str(exc.args[0] if exc.args else exc)})
            return
        counters[status] += 1
        logs.append({"level": "info", "source_ref": self.entity, "message": message})

    def _summary(self):
        self.ensure_one()
        return {
            "batch_id": self.id,
            "batch": self.name,
            "entity": self.entity,
            "state": self.state,
            "dry_run": self.dry_run,
            "rows": self.row_count,
            "created": self.created_count,
            "updated": self.updated_count,
            "skipped": self.skipped_count,
            "errors": [
                {"ref": log.source_ref, "message": log.message}
                for log in self.log_ids.filtered(lambda log: log.level == "error")
            ],
        }
