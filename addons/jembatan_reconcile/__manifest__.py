{
    "name": "Jembatan: Rekonsiliasi Migrasi",
    "summary": "Bandingkan neraca saldo, piutang/hutang, dan stok Accurate dengan Odoo",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Pindah-ERP",
    "website": "https://github.com/mfadlikurniawann-webdev/Pindah-ERP",
    "license": "LGPL-3",
    "depends": ["jembatan_migration"],
    "data": [
        "security/ir.model.access.csv",
        "views/reconcile_views.xml",
        "report/reconcile_report.xml",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "jembatan_reconcile/static/src/dashboard/*",
        ],
    },
    "installable": True,
}
