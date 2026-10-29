"""Test utilitas parsing dan pemformatan."""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from valido.utils import (
    format_value,
    is_blank,
    match_date_format,
    parse_date,
    parse_number,
    to_iso_date,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1250, 1250.0),
        ("1250", 1250.0),
        ("Rp1.250.000", 1_250_000.0),
        ("Rp 1.250.000,50", 1_250_000.5),
        ("1,250,000.75", 1_250_000.75),
        ("1,5", 1.5),
        ("-42", -42.0),
        ("(1.500)", -1500.0),
        ("12%", 0.12),
        ("  7 ", 7.0),
    ],
)
def test_parse_number_valid(raw, expected):
    assert parse_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "abc", "-", None, np.nan, True, "N/A"])
def test_parse_number_invalid(raw):
    assert parse_number(raw) is None


def test_parse_number_ignores_datetime():
    assert parse_number(pd.Timestamp("2025-01-01")) is None


@pytest.mark.parametrize(
    "value",
    [None, np.nan, pd.NaT, "", "   ", "N/A", "null", "None", "-"],
)
def test_is_blank_true(value):
    assert is_blank(value) is True


@pytest.mark.parametrize("value", [0, 0.0, False, "0", "teks", date(2025, 1, 1)])
def test_is_blank_false(value):
    assert is_blank(value) is False


def test_format_value():
    assert format_value(None) == "(kosong)"
    assert format_value(pd.Timestamp("2025-05-01")) == "2025-05-01"
    assert format_value(datetime(2025, 5, 1, 10, 30)) == "2025-05-01 10:30:00"
    assert format_value(5.0) == "5"
    assert format_value("x" * 200, max_len=10) == "xxxxxxx..."


@pytest.mark.parametrize(
    "text,fmt",
    [
        ("2025-01-31", "%Y-%m-%d"),
        ("31/01/2025", "%d/%m/%Y"),
        ("31-01-2025", "%d-%m-%Y"),
        ("31 Jan 2025", "%d %b %Y"),
    ],
)
def test_match_date_format(text, fmt):
    assert match_date_format(text, [fmt]) == fmt


def test_match_date_format_none():
    assert match_date_format("31/02/2025", ["%d/%m/%Y"]) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2025-01-15", "2025-01-15"),
        ("15/01/2025", "2025-01-15"),
        ("15 Jan 2025", "2025-01-15"),
        (pd.Timestamp("2025-01-15"), "2025-01-15"),
        ("2025-01-15 08:30:00", "2025-01-15 08:30:00"),
    ],
)
def test_to_iso_date(raw, expected):
    assert to_iso_date(raw) == expected


def test_parse_date_invalid():
    assert parse_date("bukan tanggal") is None
    assert parse_date("31/02/2025") is None
    assert parse_date(None) is None
