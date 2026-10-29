"""Membaca config.toml (pemetaan) dan .env (koneksi)."""

import os
import tomllib
from pathlib import Path


def load_config(path: Path) -> dict:
    with Path(path).open("rb") as handle:
        return tomllib.load(handle)


def load_env(path: Path) -> dict:
    """Pembaca .env sederhana: KUNCI=nilai per baris. Variabel lingkungan menang."""
    values = {}
    if Path(path).exists():
        for raw in Path(path).read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in list(values):
        values[key] = os.environ.get(key, values[key])
    for key in ("ODOO_URL", "ODOO_DB", "ODOO_API_KEY"):
        if key in os.environ:
            values[key] = os.environ[key]
    return values
