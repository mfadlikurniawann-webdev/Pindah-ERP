"""Uji seluruh transformasi pada data contoh, termasuk penolakan saat angka tidak bisa dipercaya."""

from conftest import replace_in

from pindah_etl.pipeline import run_transform, write_outputs


def test_sample_data_is_clean_enough_to_load(sample_copy, tmp_path):
    folder, config = sample_copy
    entities, snapshot, report = run_transform(config, folder)
    assert not report.has_fatal, report.issues
    assert len(entities["partner"]) == 6  # C-0004 ditolak, duplikat C-0002 dibuang
    assert len(entities["opening_stock"]) == 8  # baris kuantitas nol dilewati
    suspense = sum(line["debit"] - line["credit"] for line in entities["opening_balance"])
    receivable = sum(item["amount"] for item in entities["opening_receivable"])
    payable = sum(item["amount"] for item in entities["opening_payable"])
    # Jurnal tanpa piutang/hutang selisihnya persis piutang dikurangi hutang (BR-SALDO-03).
    assert round(suspense + receivable - payable, 2) == 0

    write_outputs(entities, snapshot, report, tmp_path / "build")
    assert (tmp_path / "build" / "normalized" / "06_opening_balance.json").exists()
    assert (tmp_path / "build" / "status.json").read_text().count('"fatal": 0') == 1


def test_open_receivables_must_match_trial_balance(sample_copy):
    folder, config = sample_copy
    replace_in(folder / "piutang_outstanding.csv", "1.920.000,00", "1.900.000,00")
    _, _, report = run_transform(config, folder)
    assert any("Total faktur terbuka" in issue.message for issue in report.issues if issue.level == "fatal")


def test_stock_value_must_match_inventory_accounts(sample_copy):
    folder, config = sample_copy
    replace_in(folder / "stok_awal.csv", "BJ-002;DST;400;13.200.000,00", "BJ-002;DST;400;13.000.000,00")
    _, _, report = run_transform(config, folder)
    assert any("Nilai stok awal" in issue.message for issue in report.issues if issue.level == "fatal")


def test_negative_stock_is_fatal(sample_copy):
    folder, config = sample_copy
    replace_in(folder / "stok_awal.csv", "BJ-003;PBK;0;0,00", "BJ-003;PBK;-5;0,00")
    _, _, report = run_transform(config, folder)
    assert any("minus" in issue.message for issue in report.issues if issue.level == "fatal")


def test_receivable_for_rejected_customer_is_fatal(sample_copy):
    folder, config = sample_copy
    replace_in(
        folder / "piutang_outstanding.csv",
        "SI.2026.09.00057;28/09/2026;28/10/2026;C-0003",
        "SI.2026.09.00057;28/09/2026;28/10/2026;C-0004",
    )
    _, _, report = run_transform(config, folder)
    assert any("tidak ikut dimigrasi" in issue.message for issue in report.issues if issue.level == "fatal")
