"""Test setiap tipe aturan secara terpisah."""

from __future__ import annotations

import pandas as pd
import pytest

from valido.config import normalize_rule
from valido.rules import RULES, Ctx


def build(df: pd.DataFrame, **rule_kwargs) -> Ctx:
    return Ctx(df=df, excel_rows=[i + 2 for i in range(len(df))])


def run(df: pd.DataFrame, **rule_kwargs):
    rule = normalize_rule(rule_kwargs)
    ctx = Ctx(df=df, excel_rows=[i + 2 for i in range(len(df))])
    return RULES[rule["type"]](ctx, rule), rule


# --------------------------------------------------------------------------- #
# Kelengkapan
# --------------------------------------------------------------------------- #
def test_required_detects_blank_variants():
    df = pd.DataFrame({"nama": ["Ani", "", "  ", "N/A", None, "Budi"]})
    findings, _ = run(df, type="required", columns=["nama"])
    assert [f["excel_row"] for f in findings] == [3, 4, 5, 6]
    assert "kosong" in findings[0]["reason"].lower()
    assert findings[0]["suggestion"]


def test_required_ignores_zero_and_false():
    df = pd.DataFrame({"nilai": [0, False, "0", "x"]})
    findings, _ = run(df, type="required", columns=["nilai"])
    assert findings == []


def test_required_if_only_when_condition_matches():
    df = pd.DataFrame({"status": ["Selesai", "Baru", "Dikirim"], "kirim": [None, None, "2025-01-01"]})
    findings, _ = run(
        df, type="required_if", columns=["kirim"], when="status.isin(['Selesai', 'Dikirim'])"
    )
    assert len(findings) == 1
    assert findings[0]["excel_row"] == 2


def test_required_if_invalid_expression():
    df = pd.DataFrame({"status": ["Selesai"], "kirim": [None]})
    with pytest.raises(ValueError):
        run(df, type="required_if", columns=["kirim"], when="kolom_hantu == 1")


# --------------------------------------------------------------------------- #
# Keunikan
# --------------------------------------------------------------------------- #
def test_unique_case_and_whitespace_insensitive():
    df = pd.DataFrame({"kode": ["A1", "a1 ", "B2", "B3", ""]})
    findings, _ = run(df, type="unique", columns=["kode"])
    assert [f["excel_row"] for f in findings] == [2, 3]
    assert "2 kali" in findings[0]["reason"]


def test_unique_case_sensitive_variant():
    df = pd.DataFrame({"kode": ["A1", "a1"]})
    findings, _ = run(df, type="unique", columns=["kode"], ignore_case=False)
    assert findings == []


def test_unique_ignores_blanks():
    df = pd.DataFrame({"kode": [None, "", "  "], "x": [1, 2, 3]})
    findings, _ = run(df, type="unique", columns=["kode"])
    assert findings == []


def test_duplicate_rows_on_subset():
    df = pd.DataFrame(
        {"nama": ["Ani", "Budi", "Ani"], "produk": ["A", "B", "A"], "total": [1, 2, 3]}
    )
    findings, _ = run(df, type="duplicate", columns=["nama", "produk"])
    assert len(findings) == 2
    assert "duplikat" in findings[0]["reason"].lower()


def test_duplicate_all_columns_when_empty():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    findings, _ = run(df, type="duplicate", columns=[])
    assert len(findings) == 2


def test_duplicate_missing_column_column_error():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="tidak ditemukan"):
        run(df, type="duplicate", columns=["hantu"])


# --------------------------------------------------------------------------- #
# Tanggal
# --------------------------------------------------------------------------- #
def test_date_format_flags_minority_format():
    df = pd.DataFrame({"tgl": ["2025-01-01", "2025-02-02", "03/03/2025", "2025-04-04", "2025-99-99"]})
    findings, rule = run(df, type="date_format", columns=["tgl"], formats=["%Y-%m-%d"])
    rows = [f["excel_row"] for f in findings]
    assert rows == [4, 6]
    assert "tidak konsisten" in findings[0]["reason"]
    assert "bukan tanggal yang valid" in findings[1]["reason"]


def test_date_format_detects_dominant_automatically():
    df = pd.DataFrame({"tgl": ["2025-01-01", "2025-02-02", "2025-03-03", "04/04/2025"]})
    findings, _ = run(df, type="date_format", columns=["tgl"], formats=[])
    assert len(findings) == 1
    assert findings[0]["excel_row"] == 5


def test_date_format_valid_and_strict_mode():
    df = pd.DataFrame({"tgl": ["2025-01-01", "02/01/2025"]})
    findings, _ = run(df, type="date_format", columns=["tgl"], formats=["%Y-%m-%d", "%d/%m/%Y"], strict=False)
    assert findings == []
    findings_strict, _ = run(df, type="date_format", columns=["tgl"], formats=["%Y-%m-%d", "%d/%m/%Y"], strict=True)
    assert len(findings_strict) == 1


def test_date_format_ignores_blanks_and_native_timestamps():
    df = pd.DataFrame({"tgl": [pd.Timestamp("2025-01-01"), None, "2025-01-02"]})
    findings, _ = run(df, type="date_format", columns=["tgl"])
    assert findings == []


def test_date_order():
    df = pd.DataFrame({"pesan": ["2025-01-10", "2025-01-10", "2025-01-10"], "kirim": ["2025-01-12", "2025-01-01", None]})
    findings, _ = run(df, type="date_order", columns=["pesan", "kirim"])
    assert len(findings) == 1
    assert findings[0]["excel_row"] == 3
    assert "lebih awal" in findings[0]["reason"]


def test_date_order_unparseable_value():
    df = pd.DataFrame({"pesan": ["2025-01-10"], "kirim": ["belum dikirim"]})
    findings, _ = run(df, type="date_order", columns=["pesan", "kirim"])
    assert len(findings) == 1
    assert findings[0]["severity"] == "warning"


# --------------------------------------------------------------------------- #
# Angka
# --------------------------------------------------------------------------- #
def test_range_flags_out_of_bounds():
    df = pd.DataFrame({"qty": [-1, 0, 50, 101, 5000]})
    findings, _ = run(df, type="range", columns=["qty"], min=1, max=100)
    assert [f["excel_row"] for f in findings] == [2, 3, 5, 6]
    assert "lebih kecil" in findings[0]["reason"]
    assert "lebih besar" in findings[2]["reason"]


def test_range_handles_text_numbers_and_blanks():
    df = pd.DataFrame({"harga": ["Rp1.500", " 2.000 ", None, "mahal"]})
    findings, _ = run(df, type="range", columns=["harga"], min=1000, max=1500)
    assert len(findings) == 2          # "2.000" (di atas) dan "mahal" (bukan angka)
    assert "bukan angka" in findings[1]["reason"]


def test_range_allow_non_numeric():
    df = pd.DataFrame({"harga": ["Rp1.000", "mahal"]})
    findings, _ = run(df, type="range", columns=["harga"], min=500, max=2000, allow_non_numeric=True)
    assert findings == []


def test_range_blank_not_allowed():
    df = pd.DataFrame({"qty": [None]})
    findings, _ = run(df, type="range", columns=["qty"], min=0, allow_blank=False)
    assert len(findings) == 1
    assert "kosong" in findings[0]["reason"].lower()


def test_dtype_number():
    df = pd.DataFrame({"nilai": ["10", "abc", None, "1.500"]})
    findings, _ = run(df, type="dtype", columns=["nilai"], expected="number")
    assert len(findings) == 1
    assert findings[0]["excel_row"] == 3


def test_dtype_integer_and_date_and_boolean():
    df = pd.DataFrame({"a": ["1", "2.5"], "b": ["2025-01-01", "kemarin"], "c": ["Ya", "mungkin"]})
    findings_int, _ = run(df, type="dtype", columns=["a"], expected="integer")
    assert [f["excel_row"] for f in findings_int] == [3]
    findings_date, _ = run(df, type="dtype", columns=["b"], expected="date")
    assert [f["excel_row"] for f in findings_date] == [3]
    findings_bool, _ = run(df, type="dtype", columns=["c"], expected="boolean")
    assert [f["excel_row"] for f in findings_bool] == [3]


def test_outlier_iqr():
    df = pd.DataFrame({"total": [100, 110, 105, 95, 100, 98, 5000]})
    findings, _ = run(df, type="outlier", columns=["total"], method="iqr", factor=1.5)
    assert len(findings) == 1
    assert findings[0]["excel_row"] == 8
    assert "pencilan" in findings[0]["reason"].lower()


def test_outlier_zscore_and_small_sample():
    df = pd.DataFrame({"total": [10, 11, 10, 12, 400]})
    findings, _ = run(df, type="outlier", columns=["total"], method="zscore", threshold=1.5)
    assert len(findings) == 1
    tiny = pd.DataFrame({"total": [1, 2]})
    findings_tiny, _ = run(tiny, type="outlier", columns=["total"])
    assert findings_tiny == []


# --------------------------------------------------------------------------- #
# Teks
# --------------------------------------------------------------------------- #
def test_allowed_values_with_close_match_hint():
    df = pd.DataFrame({"status": ["Baru", "baru", "Selesai", "Selesaai", ""]})
    findings, _ = run(df, type="allowed_values", columns=["status"], values=["Baru", "Selesai"])
    assert [f["excel_row"] for f in findings] == [5]
    assert "Selesai" in findings[0]["reason"]


def test_allowed_values_case_sensitive():
    df = pd.DataFrame({"status": ["baru"]})
    findings, _ = run(df, type="allowed_values", columns=["status"], values=["Baru"], case_sensitive=True)
    assert len(findings) == 1


def test_allowed_values_blank_not_allowed():
    df = pd.DataFrame({"status": [None]})
    findings, _ = run(df, type="allowed_values", columns=["status"], values=["Baru"], allow_blank=False)
    assert len(findings) == 1


def test_pattern_email():
    df = pd.DataFrame({"email": ["a@b.com", "salah", "a@b", None]})
    findings, _ = run(df, type="pattern", columns=["email"], regex=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", hint="contoh: a@b.com")
    assert [f["excel_row"] for f in findings] == [3, 4]
    assert "a@b.com" in findings[0]["reason"]


def test_pattern_full_match_false():
    df = pd.DataFrame({"kode": ["XX-123", "YY-999"]})
    findings, _ = run(df, type="pattern", columns=["kode"], regex=r"\d{3}", full_match=False)
    assert findings == []


def test_length_bounds():
    df = pd.DataFrame({"nama": ["Al", "Budi Santoso", "x" * 70]})
    findings, _ = run(df, type="length", columns=["nama"], min=3, max=60)
    assert [f["excel_row"] for f in findings] == [2, 4]
    assert "karakter" in findings[0]["reason"]


def test_whitespace_detection():
    df = pd.DataFrame({"nama": ["Ani", " Budi", "Citra ", "Dewi"], "kota": ["Depok ", "Bogor", "Bandung", "Bekasi"]})
    findings, _ = run(df, type="whitespace", columns=["nama", "kota"])
    assert [f["excel_row"] for f in findings] == [3, 4, 2]
    assert all(f["severity"] is None for f in findings)


# --------------------------------------------------------------------------- #
# Lintas kolom
# --------------------------------------------------------------------------- #
def test_business_rule_expression():
    df = pd.DataFrame({"qty": [1, 2], "harga": [1000, 2000], "total": [1000, 5000]})
    findings, _ = run(df, type="business_rule", columns=["qty"], expression="total == qty * harga")
    assert len(findings) == 1
    assert findings[0]["excel_row"] == 3
    assert "total == qty * harga" in findings[0]["reason"]


def test_business_rule_undefined_values_become_warning():
    df = pd.DataFrame({"qty": [1, None], "harga": [1000, 2000], "total": [1000, 2000]})
    findings, _ = run(df, type="business_rule", columns=["qty"], expression="total == qty * harga")
    assert len(findings) == 1
    assert findings[0]["severity"] == "warning"
    assert "tidak dapat diperiksa" in findings[0]["reason"]


def test_rule_numbering_uses_excel_rows():
    df = pd.DataFrame({"nama": [None, None]})
    findings, _ = run(df, type="required", columns=["nama"])
    assert [f["excel_row"] for f in findings] == [2, 3]


def test_missing_column_raises():
    df = pd.DataFrame({"nama": ["Ani"]})
    with pytest.raises(ValueError, match="tidak ditemukan"):
        run(df, type="required", columns=["email"])
