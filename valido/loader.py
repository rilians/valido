"""Pembacaan file Excel/CSV menjadi DataFrame yang siap diaudit."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, List, Optional, Tuple

import pandas as pd

EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}
CSV_SUFFIXES = {".csv", ".txt", ".tsv"}
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")


class DatasetError(ValueError):
    """Dilempar bila file tidak bisa dibaca atau formatnya tidak didukung."""


@dataclass
class LoadedDataset:
    """Hasil pembacaan file beserta metadatanya."""

    df: pd.DataFrame
    name: str
    sheet: Optional[str] = None
    header_row: int = 0
    encoding: Optional[str] = None
    delimiter: Optional[str] = None
    notes: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []

    @property
    def rows(self) -> int:
        return int(self.df.shape[0])

    @property
    def columns(self) -> int:
        return int(self.df.shape[1])


# --------------------------------------------------------------------------- #
# Utilitas internal
# --------------------------------------------------------------------------- #
def _as_source(source: Any) -> Tuple[Any, str, str]:
    """Kembalikan (buffer/path, nama file, ekstensi) dari berbagai jenis input."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise DatasetError(f"File tidak ditemukan: {path}")
        if path.stat().st_size == 0:
            raise DatasetError(f"File kosong: {path.name}")
        return path, path.name, path.suffix.lower()

    name = getattr(source, "name", None) or "dataset.csv"
    suffix = Path(name).suffix.lower()

    if isinstance(source, (bytes, bytearray)):
        return io.BytesIO(bytes(source)), name, suffix
    if hasattr(source, "getvalue"):
        data = source.getvalue()
        return io.BytesIO(data), name, suffix
    if hasattr(source, "read"):
        data = source.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not data:
            raise DatasetError(f"File {name} kosong.")
        return io.BytesIO(data), name, suffix
    raise DatasetError("Sumber data harus berupa path, bytes, atau file yang diunggah.")


def _clean_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    notes: List[str] = []
    df = df.copy()
    renamed = []
    seen: dict[str, int] = {}
    for i, col in enumerate(df.columns):
        name = str(col).strip()
        if name == "" or name.lower().startswith("unnamed:") or name.lower() == "nan":
            name = f"Kolom_{i + 1}"
            notes.append(f"Kolom tanpa nama pada posisi {i + 1} dinamai '{name}'.")
        if name in seen:
            seen[name] += 1
            new_name = f"{name}_{seen[name]}"
            notes.append(f"Nama kolom '{name}' berulang, yang kedua dinamai '{new_name}'.")
            name = new_name
        else:
            seen[name] = 1
        renamed.append(name)
    df.columns = renamed
    return df, notes


def _detect_encoding(raw: bytes) -> str:
    for encoding in CSV_ENCODINGS:
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample[:8192], delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in [",", ";", "\t", "|"]}
        return max(counts, key=counts.get) if max(counts.values()) > 0 else ","


def _detect_header_row(path_or_buffer: Any, sheet: Optional[str] = None, suffix: str = ".csv") -> int:
    """Tebak baris header: baris pertama yang punya >= 2 sel terisi & unik."""
    try:
        if suffix in EXCEL_SUFFIXES:
            preview = pd.read_excel(path_or_buffer, sheet_name=sheet or 0, header=None, nrows=6)
        else:
            if hasattr(path_or_buffer, "seek"):
                path_or_buffer.seek(0)
            raw = path_or_buffer.read() if hasattr(path_or_buffer, "read") else b""
            text = raw.decode(_detect_encoding(raw)) if isinstance(raw, bytes) else str(raw)
            delimiter = _detect_delimiter(text)
            preview = pd.read_csv(io.StringIO(text), header=None, nrows=6, sep=delimiter)
    except Exception:  # pragma: no cover - preview hanya upaya terbaik
        return 0
    for i in range(min(5, len(preview))):
        values = [str(v).strip() for v in preview.iloc[i].tolist() if str(v).strip() not in {"", "nan"}]
        if len(values) >= 2 and len(set(values)) == len(values):
            return i
    return 0


# --------------------------------------------------------------------------- #
# API publik
# --------------------------------------------------------------------------- #
def list_sheets(source: Any) -> List[str]:
    """Daftar nama sheet untuk file Excel (list kosong untuk CSV)."""
    buffer, name, suffix = _as_source(source)
    if suffix not in EXCEL_SUFFIXES:
        return []
    try:
        with pd.ExcelFile(buffer, engine="openpyxl") as xls:
            return [str(s) for s in xls.sheet_names]
    except Exception as exc:
        raise DatasetError(f"Gagal membaca daftar sheet dari {name}: {exc}") from exc


def load_dataset(
    source: Any,
    sheet: Optional[str] = None,
    header_row: Optional[int] = None,
    trim_strings: bool = False,
    skip_empty_rows: bool = True,
    drop_empty_columns: bool = True,
) -> pd.DataFrame:
    """Baca file Excel/CSV menjadi DataFrame bersih (kolom unik, tanpa baris kosong)."""
    return load_dataset_info(
        source,
        sheet=sheet,
        header_row=header_row,
        trim_strings=trim_strings,
        skip_empty_rows=skip_empty_rows,
        drop_empty_columns=drop_empty_columns,
    ).df


def load_dataset_info(
    source: Any,
    sheet: Optional[str] = None,
    header_row: Optional[int] = None,
    trim_strings: bool = False,
    skip_empty_rows: bool = True,
    drop_empty_columns: bool = True,
) -> LoadedDataset:
    """Seperti :func:`load_dataset`, tetapi mengembalikan juga metadata file."""
    buffer, name, suffix = _as_source(source)
    notes: List[str] = []

    if suffix in EXCEL_SUFFIXES:
        if header_row is None:
            header_row = 0
        try:
            if hasattr(buffer, "seek"):
                buffer.seek(0)
            sheets = list_sheets(buffer)
            if hasattr(buffer, "seek"):
                buffer.seek(0)
            target = sheet or (sheets[0] if sheets else 0)
            if sheet and sheets and sheet not in sheets:
                raise DatasetError(f"Sheet '{sheet}' tidak ada. Tersedia: {', '.join(sheets)}.")
            df = pd.read_excel(
                buffer,
                sheet_name=target,
                header=header_row,
                engine="openpyxl",
                dtype=object,
            )
            if isinstance(df, dict):  # pragma: no cover - pengaman multi-sheet
                df = next(iter(df.values()))
            encoding = delimiter = None
            sheet_name = str(target)
            if len(sheets) > 1:
                notes.append(f"File memiliki {len(sheets)} sheet; sheet '{target}' yang diaudit.")
        except DatasetError:
            raise
        except Exception as exc:
            raise DatasetError(
                f"Gagal membaca file Excel {name}: {exc}. Pastikan file tidak rusak dan tidak berpassword."
            ) from exc
    elif suffix in CSV_SUFFIXES or suffix == "":
        if hasattr(buffer, "seek"):
            buffer.seek(0)
        raw = buffer.read() if hasattr(buffer, "read") else Path(buffer).read_bytes()
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        encoding = _detect_encoding(raw)
        text = raw.decode(encoding, errors="replace")
        if text.strip() == "":
            raise DatasetError(f"File {name} tidak berisi data.")
        delimiter = "\t" if suffix == ".tsv" else _detect_delimiter(text)
        if header_row is None:
            header_row = 0
        try:
            df = pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                header=header_row,
                dtype=object,
                engine="python",
                # Bila header bukan baris pertama, indeks header harus menghitung
                # semua baris apa adanya (termasuk baris kosong).
                skip_blank_lines=(header_row == 0),
            )
        except Exception as exc:
            raise DatasetError(f"Gagal membaca file CSV {name}: {exc}") from exc
        sheet_name = None
        if delimiter != ",":
            notes.append(f"Pemisah kolom terdeteksi '{delimiter}'.")
        if encoding not in {"utf-8", "utf-8-sig"}:
            notes.append(f"Encoding file terdeteksi {encoding}; karakter khusus mungkin berubah.")
    else:
        raise DatasetError(
            f"Format {suffix or '(tanpa ekstensi)'} tidak didukung. Gunakan Excel (.xlsx/.xlsm) atau CSV."
        )

    if df.empty and len(df.columns) == 0:
        raise DatasetError(f"File {name} tidak berisi tabel yang bisa dibaca.")

    df, rename_notes = _clean_columns(df)
    notes.extend(rename_notes)

    if trim_strings:
        for col in df.columns:
            df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

    if skip_empty_rows:
        before = len(df)
        df = df.dropna(how="all")
        # Baris yang isinya hanya string kosong juga dibuang.
        mask_blank = df.apply(lambda row: all(_blank(v) for v in row), axis=1) if len(df) else pd.Series(dtype=bool)
        if len(df):
            df = df[~mask_blank]
        removed = before - len(df)
        if removed:
            notes.append(f"{removed} baris kosong diabaikan.")

    if drop_empty_columns and len(df):
        empty_cols = [c for c in df.columns if df[c].map(_blank).all()]
        if empty_cols and len(empty_cols) < len(df.columns):
            df = df.drop(columns=empty_cols)
            notes.append(f"Kolom tanpa isi diabaikan: {', '.join(map(str, empty_cols))}.")

    df = df.reset_index(drop=True)
    if df.shape[0] == 0:
        raise DatasetError("Tabel berhasil dibaca tetapi tidak ada baris data untuk diaudit.")
    if df.shape[1] == 0:
        raise DatasetError("Tabel tidak memiliki kolom yang bisa diaudit.")

    df.attrs["source"] = {
        "name": name,
        "sheet": sheet_name,
        "header_row": header_row,
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
    }
    return LoadedDataset(
        df=df,
        name=name,
        sheet=sheet_name,
        header_row=int(header_row or 0),
        encoding=encoding,
        delimiter=delimiter,
        notes=notes,
    )


def _blank(value: Any) -> bool:
    from .utils import is_blank

    return is_blank(value)
