"""Logika impor per entitas.

Setiap metode ``_import_<entitas>`` menerima satu baris (atau, untuk entitas
dokumen, semua baris) dalam bentuk ternormalisasi hasil ETL, lalu
mengembalikan ``(status, pesan)`` dengan status ``created``, ``updated``, atau
``skipped``. Kegagalan dilaporkan dengan ``UserError``; batch yang
menangkapnya dan mencatat galat per baris.

Bentuk baris tiap entitas didokumentasikan di
``docs/knowledge/README.md`` bagian Konvensi API.
"""

import re

from odoo import _, fields, models
from odoo.exceptions import UserError

SRC_MODULE = "jembatan_src"

RECEIVABLE_PAYABLE = ("asset_receivable", "liability_payable")


class JembatanImporter(models.AbstractModel):
    _name = "jembatan.importer"
    _description = "Importer data Accurate"

    # ------------------------------------------------------------------
    # Jejak sumber: kode Accurate -> record Odoo (BR-MIG-01)
    # ------------------------------------------------------------------
    def _ref_name(self, entity, code):
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(code)).strip("_").lower()
        if not slug:
            raise UserError(_("Kode sumber kosong untuk entitas %s.", entity))
        return f"{entity}_{slug}"

    def _find(self, entity, code):
        imd = (
            self.env["ir.model.data"]
            .sudo()
            .search([("module", "=", SRC_MODULE), ("name", "=", self._ref_name(entity, code))], limit=1)
        )
        if not imd:
            return None
        record = self.env[imd.model].browse(imd.res_id).exists()
        if not record:
            imd.unlink()  # record sudah dihapus manual; jejaknya ikut dibersihkan
            return None
        return record

    def _bind(self, entity, code, record):
        self.env["ir.model.data"].sudo().create(
            {
                "module": SRC_MODULE,
                "name": self._ref_name(entity, code),
                "model": record._name,
                "res_id": record.id,
                "noupdate": True,
            }
        )

    def _require(self, entity, code, label):
        record = self._find(entity, code)
        if not record:
            raise UserError(_("%(label)s dengan kode %(code)s belum dimigrasi.", label=label, code=code))
        return record

    def _account(self, code):
        Account = self.env["account.account"]
        account = Account.search([("code", "=", code), *Account._check_company_domain(self.env.company)], limit=1)
        if not account:
            raise UserError(_("Akun %s tidak ditemukan. Migrasikan COA dulu.", code))
        return account

    def _journal(self, code, name, journal_type):
        """Jurnal khusus migrasi, agar penomoran dokumen operasional tetap bersih (BR-MIG-04)."""
        Journal = self.env["account.journal"]
        journal = Journal.search([("code", "=", code), *Journal._check_company_domain(self.env.company)], limit=1)
        if not journal:
            journal = Journal.create({"code": code, "name": name, "type": journal_type})
        return journal

    def _uom(self, xmlid):
        uom = self.env.ref(xmlid, raise_if_not_found=False)
        if not uom or uom._name != "uom.uom":
            raise UserError(_("Satuan %s tidak dikenal.", xmlid))
        return uom

    # ------------------------------------------------------------------
    # Master data
    # ------------------------------------------------------------------
    def _import_account(self, row):
        Account = self.env["account.account"]
        existing = Account.search(
            [("code", "=", row["code"]), *Account._check_company_domain(self.env.company)], limit=1
        )
        if existing:
            if existing.account_type != row["account_type"]:
                raise UserError(
                    _(
                        "Kode akun %(code)s sudah ada dengan tipe %(old)s, sumber meminta %(new)s.",
                        code=row["code"],
                        old=existing.account_type,
                        new=row["account_type"],
                    )
                )
            existing.name = row["name"]
            if not self._find("account", row["code"]):
                self._bind("account", row["code"], existing)
            return "updated", None
        account = Account.create(
            {
                "code": row["code"],
                "name": row["name"],
                "account_type": row["account_type"],
                "reconcile": row.get("reconcile", False),
            }
        )
        self._bind("account", row["code"], account)
        return "created", None

    def _import_warehouse(self, row):
        warehouse = self._find("warehouse", row["code"])
        if warehouse:
            warehouse.name = row["name"]
            return "updated", None
        warehouse = self.env["stock.warehouse"].create(
            {
                "name": row["name"],
                "code": row["code"],
                "company_id": self.env.company.id,
            }
        )
        self._bind("warehouse", row["code"], warehouse)
        return "created", None

    def _import_partner(self, row):
        vals = {
            "name": row["name"],
            "ref": row["code"],
            "is_company": True,
            "vat": row.get("vat") or False,
            "street": row.get("street") or False,
            "city": row.get("city") or False,
            "phone": row.get("phone") or False,
            "email": row.get("email") or False,
            "country_id": self.env.ref("base.id").id,
            "l10n_id_pkp": bool(row.get("is_pkp")),
        }
        if row.get("receivable_account_code"):
            vals["property_account_receivable_id"] = self._account(row["receivable_account_code"]).id
        if row.get("payable_account_code"):
            vals["property_account_payable_id"] = self._account(row["payable_account_code"]).id
        if row.get("rank") == "customer":
            vals["customer_rank"] = 1
        elif row.get("rank") == "supplier":
            vals["supplier_rank"] = 1

        partner = self._find("partner", row["code"])
        if partner:
            partner.write(vals)
            return "updated", None
        partner = self.env["res.partner"].create(vals)
        self._bind("partner", row["code"], partner)
        return "created", None

    def _import_product(self, row):
        Category = self.env["product.category"]
        category = Category.search([("name", "=", row["category"])], limit=1) or Category.create(
            {"name": row["category"]}
        )
        uom = self._uom(row["uom"])
        vals = {
            "name": row["name"],
            "default_code": row["code"],
            "type": "consu",
            "is_storable": row.get("is_storable", True),
            "categ_id": category.id,
            "uom_id": uom.id,
            "list_price": row.get("sale_price", 0.0),
            "standard_price": row.get("cost", 0.0),
            "sale_ok": row.get("sale_ok", True),
            "purchase_ok": row.get("purchase_ok", True),
        }
        template = self._find("product", row["code"])
        if template:
            if template.qty_available and template.uom_id != uom:
                raise UserError(_("Satuan produk %s tidak boleh diubah setelah ada stok.", row["code"]))
            template.write(vals)
            return "updated", None
        template = self.env["product.template"].create(vals)
        self._bind("product", row["code"], template)
        return "created", None

    def _import_bom(self, row):
        template = self._require("product", row["product_code"], _("Produk"))
        lines = []
        for line in row["lines"]:
            component = self._require("product", line["product_code"], _("Komponen"))
            if component == template:
                raise UserError(_("BoM %s memakai dirinya sendiri sebagai komponen.", row["product_code"]))
            lines.append(
                fields.Command.create(
                    {
                        "product_id": component.product_variant_id.id,
                        "product_qty": line["quantity"],
                        "product_uom_id": self._uom(line["uom"]).id,
                    }
                )
            )
        vals = {
            "product_tmpl_id": template.id,
            "product_qty": row["quantity"],
            "product_uom_id": self._uom(row["uom"]).id,
            "type": "normal",
            "code": row["product_code"],
        }
        bom = self._find("bom", row["product_code"])
        if bom:
            bom.write({**vals, "bom_line_ids": [fields.Command.clear(), *lines]})
            return "updated", None
        bom = self.env["mrp.bom"].create({**vals, "bom_line_ids": lines})
        self._bind("bom", row["product_code"], bom)
        return "created", None

    # ------------------------------------------------------------------
    # Saldo awal
    # ------------------------------------------------------------------
    def _import_opening_balance(self, rows):
        """Satu jurnal saldo awal untuk semua akun selain piutang dan hutang usaha.

        Selisihnya ditampung di akun penampung. Piutang dan hutang masuk
        lewat faktur terbuka, berpasangan dengan akun penampung yang sama,
        sehingga penampung kembali nol bila semuanya cocok (BR-SALDO-03).
        """
        if not rows:
            raise UserError(_("Tidak ada baris saldo awal."))
        existing = self._find("opening_balance", "main")
        if existing:
            return "skipped", _(
                "Jurnal saldo awal %s sudah ada dan tidak diubah. Batalkan dan hapus jurnal itu dulu "
                "bila neraca saldo sumber berubah (BR-SALDO-02).",
                existing.name,
            )
        dates = {row["date"] for row in rows}
        suspense_codes = {row["suspense_account_code"] for row in rows}
        if len(dates) != 1 or len(suspense_codes) != 1:
            raise UserError(_("Semua baris saldo awal harus punya tanggal dan akun penampung yang sama."))
        suspense = self._account(suspense_codes.pop())

        lines = []
        total = 0.0
        for row in rows:
            account = self._account(row["account_code"])
            if account.account_type in RECEIVABLE_PAYABLE:
                raise UserError(
                    _(
                        "Akun %s adalah piutang/hutang usaha. Saldonya masuk lewat faktur terbuka, bukan jurnal.",
                        account.code,
                    )
                )
            debit, credit = float(row.get("debit") or 0.0), float(row.get("credit") or 0.0)
            if not debit and not credit:
                continue
            total += debit - credit
            lines.append(
                fields.Command.create(
                    {
                        "account_id": account.id,
                        "name": _("Saldo awal %s", account.code),
                        "debit": debit,
                        "credit": credit,
                    }
                )
            )
        if not self.env.company.currency_id.is_zero(total):
            lines.append(
                fields.Command.create(
                    {
                        "account_id": suspense.id,
                        "name": _("Penampung saldo awal"),
                        "debit": -total if total < 0 else 0.0,
                        "credit": total if total > 0 else 0.0,
                    }
                )
            )
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self._journal("MIG", _("Saldo Awal Migrasi"), "general").id,
                "date": dates.pop(),
                "ref": _("Saldo awal migrasi Accurate"),
                "line_ids": lines,
            }
        )
        move.action_post()
        self._bind("opening_balance", "main", move)
        return "created", _("%(name)s dengan %(count)s baris.", name=move.name, count=len(move.line_ids))

    def _import_open_invoice(self, row, entity, move_type, journal_code, journal_name, journal_type):
        if self._find(entity, row["number"]):
            return "skipped", _("Faktur %s sudah dimigrasi.", row["number"])
        partner = self._require("partner", row["partner_code"], _("Kontak"))
        amount = float(row["amount"])
        if not amount:
            raise UserError(_("Sisa faktur %s nol; tidak perlu dimigrasi.", row["number"]))
        if amount < 0:  # kelebihan bayar atau retur yang belum dipakai
            move_type = {"out_invoice": "out_refund", "in_invoice": "in_refund"}[move_type]
            amount = -amount
        suspense = self._account(row["suspense_account_code"])
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "journal_id": self._journal(journal_code, journal_name, journal_type).id,
                "partner_id": partner.id,
                "invoice_date": row["invoice_date"],
                "date": row["date"],
                "invoice_date_due": row["due_date"],
                "ref": row["number"],
                "payment_reference": row["number"],
                "invoice_line_ids": [
                    fields.Command.create(
                        {
                            "name": _("Sisa faktur Accurate %s", row["number"]),
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": suspense.id,
                            "tax_ids": [fields.Command.clear()],
                        }
                    )
                ],
            }
        )
        move.action_post()
        self._bind(entity, row["number"], move)
        return "created", None

    def _import_opening_receivable(self, row):
        return self._import_open_invoice(
            row, "opening_receivable", "out_invoice", "MIGAR", _("Saldo Awal Piutang"), "sale"
        )

    def _import_opening_payable(self, row):
        return self._import_open_invoice(
            row, "opening_payable", "in_invoice", "MIGAP", _("Saldo Awal Hutang"), "purchase"
        )

    def _import_opening_stock(self, row):
        """Isi kuantitas stok awal per gudang.

        Nilai persediaan sudah masuk lewat jurnal saldo awal, jadi penyesuaian
        stok ini tidak boleh membuat jurnal lagi (BR-STOK-02).
        """
        code = f"{row['product_code']}@{row['warehouse_code']}"
        if self._find("opening_stock", code):
            return "skipped", _("Stok awal %s sudah dimigrasi.", code)
        template = self._require("product", row["product_code"], _("Produk"))
        warehouse = self._require("warehouse", row["warehouse_code"], _("Gudang"))
        if not template.is_storable:
            raise UserError(_("Produk %s tidak dilacak stoknya.", row["product_code"]))
        if template.valuation == "real_time":
            raise UserError(
                _(
                    "Kategori produk %s memakai valuasi perpetual; stok awal akan membuat jurnal ganda.",
                    row["product_code"],
                )
            )
        quantity = float(row["quantity"])
        if quantity <= 0:
            raise UserError(_("Stok awal %s harus lebih dari nol.", code))
        quant = (
            self.env["stock.quant"]
            .with_context(inventory_mode=True)
            .create(
                {
                    "product_id": template.product_variant_id.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "inventory_quantity": quantity,
                }
            )
        )
        quant.action_apply_inventory()
        self._bind("opening_stock", code, quant)
        return "created", None
