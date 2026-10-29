from odoo.tests import TransactionCase, tagged

CUTOFF = "2026-09-30"
SUSPENSE = "399999"


@tagged("post_install", "-at_install")
class TestReconcile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        batch = cls.env["jembatan.migration.batch"]
        batch.api_import(
            "account",
            [
                {"code": "110101", "name": "Kas", "account_type": "asset_cash"},
                {"code": "110301", "name": "Piutang Usaha", "account_type": "asset_receivable", "reconcile": True},
                {"code": "310101", "name": "Modal", "account_type": "equity"},
                {"code": SUSPENSE, "name": "Penampung", "account_type": "equity"},
            ],
        )
        batch.api_import("warehouse", [{"code": "PBK", "name": "Gudang Pabrik"}])
        batch.api_import(
            "partner", [{"code": "C-0001", "name": "CV Satu", "rank": "customer", "receivable_account_code": "110301"}]
        )
        batch.api_import(
            "product",
            [
                {
                    "code": "BB-001",
                    "name": "Biji Kopi",
                    "category": "Bahan Baku",
                    "uom": "uom.product_uom_kgm",
                    "cost": 60000.0,
                }
            ],
        )
        common = {"date": CUTOFF, "suspense_account_code": SUSPENSE}
        batch.api_import(
            "opening_balance",
            [
                {**common, "account_code": "110101", "debit": 1_000_000},
                {**common, "account_code": "310101", "credit": 1_500_000},
            ],
        )
        batch.api_import(
            "opening_receivable",
            [
                {
                    **common,
                    "number": "SI-1",
                    "partner_code": "C-0001",
                    "invoice_date": "2026-09-10",
                    "due_date": "2026-10-10",
                    "amount": 500_000,
                }
            ],
        )
        batch.api_import("opening_stock", [{"product_code": "BB-001", "warehouse_code": "PBK", "quantity": 10}])

    def _load_source(self, cash=1_000_000):
        self.env["jembatan.source.balance"].api_load(
            [
                {"kind": "account", "key": "110101", "amount": cash},
                {"kind": "account", "key": "110301", "amount": 500_000},
                {"kind": "account", "key": "310101", "amount": -1_500_000},
                {"kind": "receivable", "key": "C-0001", "amount": 500_000},
                {"kind": "stock_qty", "key": "BB-001@PBK", "amount": 10},
                {"kind": "stock_value", "key": "BB-001", "amount": 600_000},
            ]
        )

    def test_everything_matches(self):
        self._load_source()
        result = self.env["jembatan.reconcile.run"].api_run(CUTOFF)
        self.assertEqual(result["state"], "match", result["lines"])

    def test_difference_is_reported(self):
        self._load_source(cash=1_250_000)
        result = self.env["jembatan.reconcile.run"].api_run(CUTOFF)
        self.assertEqual(result["state"], "mismatch")
        cash = next(line for line in result["lines"] if line["key"] == "110101")
        self.assertEqual(cash["status"], "diff")
        self.assertEqual(cash["difference"], -250_000)

    def test_suspense_with_balance_is_flagged(self):
        """BR-SALDO-03: penampung yang tidak nol muncul sebagai selisih, walau tidak ada di sumber."""
        self._load_source()
        self.env["jembatan.migration.batch"].api_import(
            "opening_receivable",
            [
                {
                    "date": CUTOFF,
                    "suspense_account_code": SUSPENSE,
                    "number": "SI-EXTRA",
                    "partner_code": "C-0001",
                    "invoice_date": "2026-09-11",
                    "due_date": "2026-10-11",
                    "amount": 1000,
                }
            ],
        )
        result = self.env["jembatan.reconcile.run"].api_run(CUTOFF)
        keys = {(line["kind"], line["key"]): line["status"] for line in result["lines"]}
        self.assertEqual(keys[("account", SUSPENSE)], "missing_source")

    def test_report_renders(self):
        self._load_source()
        run = self.env["jembatan.reconcile.run"].create({"date": CUTOFF})
        run.action_compute()
        html, _type = self.env["ir.actions.report"]._render_qweb_html("jembatan_reconcile.report_reconcile", run.ids)
        self.assertIn(b"Laporan Rekonsiliasi Migrasi", html)

    def test_dashboard_data(self):
        self._load_source()
        self.env["jembatan.reconcile.run"].api_run(CUTOFF)
        data = self.env["jembatan.reconcile.run"].get_dashboard_data()
        self.assertTrue(data["run"])
        self.assertTrue(data["batches"])
