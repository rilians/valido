"""Profiling cepat isi dataset (dipakai UI dan saran aturan otomatis)."""

from __future__ import annotations

from typing import Any, List

import pandas as pd

from .utils import is_blank, parse_date, parse_number

PROFILE_LABELS = {
    "kolom": "Kolom",
    "tipe": "Tipe Terdeteksi",
    "terisi": "Terisi",
    "kosong": "Kosong",
    "persen_kosong": "% Kosong",
    "unik": "Nilai Unik",
    "min": "Min",
    "maks": "Maks",
    "contoh": "Contoh Nilai",
}

BOOLEAN_TOKENS = {"ya", "tidak", "yes", "no", "true", "false", "y", "n", "1", "0"}


def detect_type(series: pd.Series, sample: int = 300) -> str:
    """Tebak tipe dominan sebuah kolom: angka, tanggal, boolean, teks, atau campuran."""
    values = [v for v in series.head(sample) if not is_blank(v)]
    if not values:
        return "kosong"
    numeric = sum(1 for v in values if parse_number(v) is not None)
    dates = sum(1 for v in values if parse_date(v) is not None)
    bools = sum(1 for v in values if str(v).strip().lower() in BOOLEAN_TOKENS)
    total = len(values)

    if numeric == total:
        return "angka"
    if dates == total and not numeric == total:
        return "tanggal"
    if bools == total and numeric < total:
        return "boolean"
    if numeric > total * 0.5:
        return "campuran (mayoritas angka)"
    if dates > total * 0.5:
        return "campuran (mayoritas tanggal)"
    return "teks"


def profile_columns(df: pd.DataFrame, sample_values: int = 3) -> pd.DataFrame:
    """Ringkasan per kolom: tipe, kelengkapan, keunikan, dan contoh nilai."""
    rows: List[dict[str, Any]] = []
    total = max(len(df), 1)

    for col in df.columns:
        series = df[col]
        blanks = series.map(is_blank)
        filled = int((~blanks).sum())
        non_blank = series[~blanks]
        tipe = detect_type(series)
        # Min/maks hanya bermakna untuk kolom numerik.
        numbers = non_blank.map(parse_number).dropna() if tipe == "angka" else pd.Series(dtype=float)

        examples = []
        for value in non_blank.head(sample_values * 3):
            text = str(value).strip()
            if text and text not in examples:
                examples.append(text)
            if len(examples) >= sample_values:
                break

        rows.append(
            {
                "kolom": str(col),
                "tipe": tipe,
                "terisi": filled,
                "kosong": int(blanks.sum()),
                "persen_kosong": round(100.0 * int(blanks.sum()) / total, 1),
                "unik": int(non_blank.astype(str).nunique()),
                "min": float(numbers.min()) if len(numbers) else None,
                "maks": float(numbers.max()) if len(numbers) else None,
                "contoh": " | ".join(examples),
            }
        )

    return pd.DataFrame(rows)


def profile_display(profile: pd.DataFrame) -> pd.DataFrame:
    """Versi profil dengan judul kolom bahasa Indonesia untuk ditampilkan."""
    if profile.empty:
        return profile
    return profile.rename(columns=PROFILE_LABELS)[list(PROFILE_LABELS.values())]


def column_value_counts(df: pd.DataFrame, column: str, top: int = 15) -> pd.DataFrame:
    """Frekuensi nilai teratas satu kolom (untuk grafik di UI)."""
    if column not in df.columns:
        return pd.DataFrame(columns=["Nilai", "Jumlah"])
    series = df[column].map(lambda v: "(kosong)" if is_blank(v) else str(v).strip())
    counts = series.value_counts().head(top)
    return pd.DataFrame({"Nilai": counts.index.astype(str), "Jumlah": counts.to_numpy()})
