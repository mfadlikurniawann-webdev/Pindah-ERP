from pindah_etl import transform as t
from pindah_etl.extract import SourceRow


def row(data, line=2, file="x.csv"):
    return SourceRow(file, line, data)


def test_npwp_15_digits_becomes_16():
    assert t.normalize_npwp("01.300.066.6-091.000") == ("0013000666091000", None)


def test_npwp_16_digits_without_leading_zero_is_accepted():
    assert t.normalize_npwp("1092837465019283") == ("1092837465019283", None)


def test_npwp_bad_checksum_is_rejected():
    vat, reason = t.normalize_npwp("01.234.567.8-901.000")
    assert vat is None and "checksum" in reason


def test_npwp_wrong_length_is_rejected():
    assert t.normalize_npwp("12345")[1].startswith("NPWP harus")


def test_exact_duplicate_is_dropped_but_conflict_rejects_both():
    report = t.Report()
    rows = [
        row({"Kode": "A", "Nama": "Satu"}, 2),
        row({"Kode": "A", "Nama": "Satu"}, 3),
        row({"Kode": "B", "Nama": "Dua"}, 4),
        row({"Kode": "B", "Nama": "Dua beda"}, 5),
    ]
    kept = t._dedupe(rows, "Kode", report)
    assert [r.get("Kode") for r in kept] == ["A"]
    assert report.count("fixed") == 1 and report.count("rejected") == 1


def test_pkp_without_npwp_is_rejected(config):
    report = t.Report()
    rows = [row({"No. Pelanggan": "C-1", "Nama": "CV X", "NPWP": "", "PKP": "Ya"})]
    assert t.transform_partners(rows, "customer", "No. Pelanggan", config, report) == []
    assert report.count("rejected") == 1


def test_unknown_account_type_is_fatal(config):
    report = t.Report()
    t.transform_accounts([row({"No. Akun": "1", "Nama Akun": "X", "Tipe Akun": "Aneh"})], config, report)
    assert report.has_fatal


def test_trial_balance_skips_receivable_payable_and_flags_imbalance(config):
    report = t.Report()
    accounts = [
        {"code": "1", "account_type": "asset_cash"},
        {"code": "2", "account_type": "asset_receivable"},
        {"code": "3", "account_type": "equity"},
    ]
    rows = [
        row({"No. Akun": "1", "Debit": "100,00", "Kredit": "0"}),
        row({"No. Akun": "2", "Debit": "50,00", "Kredit": "0"}),
        row({"No. Akun": "3", "Debit": "0", "Kredit": "140,00"}),
    ]
    lines, balances = t.transform_trial_balance(rows, accounts, config, report)
    assert {line["account_code"] for line in lines} == {"1", "3"}
    assert balances["2"] == 50
    assert report.has_fatal  # 150 debit vs 140 kredit
