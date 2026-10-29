"""Menjalankan seluruh transformasi dan menulis hasilnya ke ``build/``."""

import json
from datetime import datetime
from pathlib import Path

from . import transform as t
from .extract import read_csv

# Urutan muat. Nomor di nama berkas memaksa urutan yang sama saat diunggah manual.
LOAD_ORDER = [
    ("01", "account"),
    ("02", "warehouse"),
    ("03", "partner"),
    ("04", "product"),
    ("05", "bom"),
    ("06", "opening_balance"),
    ("07", "opening_receivable"),
    ("08", "opening_payable"),
    ("09", "opening_stock"),
]
SNAPSHOT_FILE = "10_source_balance.json"

INTERNAL_KEYS = {"is_inventory"}


def run_transform(config: dict, base_dir: Path) -> tuple[dict[str, list], list[dict], t.Report]:
    source = config["source"]
    folder = (base_dir / source["folder"]).resolve()
    delimiter = source["delimiter"]

    def read(name):
        return read_csv(folder, name, delimiter)

    report = t.Report()
    stock_rows = read("stok_awal.csv")

    accounts = t.transform_accounts(read("daftar_akun.csv"), config, report)
    warehouses = t.transform_warehouses(read("gudang.csv"), config, report)
    customers = t.transform_partners(read("pelanggan.csv"), "customer", "No. Pelanggan", config, report)
    suppliers = t.transform_partners(read("pemasok.csv"), "supplier", "No. Pemasok", config, report)
    products = t.transform_products(read("barang.csv"), stock_rows, config, report)
    boms = t.transform_boms(read("bom.csv"), products, config, report)
    opening, balances = t.transform_trial_balance(read("neraca_saldo.csv"), accounts, config, report)
    receivables = t.transform_open_items(
        read("piutang_outstanding.csv"), "No. Pelanggan", customers, "receivable", balances, accounts, config, report
    )
    payables = t.transform_open_items(
        read("hutang_outstanding.csv"), "No. Pemasok", suppliers, "payable", balances, accounts, config, report
    )
    stock = t.transform_opening_stock(stock_rows, products, warehouses, accounts, balances, report)
    snapshot = t.build_source_snapshot(accounts, balances, receivables, payables, stock_rows, products)

    entities = {
        "account": [{k: v for k, v in a.items() if k not in INTERNAL_KEYS} for a in accounts],
        "warehouse": warehouses,
        "partner": customers + suppliers,
        "product": products,
        "bom": boms,
        "opening_balance": opening,
        "opening_receivable": receivables,
        "opening_payable": payables,
        "opening_stock": stock,
    }
    return entities, snapshot, report


def write_outputs(entities: dict, snapshot: list, report: t.Report, out_dir: Path) -> None:
    normalized = out_dir / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    for old in normalized.glob("*.json"):
        old.unlink()
    for number, entity in LOAD_ORDER:
        payload = {"entity": entity, "rows": entities[entity]}
        (normalized / f"{number}_{entity}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    (normalized / SNAPSHOT_FILE).write_text(json.dumps({"rows": snapshot}, indent=2, ensure_ascii=False))
    (out_dir / "laporan_validasi.md").write_text(render_report(entities, snapshot, report))
    status = {level: report.count(level) for level in t.LEVELS}
    (out_dir / "status.json").write_text(json.dumps(status, indent=2))


def render_report(entities: dict, snapshot: list, report: t.Report) -> str:
    lines = [
        "# Laporan Validasi ETL",
        "",
        f"Dibuat {datetime.now():%Y-%m-%d %H:%M}. Berkas ini dibuat ulang setiap `transform` dijalankan.",
        "",
        "## Ringkasan",
        "",
        "| Entitas | Baris siap muat |",
        "|---|--:|",
    ]
    lines += [f"| `{entity}` | {len(entities[entity])} |" for _, entity in LOAD_ORDER]
    lines += [f"| `source_balance` | {len(snapshot)} |", ""]
    lines += [
        "| Tingkat | Jumlah | Artinya |",
        "|---|--:|---|",
        f"| fatal | {report.count('fatal')} | Pemuatan dihentikan sampai sumbernya diperbaiki |",
        f"| rejected | {report.count('rejected')} | Baris tidak ikut dimuat |",
        f"| fixed | {report.count('fixed')} | Dibetulkan otomatis, periksa sekilas |",
        f"| info | {report.count('info')} | Catatan saja |",
        "",
        "## Temuan",
        "",
    ]
    if not report.issues:
        lines.append("Tidak ada temuan.")
    else:
        lines += ["| Tingkat | Berkas | Baris | Kode | Pesan |", "|---|---|--:|---|---|"]
        order = {level: index for index, level in enumerate(reversed(t.LEVELS))}
        for issue in sorted(report.issues, key=lambda i: (order[i.level], i.file, i.line or 0)):
            lines.append(f"| {issue.level} | {issue.file} | {issue.line or ''} | {issue.ref} | {issue.message} |")
    return "\n".join(lines) + "\n"
