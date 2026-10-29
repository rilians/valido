"""Utilitas umum: parsing angka, tanggal, dan pemformatan nilai."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

CURRENCY_CHARS = "Rp$€£¥"
NULL_TOKENS = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "n.a.",
    "null",
    "none",
    "nil",
    "nan",
    "#n/a",
    "#value!",
    "#ref!",
    "(null)",
}

_NUMBER_CLEAN_RE = re.compile(r"[^0-9,.\-+]")


def is_blank(value: Any) -> bool:
    """True jika nilai dianggap kosong (NaN/None/string kosong/penanda null)."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        if value is pd.NaT:
            return True
        if isinstance(value, (pd.Timestamp, datetime, date)):
            return False
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in NULL_TOKENS or value.strip() == ""
    return False


def format_value(value: Any, max_len: int = 120) -> str:
    """Representasi nilai yang ramah dibaca untuk laporan."""
    if is_blank(value):
        return "(kosong)"
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(value)
        if ts.time() == datetime.min.time():
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:,.6g}"
    text = str(value).replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def parse_number(value: Any) -> Optional[float]:
    """Ubah nilai (termasuk teks "Rp1.250.000,50") menjadi float.

    Mendukung format ribuan Indonesia (1.250.000,50) maupun internasional
    (1,250,000.50). Mengembalikan ``None`` bila tidak bisa diinterpretasikan.
    """
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return None

    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    percent = text.endswith("%")
    text = text.strip("()")
    for ch in CURRENCY_CHARS:
        text = text.replace(ch, "")
    text = text.replace("\xa0", " ").replace(" ", "")
    text = _NUMBER_CLEAN_RE.sub("", text)
    if text in {"", "-", "+", ".", ","}:
        return None

    has_comma, has_dot = "," in text, "." in text
    if has_comma and has_dot:
        # Simbol yang muncul terakhir dianggap pemisah desimal.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        # Konvensi Indonesia: koma = desimal, kecuali pola ribuan berulang
        # seperti "1,250,000".
        text = text.replace(",", "") if text.count(",") > 1 else text.replace(",", ".")
    elif has_dot:
        head, _, tail = text.rpartition(".")
        looks_thousands = (
            text.count(".") == 1
            and len(tail) == 3
            and head.lstrip("-+").isdigit()
            and not head.lstrip("-+").startswith("0")
            and len(head.lstrip("-+")) <= 3
        )
        if looks_thousands or text.count(".") > 1:
            text = text.replace(".", "")

    try:
        number = float(text)
    except ValueError:
        return None
    if negative:
        number = -number
    if percent:
        number = number / 100.0
    return number


DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M",
]


def match_date_format(text: str, formats: list[str]) -> Optional[str]:
    """Kembalikan format ``strptime`` pertama yang cocok, atau ``None``."""
    for fmt in formats:
        try:
            datetime.strptime(text, fmt)
            return fmt
        except (ValueError, TypeError):
            continue
    return None


def parse_date(value: Any) -> Optional[pd.Timestamp]:
    """Parse nilai menjadi ``pd.Timestamp`` secara toleran (None bila gagal)."""
    if is_blank(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        ts = pd.Timestamp(value)
        return None if pd.isna(ts) else ts
    text = str(value).strip()
    fmt = match_date_format(text, DATE_FORMATS)
    if fmt:
        try:
            return pd.Timestamp(datetime.strptime(text, fmt))
        except ValueError:
            return None
    try:
        ts = pd.to_datetime(text, errors="raise", dayfirst=True)
        return None if pd.isna(ts) else pd.Timestamp(ts)
    except (ValueError, TypeError, OverflowError):
        return None


def to_iso_date(value: Any) -> Optional[str]:
    """Normalisasi nilai tanggal ke string ISO ``YYYY-MM-DD``."""
    ts = parse_date(value)
    if ts is None:
        return None
    if ts.time() == datetime.min.time():
        return ts.strftime("%Y-%m-%d")
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def is_identifier(name: Any) -> bool:
    return isinstance(name, str) and name.isidentifier() and not name.startswith("_")


def safe_text(value: Any) -> str:
    return "" if value is None else str(value)
