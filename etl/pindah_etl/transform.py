"""Membersihkan dan menormalisasi ekspor Accurate menjadi baris siap impor.

Setiap fungsi ``transform_*`` mengembalikan daftar baris ternormalisasi dan
mencatat temuan ke ``Report``. Tingkat temuan:

* ``info``      dicatat saja, misalnya baris kosong dilewati.
* ``fixed``     data dibetulkan otomatis, misalnya format NPWP.
* ``rejected``  baris ditolak dan tidak ikut dimuat; Finance perlu memperbaiki sumbernya.
* ``fatal``     angka tidak bisa dipercaya; seluruh pemuatan dihentikan.

Aturan yang dirujuk (``BR-...``) ada di ``docs/knowledge/domain/``.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from .extract import SourceRow, parse_date, parse_number

LEVELS = ("info", "fixed", "rejected", "fatal")


@dataclass
class Issue:
    level: str
    file: str
    line: int | None
    ref: str
    message: str


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    def add(self, level: str, row: SourceRow | None, ref: str, message: str, file: str = "") -> None:
        assert level in LEVELS, level
        self.issues.append(Issue(level, row.file if row else file, row.line if row else None, ref, message))

    def count(self, level: str) -> int:
        return sum(1 for issue in self.issues if issue.level == level)

    @property
    def has_fatal(self) -> bool:
        return self.count("fatal") > 0


def _close(a: float, b: float) -> bool:
    return abs(a - b) < 0.005


# ----------------------------------------------------------------------
# NPWP
# ----------------------------------------------------------------------
def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def normalize_npwp(raw: str) -> tuple[str | None, str | None]:
    """Kembalikan ``(npwp_16_digit, alasan_tolak)``.

    NPWP 15 digit lama diubah ke 16 digit dengan menambah 0 di depan
    (BR-KONTAK-02). Nomor berawalan 0 diperiksa checksum Luhn pada 9 digit
    pertama nomor lama, sama seperti validasi Odoo.
    """
    digits = "".join(char for char in raw if char.isdigit())
    if not digits:
        return None, None
    if len(digits) == 15:
        digits = "0" + digits
    if len(digits) != 16:
        return None, f"NPWP harus 15 atau 16 digit, tertulis {len(digits)} digit"
    if digits[0] == "0" and not _luhn_ok(digits[1:10]):
        return None, "checksum NPWP tidak cocok, kemungkinan salah ketik"
    return digits, None


# ----------------------------------------------------------------------
# Master data
# ----------------------------------------------------------------------
def _dedupe(rows: list[SourceRow], key_column: str, report: Report) -> list[SourceRow]:
    """Buang duplikat persis; tolak kode ganda dengan isi berbeda (BR-MIG-02)."""
    seen: dict[str, SourceRow] = {}
    conflicts: set[str] = set()
    for row in rows:
        code = row.get(key_column)
        if not code:
            report.add("rejected", row, "", f"Kolom {key_column} kosong")
            continue
        if code in seen:
            if seen[code].data == row.data:
                report.add("fixed", row, code, f"Duplikat persis baris {seen[code].line}, dibuang")
            else:
                conflicts.add(code)
                report.add("rejected", row, code, f"Kode sama dengan baris {seen[code].line} tapi isinya berbeda")
            continue
        seen[code] = row
    return [row for code, row in seen.items() if code not in conflicts]


def transform_accounts(rows, config, report):
    types = config["account_types"]
    result = []
    for row in _dedupe(rows, "No. Akun", report):
        code, source_type = row.get("No. Akun"), row.get("Tipe Akun")
        if source_type not in types:
            report.add("fatal", row, code, f"Tipe Akun '{source_type}' belum dipetakan di config.toml")
            continue
        account_type = types[source_type]
        result.append(
            {
                "code": code,
                "name": row.get("Nama Akun"),
                "account_type": account_type,
                "reconcile": account_type in ("asset_receivable", "liability_payable"),
                "is_inventory": source_type == "Persediaan",
            }
        )
    for code, extra in config.get("extra_accounts", {}).items():
        result.append(
            {
                "code": code,
                "name": extra["name"],
                "account_type": types[extra["type"]],
                "reconcile": False,
                "is_inventory": False,
            }
        )
        report.add("info", None, code, "Akun tambahan dari config.toml", file="config.toml")
    return result


def transform_warehouses(rows, config, report):
    result = []
    for row in _dedupe(rows, "Kode", report):
        code = row.get("Kode").upper()
        if len(code) > 5:
            report.add("rejected", row, code, "Kode gudang Odoo paling panjang 5 karakter")
            continue
        result.append({"code": code, "name": row.get("Nama Gudang")})
    return result


def transform_partners(rows, rank, code_column, config, report):
    company = config["company"]
    result = []
    for row in _dedupe(rows, code_column, report):
        code = row.get(code_column)
        is_pkp = row.get("PKP").lower() in ("ya", "y", "true", "1")
        vat, reason = normalize_npwp(row.get("NPWP"))
        if reason:
            report.add("rejected", row, code, f"{reason}: {row.get('NPWP')}")
            continue
        if vat and vat != row.get("NPWP"):
            report.add("fixed", row, code, f"NPWP dinormalisasi {row.get('NPWP')} -> {vat}")
        if is_pkp and not vat:
            report.add("rejected", row, code, "Berstatus PKP tapi NPWP kosong; e-Faktur tidak bisa dibuat")
            continue
        result.append(
            {
                "code": code,
                "name": row.get("Nama"),
                "rank": rank,
                "vat": vat,
                "is_pkp": is_pkp,
                "street": row.get("Alamat") or None,
                "city": row.get("Kota") or None,
                "phone": row.get("Telepon") or None,
                "email": row.get("Email") or None,
                "receivable_account_code": company["receivable_account_code"],
                "payable_account_code": company["payable_account_code"],
            }
        )
    return result


def _uom(text, config):
    return config["uom"].get(text.strip().upper())


def transform_products(rows, stock_rows, config, report):
    """Produk. Harga pokok diambil dari stok awal: nilai dibagi kuantitas (BR-STOK-03)."""
    totals = defaultdict(lambda: [0.0, 0.0])
    for row in stock_rows:
        totals[row.get("No. Barang")][0] += parse_number(row.get("Kuantitas"))
        totals[row.get("No. Barang")][1] += parse_number(row.get("Nilai"))

    result = []
    for row in _dedupe(rows, "No. Barang", report):
        code = row.get("No. Barang")
        uom = _uom(row.get("Satuan"), config)
        if not uom:
            report.add("rejected", row, code, f"Satuan '{row.get('Satuan')}' belum dipetakan di config.toml")
            continue
        qty, value = totals.get(code, (0.0, 0.0))
        is_storable = row.get("Jenis Barang").lower() == "persediaan"
        result.append(
            {
                "code": code,
                "name": row.get("Nama Barang"),
                "category": row.get("Kategori") or "Lainnya",
                "uom": uom,
                "sale_price": parse_number(row.get("Harga Jual")),
                "cost": round(value / qty, 6) if qty else 0.0,
                "is_storable": is_storable,
                "sale_ok": parse_number(row.get("Harga Jual")) > 0,
                "purchase_ok": is_storable,
            }
        )
    return result


def transform_boms(rows, products, config, report):
    known = {product["code"] for product in products}
    boms: dict[str, dict] = {}
    for row in rows:
        parent, component = row.get("No. Barang Jadi"), row.get("No. Bahan")
        missing = [code for code in (parent, component) if code not in known]
        if missing:
            report.add("rejected", row, parent, f"Barang {', '.join(missing)} tidak ada di daftar barang")
            boms.setdefault(parent, {})["broken"] = True
            continue
        bom = boms.setdefault(parent, {})
        bom.setdefault("product_code", parent)
        bom.setdefault("quantity", parse_number(row.get("Kuantitas")))
        bom.setdefault("uom", _uom(row.get("Satuan"), config))
        bom.setdefault("lines", []).append(
            {
                "product_code": component,
                "quantity": parse_number(row.get("Kuantitas Bahan")),
                "uom": _uom(row.get("Satuan Bahan"), config),
            }
        )
    result = []
    for code, bom in boms.items():
        if bom.pop("broken", False):
            report.add("rejected", None, code, "BoM ditolak utuh karena ada komponen bermasalah", file="bom.csv")
            continue
        result.append(bom)
    return result


# ----------------------------------------------------------------------
# Saldo awal
# ----------------------------------------------------------------------
def transform_trial_balance(rows, accounts, config, report):
    """Neraca saldo -> baris jurnal saldo awal, tanpa akun piutang dan hutang usaha."""
    company = config["company"]
    by_code = {account["code"]: account for account in accounts}
    debit_total = credit_total = 0.0
    balances = {}
    for row in rows:
        code = row.get("No. Akun")
        debit, credit = parse_number(row.get("Debit")), parse_number(row.get("Kredit"))
        debit_total += debit
        credit_total += credit
        if code not in by_code:
            report.add("fatal", row, code, "Akun di neraca saldo tidak ada di daftar akun")
            continue
        balances[code] = balances.get(code, 0.0) + debit - credit

    if not _close(debit_total, credit_total):
        report.add(
            "fatal",
            None,
            "neraca_saldo",
            (f"Neraca saldo tidak seimbang: debit {debit_total:,.2f}, kredit {credit_total:,.2f}"),
            file="neraca_saldo.csv",
        )

    lines = []
    for code, balance in balances.items():
        if by_code[code]["account_type"] in ("asset_receivable", "liability_payable") or _close(balance, 0):
            continue
        lines.append(
            {
                "date": company["cutoff_date"],
                "suspense_account_code": company["suspense_account_code"],
                "account_code": code,
                "debit": round(balance, 2) if balance > 0 else 0.0,
                "credit": round(-balance, 2) if balance < 0 else 0.0,
            }
        )
    return lines, balances


def transform_open_items(rows, partner_column, partners, kind, balances, accounts, config, report):
    """Faktur yang belum lunas. Totalnya wajib sama dengan saldo akun di neraca saldo (BR-SALDO-04)."""
    company = config["company"]
    source = config["source"]
    known = {partner["code"] for partner in partners}
    account_type = "asset_receivable" if kind == "receivable" else "liability_payable"
    control = sum(balances.get(a["code"], 0.0) for a in accounts if a["account_type"] == account_type)
    sign = 1 if kind == "receivable" else -1

    result, total = [], 0.0
    numbers = set()
    for row in rows:
        number, partner = row.get("No. Faktur"), row.get(partner_column)
        amount = parse_number(row.get("Sisa"))
        total += amount
        if number in numbers:
            report.add("fatal", row, number, "Nomor faktur muncul dua kali")
            continue
        numbers.add(number)
        if partner not in known:
            report.add("fatal", row, number, f"Kontak {partner} tidak ikut dimigrasi; saldonya akan hilang")
            continue
        if _close(amount, 0):
            report.add("info", row, number, "Sisa nol, dilewati")
            continue
        result.append(
            {
                "date": company["cutoff_date"],
                "suspense_account_code": company["suspense_account_code"],
                "number": number,
                "partner_code": partner,
                "invoice_date": parse_date(row.get("Tanggal"), source["date_format"]),
                "due_date": parse_date(row.get("Jatuh Tempo"), source["date_format"]),
                "amount": round(amount, 2),
            }
        )
    if not _close(total * sign, control):
        report.add(
            "fatal",
            None,
            kind,
            (f"Total faktur terbuka {total:,.2f} tidak sama dengan saldo akun di neraca saldo {abs(control):,.2f}"),
            file=rows[0].file if rows else "",
        )
    return result


def transform_opening_stock(rows, products, warehouses, accounts, balances, report):
    known_products = {product["code"]: product for product in products}
    known_warehouses = {warehouse["code"] for warehouse in warehouses}
    result, total_value = [], 0.0
    for row in rows:
        code, warehouse = row.get("No. Barang"), row.get("Gudang").upper()
        quantity, value = parse_number(row.get("Kuantitas")), parse_number(row.get("Nilai"))
        ref = f"{code}@{warehouse}"
        total_value += value
        if code not in known_products or warehouse not in known_warehouses:
            report.add("fatal", row, ref, "Barang atau gudang tidak ikut dimigrasi; nilai stok akan hilang")
            continue
        if quantity < 0:
            report.add("fatal", row, ref, "Stok minus tidak bisa dimigrasi; selesaikan di Accurate dulu")
            continue
        if _close(quantity, 0):
            report.add("info", row, ref, "Kuantitas nol, dilewati")
            continue
        result.append({"product_code": code, "warehouse_code": warehouse, "quantity": quantity})
    control = sum(balances.get(a["code"], 0.0) for a in accounts if a.get("is_inventory"))
    if not _close(total_value, control):
        report.add(
            "fatal",
            None,
            "stok_awal",
            (f"Nilai stok awal {total_value:,.2f} tidak sama dengan saldo akun persediaan {control:,.2f}"),
            file="stok_awal.csv",
        )
    return result


# ----------------------------------------------------------------------
# Snapshot pembanding untuk rekonsiliasi
# ----------------------------------------------------------------------
def build_source_snapshot(accounts, balances, receivables, payables, stock_rows, products):
    """Angka Accurate yang nanti dibandingkan dengan Odoo. Tanda: debit dikurangi kredit (BR-REK-01)."""
    names = {account["code"]: account["name"] for account in accounts}
    snapshot = [
        {"kind": "account", "key": code, "label": names.get(code), "amount": round(balance, 2)}
        for code, balance in balances.items()
        if not _close(balance, 0)
    ]
    for kind, items, sign in (("receivable", receivables, 1), ("payable", payables, -1)):
        per_partner = defaultdict(float)
        for item in items:
            per_partner[item["partner_code"]] += item["amount"] * sign
        snapshot += [
            {"kind": kind, "key": code, "label": code, "amount": round(amount, 2)}
            for code, amount in per_partner.items()
        ]
    product_names = {product["code"]: product["name"] for product in products}
    values = defaultdict(float)
    for row in stock_rows:
        quantity = parse_number(row.get("Kuantitas"))
        if _close(quantity, 0):
            continue
        code, warehouse = row.get("No. Barang"), row.get("Gudang").upper()
        snapshot.append(
            {"kind": "stock_qty", "key": f"{code}@{warehouse}", "label": product_names.get(code), "amount": quantity}
        )
        values[code] += parse_number(row.get("Nilai"))
    snapshot += [
        {"kind": "stock_value", "key": code, "label": product_names.get(code), "amount": round(value, 2)}
        for code, value in values.items()
    ]
    return snapshot
