from odoo.tests import TransactionCase, tagged

CUTOFF = "2026-09-30"
SUSPENSE = "399999"


@tagged("post_install", "-at_install")
class TestJembatanImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Batch = cls.env["jembatan.migration.batch"]
        cls.Batch.api_import(
            "account",
            [
                {"code": "110101", "name": "Kas", "account_type": "asset_cash"},
                {"code": "110301", "name": "Piutang Usaha", "account_type": "asset_receivable", "reconcile": True},
                {"code": "110401", "name": "Persediaan", "account_type": "asset_current"},
                {"code": "210101", "name": "Hutang Usaha", "account_type": "liability_payable", "reconcile": True},
                {"code": "310101", "name": "Modal Disetor", "account_type": "equity"},
                {"code": SUSPENSE, "name": "Penampung Saldo Awal", "account_type": "equity"},
            ],
        )
        cls.Batch.api_import("warehouse", [{"code": "PBK", "name": "Gudang Pabrik"}])
        cls.Batch.api_import(
            "partner",
            [
                {
                    "code": "C-0001",
                    "name": "CV Pelanggan Satu",
                    "rank": "customer",
                    "vat": "0013000666091000",
                    "is_pkp": True,
                    "receivable_account_code": "110301",
                    "payable_account_code": "210101",
                },
                {
                    "code": "V-0001",
                    "name": "UD Pemasok Satu",
                    "rank": "supplier",
                    "receivable_account_code": "110301",
                    "payable_account_code": "210101",
                },
            ],
        )
        cls.Batch.api_import(
            "product",
            [
                {
                    "code": "BB-001",
                    "name": "Biji Kopi Mentah",
                    "category": "Bahan Baku",
                    "uom": "uom.product_uom_kgm",
                    "cost": 60000.0,
                    "sale_ok": False,
                },
                {
                    "code": "BJ-001",
                    "name": "Kopi Bubuk 250 g",
                    "category": "Barang Jadi",
                    "uom": "uom.product_uom_unit",
                    "cost": 25000.0,
                    "sale_price": 45000.0,
                },
            ],
        )

    def _ref(self, entity, code):
        return self.env["jembatan.importer"]._find(entity, code)

    def test_master_data_is_idempotent(self):
        """BR-MIG-01: menjalankan ulang batch yang sama memperbarui, tidak menggandakan."""
        summary = self.Batch.api_import(
            "partner",
            [
                {"code": "C-0001", "name": "CV Pelanggan Satu (ganti nama)", "rank": "customer"},
            ],
        )
        self.assertEqual((summary["created"], summary["updated"]), (0, 1))
        self.assertEqual(self.env["res.partner"].search_count([("ref", "=", "C-0001")]), 1)
        self.assertEqual(self._ref("partner", "C-0001").name, "CV Pelanggan Satu (ganti nama)")

    def test_partner_tax_fields(self):
        partner = self._ref("partner", "C-0001")
        self.assertTrue(partner.l10n_id_pkp)
        self.assertEqual(partner.property_account_receivable_id.code, "110301")

    def test_account_type_conflict_is_rejected(self):
        summary = self.Batch.api_import(
            "account",
            [
                {"code": "110101", "name": "Kas", "account_type": "income"},
            ],
        )
        self.assertEqual(summary["state"], "failed")
        self.assertIn("tipe", summary["errors"][0]["message"])

    def test_dry_run_saves_nothing(self):
        summary = self.Batch.api_import("warehouse", [{"code": "DST", "name": "Gudang Distribusi"}], dry_run=True)
        self.assertEqual(summary["created"], 1)
        self.assertFalse(self._ref("warehouse", "DST"))
        self.assertFalse(self.env["stock.warehouse"].search([("code", "=", "DST")]))

    def test_bom(self):
        summary = self.Batch.api_import(
            "bom",
            [
                {
                    "product_code": "BJ-001",
                    "quantity": 1,
                    "uom": "uom.product_uom_unit",
                    "lines": [{"product_code": "BB-001", "quantity": 0.3, "uom": "uom.product_uom_kgm"}],
                }
            ],
        )
        self.assertEqual(summary["created"], 1, summary)
        bom = self._ref("bom", "BJ-001")
        self.assertEqual(bom.bom_line_ids.product_id.default_code, "BB-001")

    def test_full_opening_flow_leaves_suspense_at_zero(self):
        """BR-SALDO-03: setelah jurnal saldo awal dan faktur terbuka, akun penampung nol."""
        opening = [
            {"date": CUTOFF, "suspense_account_code": SUSPENSE, "account_code": "110101", "debit": 10_000_000},
            {"date": CUTOFF, "suspense_account_code": SUSPENSE, "account_code": "110401", "debit": 6_000_000},
            {"date": CUTOFF, "suspense_account_code": SUSPENSE, "account_code": "310101", "credit": 19_000_000},
        ]
        # Neraca sumber: piutang 5 jt, hutang 2 jt, jadi selisih jurnal = 3 jt di penampung.
        summary = self.Batch.api_import("opening_balance", opening)
        self.assertEqual(summary["state"], "done", summary)

        common = {"date": CUTOFF, "suspense_account_code": SUSPENSE}
        self.Batch.api_import(
            "opening_receivable",
            [
                {
                    **common,
                    "number": "SI.2026.09.00012",
                    "partner_code": "C-0001",
                    "invoice_date": "2026-09-15",
                    "due_date": "2026-10-15",
                    "amount": 5_000_000,
                }
            ],
        )
        self.Batch.api_import(
            "opening_payable",
            [
                {
                    **common,
                    "number": "PI.2026.09.00007",
                    "partner_code": "V-0001",
                    "invoice_date": "2026-09-20",
                    "due_date": "2026-10-20",
                    "amount": 2_000_000,
                }
            ],
        )

        suspense = self.env["jembatan.importer"]._account(SUSPENSE)
        lines = self.env["account.move.line"].search(
            [
                ("account_id", "=", suspense.id),
                ("parent_state", "=", "posted"),
            ]
        )
        self.assertAlmostEqual(sum(lines.mapped("balance")), 0.0)

        invoice = self._ref("opening_receivable", "SI.2026.09.00012")
        self.assertEqual(invoice.amount_residual, 5_000_000)
        self.assertEqual(str(invoice.date), CUTOFF, "Tanggal jurnal harus tanggal cutoff")
        self.assertEqual(str(invoice.invoice_date), "2026-09-15", "Tanggal faktur asli dipertahankan")
        self.assertEqual(invoice.journal_id.code, "MIGAR")

    def test_opening_balance_runs_once(self):
        rows = [{"date": CUTOFF, "suspense_account_code": SUSPENSE, "account_code": "110101", "debit": 1000}]
        self.assertEqual(self.Batch.api_import("opening_balance", rows)["state"], "done")
        second = self.Batch.api_import("opening_balance", rows)
        self.assertEqual((second["state"], second["skipped"]), ("done", 1))
        self.assertEqual(self.env["account.move"].search_count([("journal_id.code", "=", "MIG")]), 1)

    def test_opening_balance_rejects_receivable_account(self):
        rows = [{"date": CUTOFF, "suspense_account_code": SUSPENSE, "account_code": "110301", "debit": 1000}]
        summary = self.Batch.api_import("opening_balance", rows)
        self.assertEqual(summary["state"], "failed")
        self.assertFalse(self._ref("opening_balance", "main"))

    def test_open_invoice_is_not_duplicated(self):
        row = {
            "date": CUTOFF,
            "suspense_account_code": SUSPENSE,
            "number": "SI-1",
            "partner_code": "C-0001",
            "invoice_date": "2026-09-01",
            "due_date": "2026-10-01",
            "amount": 100_000,
        }
        self.Batch.api_import("opening_receivable", [row])
        second = self.Batch.api_import("opening_receivable", [row])
        self.assertEqual(second["skipped"], 1)

    def test_negative_receivable_becomes_credit_note(self):
        row = {
            "date": CUTOFF,
            "suspense_account_code": SUSPENSE,
            "number": "SR-1",
            "partner_code": "C-0001",
            "invoice_date": "2026-09-01",
            "due_date": "2026-09-01",
            "amount": -250_000,
        }
        self.Batch.api_import("opening_receivable", [row])
        self.assertEqual(self._ref("opening_receivable", "SR-1").move_type, "out_refund")

    def test_opening_stock_sets_quantity_without_journal(self):
        """BR-STOK-02: stok awal hanya mengisi kuantitas; nilainya dari jurnal saldo awal."""
        moves_before = self.env["account.move"].search_count([])
        summary = self.Batch.api_import(
            "opening_stock",
            [
                {"product_code": "BB-001", "warehouse_code": "PBK", "quantity": 100},
            ],
        )
        self.assertEqual(summary["created"], 1, summary)
        product = self._ref("product", "BB-001")
        warehouse = self._ref("warehouse", "PBK")
        self.assertEqual(product.with_context(warehouse_id=warehouse.id).qty_available, 100)
        self.assertEqual(self.env["account.move"].search_count([]), moves_before)

    def test_opening_stock_rejects_unknown_product(self):
        summary = self.Batch.api_import(
            "opening_stock",
            [
                {"product_code": "XX-999", "warehouse_code": "PBK", "quantity": 1},
            ],
        )
        self.assertEqual(summary["state"], "failed")
        self.assertIn("belum dimigrasi", summary["errors"][0]["message"])

    def test_dry_run_many_keeps_dependencies_and_leaves_no_hooks(self):
        """BR-MIG-05: dry run seluruh urutan memakai hasil entitas sebelumnya, lalu tidak meninggalkan apa pun."""
        hooks_before = len(self.env.cr.postcommit._funcs)
        results = self.Batch.api_import_many(
            [
                {
                    "entity": "partner",
                    "rows": [
                        {"code": "C-0099", "name": "CV Baru", "rank": "customer", "receivable_account_code": "110301"}
                    ],
                },
                {
                    "entity": "opening_receivable",
                    "rows": [
                        {
                            "date": CUTOFF,
                            "suspense_account_code": SUSPENSE,
                            "number": "SI-99",
                            "partner_code": "C-0099",
                            "invoice_date": "2026-09-01",
                            "due_date": "2026-10-01",
                            "amount": 1000,
                        }
                    ],
                },
            ],
            dry_run=True,
        )
        self.assertEqual([r["state"] for r in results], ["done", "done"])
        self.assertTrue(all(r["dry_run"] for r in results))
        self.assertFalse(self._ref("partner", "C-0099"))
        self.assertEqual(len(self.env.cr.postcommit._funcs), hooks_before)
