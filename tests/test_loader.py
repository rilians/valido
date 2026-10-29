"""Test pembacaan file Excel/CSV."""

from __future__ import annotations

import pandas as pd
import pytest

from valido.loader import DatasetError, list_sheets, load_dataset, load_dataset_info


def test_load_csv(csv_file):
    df = load_dataset(csv_file)
    assert df.shape == (6, 9)
    assert list(df.columns)[:2] == ["id", "nama"]


def test_load_csv_with_semicolon(tmp_path):
    path = tmp_path / "titik_koma.csv"
    path.write_text("nama;kota\nAni;Depok\nBudi;Medan\n", encoding="utf-8")
    df = load_dataset(path)
    assert list(df.columns) == ["nama", "kota"]
    assert len(df) == 2


def test_load_csv_with_tab(tmp_path):
    path = tmp_path / "data.tsv"
    path.write_text("nama\tkota\nAni\tDepok\n", encoding="utf-8")
    df = load_dataset(path)
    assert list(df.columns) == ["nama", "kota"]


def test_load_csv_latin1_encoding(tmp_path):
    path = tmp_path / "latin.csv"
    path.write_bytes("nama\nJosé\n".encode("latin-1"))
    loaded = load_dataset_info(path)
    assert loaded.df.loc[0, "nama"] == "José"
    assert loaded.encoding in {"latin-1", "cp1252", "utf-8", "utf-8-sig"}


def test_load_excel_sheet_selection(xlsx_file):
    df = load_dataset(xlsx_file, sheet="Ringkas")
    assert len(df) == 2
    assert list_sheets(xlsx_file) == ["Data", "Ringkas"]


def test_load_excel_unknown_sheet(xlsx_file):
    with pytest.raises(DatasetError, match="tidak ada"):
        load_dataset(xlsx_file, sheet="TidakAda")


def test_list_sheets_for_csv(csv_file):
    assert list_sheets(csv_file) == []


def test_empty_file(tmp_path):
    path = tmp_path / "kosong.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DatasetError):
        load_dataset(path)


def test_missing_file(tmp_path):
    with pytest.raises(DatasetError, match="tidak ditemukan"):
        load_dataset(tmp_path / "hilang.csv")


def test_unsupported_extension(tmp_path):
    path = tmp_path / "data.pdf"
    path.write_bytes(b"%PDF-1.4")
    with pytest.raises(DatasetError, match="tidak didukung"):
        load_dataset(path)


def test_duplicate_and_unnamed_columns(tmp_path):
    path = tmp_path / "aneh.csv"
    path.write_text("nama,nama,,kota\nAni,Budi,x,Depok\n", encoding="utf-8")
    loaded = load_dataset_info(path)
    cols = list(loaded.df.columns)
    assert len(cols) == len(set(cols)) == 4          # nama unik
    assert cols[-1] == "kota"
    assert cols[2].startswith("Kolom_")             # header kosong diberi nama
    assert cols[0].startswith("nama") and cols[1].startswith("nama")


def test_skip_empty_rows_and_columns(tmp_path):
    path = tmp_path / "kosong_baris.csv"
    path.write_text("nama,kota,catatan\nAni,Depok,\n,\nBudi,Medan,\n", encoding="utf-8")
    loaded = load_dataset_info(path)
    assert len(loaded.df) == 2
    assert "catatan" not in loaded.df.columns


def test_kolom_kosong_semua_ditolak(tmp_path):
    path = tmp_path / "hanya_kolom.csv"
    path.write_text("a,b\n,\n", encoding="utf-8")
    with pytest.raises(DatasetError):
        load_dataset(path)


def test_header_row_offset(tmp_path):
    path = tmp_path / "dengan_judul.csv"
    path.write_text("Laporan Penjualan\n\nnama,kota\nAni,Depok\nBudi,Medan\n", encoding="utf-8")
    df = load_dataset(path, header_row=2)
    assert list(df.columns) == ["nama", "kota"]
    assert len(df) == 2


def test_bytes_input(csv_file):
    df = load_dataset(csv_file.read_bytes())
    assert not df.empty


def test_load_from_uploaded_file_like_object(csv_file):
    class FakeUpload:
        name = "unggahan.csv"

        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

    df = load_dataset(FakeUpload(csv_file.read_bytes()))
    assert df.shape[0] == 6


def test_source_metadata_attached(csv_file):
    df = load_dataset(csv_file)
    assert df.attrs["source"]["name"] == "data_uji.csv"


def test_no_trim_by_default_keeps_whitespace(tmp_path):
    path = tmp_path / "spasi.csv"
    path.write_text("nama\n Ani \n", encoding="utf-8")
    assert load_dataset(path).loc[0, "nama"] == " Ani "


def test_trim_option(tmp_path):
    path = tmp_path / "spasi.csv"
    path.write_text("nama\n Ani \n", encoding="utf-8")
    assert load_dataset(path, trim_strings=True).loc[0, "nama"] == "Ani"
