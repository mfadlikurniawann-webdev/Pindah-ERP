"""Perintah ETL.

    python -m pindah_etl transform           baca ekspor Accurate, tulis build/
    python -m pindah_etl load [--dry-run]    muat build/normalized/ ke Odoo
    python -m pindah_etl reconcile           muat saldo Accurate lalu bandingkan dengan Odoo
    python -m pindah_etl all                 ketiganya berurutan

Jalankan dari folder ``etl/``. Lihat docs/panduan-migrasi.md.
"""

import argparse
import json
import sys
from pathlib import Path

from .client import OdooClient, OdooError
from .pipeline import LOAD_ORDER, SNAPSHOT_FILE, run_transform, write_outputs
from .settings import load_config, load_env

ETL_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = ETL_DIR.parent


def _print(message=""):
    print(message, flush=True)


def cmd_transform(args) -> int:
    config = load_config(args.config)
    entities, snapshot, report = run_transform(config, Path(args.config).resolve().parent)
    write_outputs(entities, snapshot, report, args.build)
    _print(f"Hasil ditulis ke {args.build}/normalized/")
    _print(f"Laporan validasi: {args.build}/laporan_validasi.md")
    _print(
        f"  fatal {report.count('fatal')}, ditolak {report.count('rejected')}, "
        f"dibetulkan {report.count('fixed')}, info {report.count('info')}"
    )
    if report.has_fatal:
        _print("ADA TEMUAN FATAL. Perbaiki sumbernya dulu; pemuatan akan menolak berjalan.")
        return 1
    return 0


def _client(args) -> OdooClient:
    env = load_env(args.env)
    missing = [key for key in ("ODOO_URL", "ODOO_DB", "ODOO_API_KEY") if not env.get(key)]
    if missing:
        raise SystemExit(f"Isi {', '.join(missing)} di {args.env}. Lihat docs/setup-lokal.md langkah 5.")
    return OdooClient(env["ODOO_URL"], env["ODOO_DB"], env["ODOO_API_KEY"])


def _check_no_fatal(build: Path) -> None:
    status = build / "status.json"
    if not status.exists():
        raise SystemExit("Belum ada hasil transform. Jalankan: python -m pindah_etl transform")
    if json.loads(status.read_text())["fatal"]:
        raise SystemExit(f"Ada temuan fatal di {build}/laporan_validasi.md. Pemuatan dibatalkan (BR-MIG-03).")


def _print_summary(number, result):
    _print(
        f"{number} {result['entity']:<20} {result['state']:<8} baris {result['rows']:>4}  "
        f"dibuat {result['created']:>4}  diperbarui {result['updated']:>4}  "
        f"dilewati {result['skipped']:>4}  galat {len(result['errors']):>3}"
    )
    for error in result["errors"]:
        _print(f"     ! {error['ref']}: {error['message']}")


def cmd_load(args) -> int:
    _check_no_fatal(args.build)
    client = _client(args)
    only = set(args.only or [])
    payloads = []
    for number, entity in LOAD_ORDER:
        if only and entity not in only:
            continue
        rows = json.loads((args.build / "normalized" / f"{number}_{entity}.json").read_text())["rows"]
        if rows:
            payloads.append((number, {"entity": entity, "rows": rows}))
        else:
            _print(f"{number} {entity:<20} kosong, dilewati")

    if args.dry_run:
        # Satu panggilan, satu transaksi: entitas belakang bisa memakai hasil entitas depan.
        results = client.call(
            "jembatan.migration.batch",
            "api_import_many",
            payloads=[payload for _, payload in payloads],
            dry_run=True,
            keep_going=args.keep_going,
        )
        numbers = dict((payload["entity"], number) for number, payload in payloads)
        for result in results:
            _print_summary(numbers[result["entity"]], result)
        _print("Uji coba selesai. Tidak ada data yang tersimpan, hanya catatan batch.")
        return 1 if any(r["state"] in ("failed", "partial") for r in results) else 0

    failed = False
    for number, payload in payloads:
        result = client.call("jembatan.migration.batch", "api_import", entity=payload["entity"], rows=payload["rows"])
        _print_summary(number, result)
        if result["state"] in ("failed", "partial"):
            failed = True
            if not args.keep_going:
                _print("Berhenti karena ada galat. Perbaiki, lalu jalankan ulang (impor aman diulang).")
                return 1
    return 1 if failed else 0


def cmd_reconcile(args) -> int:
    client = _client(args)
    config = load_config(args.config)
    snapshot = json.loads((args.build / "normalized" / SNAPSHOT_FILE).read_text())["rows"]
    loaded = client.call("jembatan.source.balance", "api_load", rows=snapshot)
    _print(f"Saldo Accurate dimuat: {loaded['loaded']} baris")
    result = client.call("jembatan.reconcile.run", "api_run", date=config["company"]["cutoff_date"])
    _print(
        f"Rekonsiliasi #{result['run_id']}: {result['state'].upper()}  "
        f"cocok {result['match']}, tidak cocok {result['mismatch']}"
    )
    for line in result["lines"]:
        _print(
            f"  {line['kind']:<12} {line['key']:<16} Accurate {line['source']:>18,.2f}  "
            f"Odoo {line['odoo']:>18,.2f}  selisih {line['difference']:>16,.2f}  {line['status']}"
        )
    _print("Rincian dan PDF: menu Migrasi > Rekonsiliasi di Odoo.")
    return 0 if result["state"] == "match" else 1


def cmd_all(args) -> int:
    for step in (cmd_transform, cmd_load, cmd_reconcile):
        code = step(args)
        if code:
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pindah_etl", description="Migrasi Accurate ke Odoo 19")
    parser.add_argument("--config", type=Path, default=ETL_DIR / "config.toml")
    parser.add_argument("--env", type=Path, default=REPO_DIR / ".env")
    parser.add_argument("--build", type=Path, default=ETL_DIR / "build")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("transform", help="Validasi dan normalisasi ekspor Accurate")
    load = sub.add_parser("load", help="Muat hasil transform ke Odoo")
    every = sub.add_parser("all", help="transform, load, lalu reconcile")
    for p in (load, every):
        p.add_argument("--dry-run", action="store_true", help="Uji coba tanpa menyimpan")
        p.add_argument("--keep-going", action="store_true", help="Lanjut ke entitas berikut walau ada galat")
        p.add_argument("--only", nargs="*", help="Hanya entitas tertentu, misalnya: --only partner product")
    sub.add_parser("reconcile", help="Bandingkan saldo Accurate dengan Odoo")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"transform": cmd_transform, "load": cmd_load, "reconcile": cmd_reconcile, "all": cmd_all}
    try:
        return handlers[args.command](args)
    except OdooError as exc:
        print(f"GAGAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
