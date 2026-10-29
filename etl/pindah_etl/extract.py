"""Membaca berkas ekspor Accurate dan mengurai format angka serta tanggal Indonesia."""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class SourceRow:
    """Satu baris CSV beserta asalnya, supaya pesan galat bisa menunjuk baris yang tepat."""

    file: str
    line: int
    data: dict[str, str]

    def get(self, column: str) -> str:
        return (self.data.get(column) or "").strip()


def read_csv(folder: Path, filename: str, delimiter: str) -> list[SourceRow]:
    path = Path(folder) / filename
    if not path.exists():
        raise FileNotFoundError(f"Berkas ekspor tidak ditemukan: {path}")
    # utf-8-sig membuang BOM yang sering ditambahkan Excel.
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        reader.fieldnames = [name.strip() for name in reader.fieldnames or []]
        # Baris 1 adalah judul kolom, jadi data mulai di baris 2.
        return [
            SourceRow(filename, index, {key: value for key, value in row.items() if key})
            for index, row in enumerate(reader, start=2)
            if any((value or "").strip() for value in row.values())
        ]


def parse_number(text: str) -> float:
    """Urai angka format Indonesia: titik pemisah ribuan, koma desimal.

    >>> parse_number("1.250.000,50")
    1250000.5
    >>> parse_number("-555.000,00")
    -555000.0
    >>> parse_number("0,3")
    0.3
    """
    text = (text or "").strip().replace(" ", "")
    if not text:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")  # gaya akuntansi: (1.000)
    text = text.strip("()")
    value = float(text.replace(".", "").replace(",", "."))
    return -value if negative else value


def parse_date(text: str, fmt: str) -> str:
    """Kembalikan tanggal ISO (YYYY-MM-DD) dari format ekspor Accurate."""
    return datetime.strptime(text.strip(), fmt).date().isoformat()
