import shutil
import sys
from pathlib import Path

import pytest

ETL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ETL_DIR))

from pindah_etl.settings import load_config  # noqa: E402

SAMPLE_DIR = ETL_DIR.parent / "sample_data" / "accurate_export"


@pytest.fixture
def config():
    return load_config(ETL_DIR / "config.toml")


@pytest.fixture
def sample_copy(tmp_path, config):
    """Salinan data contoh yang boleh dirusak oleh test, beserta config yang menunjuk ke sana."""
    folder = tmp_path / "export"
    shutil.copytree(SAMPLE_DIR, folder)
    config["source"]["folder"] = str(folder)
    return folder, config


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"{old!r} tidak ada di {path.name}"
    path.write_text(text.replace(old, new))
