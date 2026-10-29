import pytest

from pindah_etl.extract import parse_date, parse_number


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.250.000,50", 1_250_000.5),
        ("-555.000,00", -555_000.0),
        ("(1.000)", -1000.0),
        ("0,3", 0.3),
        ("5.000", 5000.0),
        ("", 0.0),
    ],
)
def test_parse_number_indonesian_format(text, expected):
    assert parse_number(text) == expected


def test_parse_date():
    assert parse_date("20/08/2026", "%d/%m/%Y") == "2026-08-20"
