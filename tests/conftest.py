"""Fixture bersama untuk seluruh test Valido."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from valido.config import normalize_config  # noqa: E402


@pytest.fixture
def messy_df() -> pd.DataFrame:
    """Dataset kecil dengan beragam masalah kualitas data."""
    return pd.DataFrame(
        {
            "id": ["A1", "A2", "A3", "A4", "A5", "A6"],
            "nama": ["Ani", "Budi", "Budi ", "  ", "Citra", "Dewi"],
            "email": [
                "ani@mail.com",
                "budi@mail,com",
                None,
                "x@y.co",
                "citra@mail.com",
                "dewi@mail.com",
            ],
            "tanggal": ["2025-01-01", "01/02/2025", "2025-03-03", "2025-04-04", "2025-13-13", "2025-06-06"],
            "qty": [1, -2, 3, 4, 5, 10_000],
            "harga": [1000, 2000, 3000, 4000, 5000, 6000],
            "total": [1000, 4000, 9000, 16_000, 25_000, 60_000_000],
            "status": ["Selesai", "Baru", "selesai", "Baru", "Dikirim", None],
            "kirim": ["2025-01-02", None, None, None, "2025-01-01", None],
        }
    )


@pytest.fixture
def sample_config() -> dict:
    return normalize_config(
        {
            "meta": {"name": "Konfigurasi uji"},
            "rules": [
                {"id": "wajib_nama", "type": "required", "columns": ["nama"]},
                {"id": "wajib_email", "type": "required", "columns": ["email"]},
                {"id": "unik_id", "type": "unique", "columns": ["id"]},
                {"id": "tanggal_baku", "type": "date_format", "columns": ["tanggal"], "severity": "warning"},
                {"id": "qty_rentang", "type": "range", "columns": ["qty"], "min": 1, "max": 100},
                {"id": "status_baku", "type": "allowed_values", "columns": ["status"], "values": ["Baru", "Dikirim", "Selesai"]},
                {"id": "email_pola", "type": "pattern", "columns": ["email"], "regex": r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"},
                {"id": "spasi", "type": "whitespace", "columns": ["nama"], "severity": "info"},
                {"id": "total_benar", "type": "business_rule", "columns": ["qty", "harga", "total"], "expression": "total == qty * harga"},
                {"id": "kirim_wajib", "type": "required_if", "columns": ["kirim"], "when": "status.isin(['Dikirim', 'Selesai'])"},
                {"id": "urutan_tanggal", "type": "date_order", "columns": ["tanggal", "kirim"]},
                {"id": "duplikat_nama", "type": "duplicate", "columns": ["nama"], "severity": "warning"},
            ],
        }
    )


@pytest.fixture
def clean_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ["A1", "A2", "A3"],
            "nama": ["Ani", "Budi", "Citra"],
            "email": ["ani@mail.com", "budi@mail.com", "citra@mail.com"],
            "qty": [1, 2, 3],
            "harga": [1000, 2000, 3000],
            "total": [1000, 4000, 9000],
        }
    )


@pytest.fixture
def clean_config() -> dict:
    return normalize_config(
        {
            "rules": [
                {"id": "wajib_id", "type": "required", "columns": ["id"]},
                {"id": "unik_id", "type": "unique", "columns": ["id"]},
                {"id": "total_benar", "type": "business_rule", "columns": ["qty", "harga", "total"], "expression": "total == qty * harga"},
            ]
        }
    )


@pytest.fixture
def csv_file(tmp_path: Path, messy_df: pd.DataFrame) -> Path:
    path = tmp_path / "data_uji.csv"
    messy_df.to_csv(path, index=False)
    return path


@pytest.fixture
def xlsx_file(tmp_path: Path, messy_df: pd.DataFrame) -> Path:
    path = tmp_path / "data_uji.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        messy_df.to_excel(writer, sheet_name="Data", index=False)
        messy_df.head(2).to_excel(writer, sheet_name="Ringkas", index=False)
    return path


@pytest.fixture
def config_file(tmp_path: Path, sample_config: dict) -> Path:
    from valido.config import save_config

    path = tmp_path / "aturan.yaml"
    save_config(sample_config, path)
    return path
