"""Implementasi setiap tipe aturan audit.

Setiap fungsi aturan menerima ``(ctx, rule)`` dan mengembalikan daftar temuan
berbentuk dict dengan kunci: ``row`` (posisi baris di dataframe), ``column``,
``value``, ``reason``, ``suggestion``, dan opsional ``severity``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import EXPECTED_LABEL
from .expr import ExprError, evaluate
from .utils import (
    DATE_FORMATS,
    format_value,
    is_blank,
    match_date_format,
    parse_date,
    parse_number,
    to_iso_date,
)

Finding = Dict[str, Any]


@dataclass
class Ctx:
    """Konteks audit: dataframe yang sudah dinormalkan + nomor baris Excel."""

    df: pd.DataFrame
    excel_rows: List[int]

    def row_of(self, position: int) -> int:
        try:
            return self.excel_rows[position]
        except IndexError:  # pragma: no cover - pertahanan
            return position + 2


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:  # pragma: no cover - formatting longgar
        return ""


def render(template: str, **kwargs: Any) -> str:
    """Format template pesan; placeholder yang tidak terisi dibiarkan kosong."""
    try:
        return template.format_map(_SafeDict(kwargs)).strip()
    except (ValueError, IndexError):
        return template


def _finding(
    ctx: Ctx,
    position: int,
    column: Optional[str],
    value: Any,
    reason: str,
    suggestion: str,
    severity: Optional[str] = None,
) -> Finding:
    return {
        "row": position,
        "excel_row": ctx.row_of(position),
        "column": column,
        "value": value,
        "reason": reason,
        "suggestion": suggestion,
        "severity": severity,
    }


def _is_blank(value: Any) -> bool:
    return is_blank(value)


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.map(_is_blank).astype(bool)


_DATE_FORMAT_TOKENS = [
    ("%Y", "YYYY"),
    ("%y", "YY"),
    ("%m", "MM"),
    ("%d", "DD"),
    ("%H", "HH"),
    ("%M", "mm"),
    ("%S", "ss"),
    ("%b", "Mon"),
    ("%B", "NamaBulan"),
]


def _human_date_format(fmt: str) -> str:
    """Ubah pola strptime (mis. %d/%m/%Y) menjadi pola yang mudah dibaca."""
    if fmt == "excel-date":
        return "tanggal Excel (YYYY-MM-DD)"
    human = fmt
    for token, label in _DATE_FORMAT_TOKENS:
        human = human.replace(token, label)
    return human


def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _bounds_text(low: Optional[float], high: Optional[float]) -> str:
    if low is not None and high is not None:
        return f"{_fmt_num(low)} s/d {_fmt_num(high)}"
    if low is not None:
        return f"minimal {_fmt_num(low)}"
    if high is not None:
        return f"maksimal {_fmt_num(high)}"
    return "tanpa batas"


# --------------------------------------------------------------------------- #
# Aturan: kelengkapan
# --------------------------------------------------------------------------- #
def rule_required(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    series = ctx.df[col]
    blanks = _blank_mask(series)
    out: List[Finding] = []
    for pos in range(len(ctx.df)):
        if not blanks.iloc[pos]:
            continue
        out.append(
            _finding(
                ctx,
                pos,
                col,
                series.iloc[pos],
                render(rule["message"], column=col, row=ctx.row_of(pos), value="(kosong)"),
                render(rule["suggestion"], column=col, row=ctx.row_of(pos)),
            )
        )
    return out


def rule_required_if(ctx: Ctx, rule: dict) -> List[Finding]:
    when = rule["when"]
    try:
        condition, undefined = evaluate(when, ctx.df)
    except ExprError as exc:
        raise ValueError(str(exc)) from exc

    out: List[Finding] = []
    for col in rule["columns"]:
        if col not in ctx.df.columns:
            raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
        blanks = _blank_mask(ctx.df[col]).to_numpy()
        for pos in range(len(ctx.df)):
            if undefined.iloc[pos] or not bool(condition.iloc[pos]):
                continue
            if not blanks[pos]:
                continue
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    ctx.df[col].iloc[pos],
                    render(rule["message"], column=col, row=ctx.row_of(pos), when=when),
                    render(rule["suggestion"], column=col, row=ctx.row_of(pos), when=when),
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Aturan: keunikan
# --------------------------------------------------------------------------- #
def rule_unique(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    ignore_case = bool(rule.get("ignore_case", True))
    ignore_ws = bool(rule.get("ignore_whitespace", True))
    series = ctx.df[col]

    keys: Dict[str, List[int]] = {}
    for pos, value in enumerate(series):
        if _is_blank(value):
            continue
        text = str(value)
        if ignore_ws:
            text = text.strip()
        if ignore_case:
            text = text.casefold()
        keys.setdefault(text, []).append(pos)

    out: List[Finding] = []
    for positions in keys.values():
        if len(positions) < 2:
            continue
        rows_text = ", ".join(str(ctx.row_of(p)) for p in positions[:12])
        if len(positions) > 12:
            rows_text += ", ..."
        for pos in positions:
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    series.iloc[pos],
                    render(
                        rule["message"],
                        column=col,
                        row=ctx.row_of(pos),
                        value=format_value(series.iloc[pos]),
                        count=len(positions),
                        rows=rows_text,
                        first_row=ctx.row_of(positions[0]),
                    ),
                    render(
                        rule["suggestion"],
                        column=col,
                        row=ctx.row_of(pos),
                        first_row=ctx.row_of(positions[0]),
                        count=len(positions),
                    ),
                )
            )
    return out


def rule_duplicate(ctx: Ctx, rule: dict) -> List[Finding]:
    df = ctx.df
    columns = rule.get("columns") or []
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Kolom tidak ditemukan pada data: {', '.join(missing)}")
    subset = columns or list(df.columns)
    ignore_case = bool(rule.get("ignore_case", True))

    def key_of(pos: int) -> str:
        parts = []
        for col in subset:
            value = df[col].iloc[pos]
            text = "" if is_blank(value) else str(value).strip()
            if ignore_case:
                text = text.casefold()
            parts.append(text)
        return "\u0001".join(parts)

    groups: Dict[str, List[int]] = {}
    for pos in range(len(df)):
        groups.setdefault(key_of(pos), []).append(pos)

    out: List[Finding] = []
    group_no = 0
    col_text = ", ".join(subset)
    for positions in groups.values():
        if len(positions) < 2:
            continue
        group_no += 1
        rows_text = ", ".join(str(ctx.row_of(p)) for p in positions[:12])
        if len(positions) > 12:
            rows_text += ", ..."
        for pos in positions:
            out.append(
                _finding(
                    ctx,
                    pos,
                    None,
                    " | ".join(format_value(df[c].iloc[pos], 40) for c in subset),
                    render(
                        rule["message"],
                        column=col_text,
                        columns=col_text,
                        row=ctx.row_of(pos),
                        group=group_no,
                        count=len(positions),
                        rows=rows_text,
                        first_row=ctx.row_of(positions[0]),
                    ),
                    render(
                        rule["suggestion"],
                        columns=col_text,
                        row=ctx.row_of(pos),
                        first_row=ctx.row_of(positions[0]),
                        count=len(positions),
                    ),
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Aturan: tanggal
# --------------------------------------------------------------------------- #
def rule_date_format(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    formats = rule.get("formats") or []
    strict = bool(rule.get("strict", True))
    candidate = formats or DATE_FORMATS
    series = ctx.df[col]

    matches: List[Optional[str]] = []
    flexible: List[Optional[pd.Timestamp]] = []
    for value in series:
        if _is_blank(value):
            matches.append(None)
            flexible.append(None)
            continue
        if isinstance(value, (pd.Timestamp,)) or hasattr(value, "year"):
            matches.append("excel-date")
            flexible.append(parse_date(value))
            continue
        text = str(value).strip()
        found = match_date_format(text, candidate)
        matches.append(found)
        flexible.append(parse_date(value) if found is None else None)

    if formats:
        expected = formats[0]
    else:
        counted = [m for m in matches if m and m != "excel-date"]
        expected = pd.Series(counted).mode().iloc[0] if counted else DATE_FORMATS[0]
        if not counted and any(m == "excel-date" for m in matches):
            expected = "excel-date"

    # Contoh nilai untuk saran perbaikan
    example_source = None
    for value, found in zip(series, matches):
        if found == expected and not _is_blank(value):
            example_source = value
            break
    example = to_iso_date(example_source) if example_source is not None else None
    expected_human = _human_date_format(expected)

    out: List[Finding] = []
    for pos, value in enumerate(series):
        if _is_blank(value):
            continue
        found = matches[pos]
        if found == "excel-date":
            # Nilai sudah bertipe tanggal asli (bukan teks) — tidak perlu dirapikan.
            continue
        if found == expected:
            continue
        if found and formats and not strict:
            # Semua format yang terdaftar diizinkan.
            continue
        if found in formats and not strict:
            continue
        if found:
            reason = render(
                rule["message"],
                column=col,
                row=ctx.row_of(pos),
                value=format_value(value),
                found=found,
                expected=expected,
            )
            severity = None
        elif flexible[pos] is not None:
            reason = (
                f"Format tanggal tidak konsisten: {format_value(value)} bisa dibaca sistem "
                f"tetapi tidak mengikuti format baku {expected}."
            )
            severity = None
        else:
            reason = f"Nilai {format_value(value)} bukan tanggal yang valid (tidak bisa dibaca sebagai tanggal)."
            severity = "error"
        suggestion = render(
            rule["suggestion"],
            column=col,
            row=ctx.row_of(pos),
            expected=expected,
            expected_human=expected_human,
            example=example or "-",
            value=format_value(value),
        )
        out.append(_finding(ctx, pos, col, value, reason, suggestion, severity))
    return out


def rule_date_order(ctx: Ctx, rule: dict) -> List[Finding]:
    first, second = rule["columns"]
    for col in (first, second):
        if col not in ctx.df.columns:
            raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    out: List[Finding] = []
    for pos in range(len(ctx.df)):
        a_raw, b_raw = ctx.df[first].iloc[pos], ctx.df[second].iloc[pos]
        a, b = parse_date(a_raw), parse_date(b_raw)
        if is_blank(a_raw) or is_blank(b_raw):
            continue
        if a is None or b is None:
            out.append(
                _finding(
                    ctx,
                    pos,
                    second if b is None else first,
                    b_raw if b is None else a_raw,
                    f"Tanggal pada kolom {second if b is None else first} tidak bisa dibaca sebagai tanggal, "
                    f"sehingga urutan {first} → {second} tidak dapat diperiksa.",
                    f"Perbaiki format tanggal pada baris {ctx.row_of(pos)} menjadi format baku YYYY-MM-DD.",
                    "warning",
                )
            )
            continue
        if b < a:
            out.append(
                _finding(
                    ctx,
                    pos,
                    second,
                    b_raw,
                    render(
                        rule["message"],
                        column=second,
                        columns=f"{first} → {second}",
                        row=ctx.row_of(pos),
                        first=first,
                        second=second,
                        first_value=format_value(a_raw),
                        second_value=format_value(b_raw),
                    ),
                    render(rule["suggestion"], column=second, row=ctx.row_of(pos), first=first, second=second),
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Aturan: angka
# --------------------------------------------------------------------------- #
def rule_range(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    low, high = rule.get("min"), rule.get("max")
    allow_blank = bool(rule.get("allow_blank", True))
    allow_non_numeric = bool(rule.get("allow_non_numeric", False))
    bounds = _bounds_text(low, high)
    out: List[Finding] = []

    for pos, raw in enumerate(ctx.df[col]):
        if _is_blank(raw):
            if allow_blank:
                continue
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    raw,
                    f"Nilai kosong, padahal kolom {col} wajib berisi angka.",
                    f"Isi kolom {col} baris {ctx.row_of(pos)} dengan angka dalam rentang {bounds}.",
                )
            )
            continue
        number = parse_number(raw)
        if number is None:
            if allow_non_numeric:
                continue
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    raw,
                    f"Nilai {format_value(raw)} bukan angka, sehingga tidak bisa diperiksa terhadap rentang {bounds}.",
                    f"Ubah isi kolom {col} baris {ctx.row_of(pos)} menjadi angka saja (tanpa teks atau simbol lain).",
                )
            )
            continue
        too_low = low is not None and number < float(low)
        too_high = high is not None and number > float(high)
        if not (too_low or too_high):
            continue
        direction = "lebih kecil dari batas minimum" if too_low else "lebih besar dari batas maksimum"
        out.append(
            _finding(
                ctx,
                pos,
                col,
                raw,
                render(rule["message"], column=col, row=ctx.row_of(pos), value=format_value(raw), bounds=bounds)
                + f" Nilai tersebut {direction}.",
                render(rule["suggestion"], column=col, row=ctx.row_of(pos), bounds=bounds, value=format_value(raw)),
            )
        )
    return out


def rule_dtype(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    expected = rule.get("expected", "number")
    allow_blank = bool(rule.get("allow_blank", True))
    label = EXPECTED_LABEL.get(expected, expected)
    out: List[Finding] = []
    boolean_tokens = {"ya", "yes", "y", "true", "1", "t", "benar", "tidak", "no", "n", "false", "0", "salah"}

    for pos, raw in enumerate(ctx.df[col]):
        if _is_blank(raw):
            if allow_blank:
                continue
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    raw,
                    f"Nilai kosong, padahal kolom {col} harus bertipe {label}.",
                    f"Isi kolom {col} baris {ctx.row_of(pos)} dengan nilai {label}.",
                )
            )
            continue
        ok = True
        if expected == "number":
            ok = parse_number(raw) is not None
        elif expected == "integer":
            number = parse_number(raw)
            ok = number is not None and float(number).is_integer()
        elif expected == "date":
            ok = parse_date(raw) is not None
        elif expected == "boolean":
            ok = str(raw).strip().lower() in boolean_tokens
        if ok:
            continue
        out.append(
            _finding(
                ctx,
                pos,
                col,
                raw,
                render(rule["message"], column=col, row=ctx.row_of(pos), value=format_value(raw), expected=label),
                render(
                    rule["suggestion"],
                    column=col,
                    row=ctx.row_of(pos),
                    expected_label=label,
                    expected=label,
                ),
            )
        )
    return out


def rule_outlier(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    numbers = ctx.df[col].map(parse_number)
    valid = numbers.dropna()
    if len(valid) < 4:
        return []

    method = rule.get("method", "iqr")
    if method == "zscore":
        mean, std = float(valid.mean()), float(valid.std(ddof=0))
        if std == 0 or pd.isna(std):
            return []
        threshold = float(rule.get("threshold", 3.0))
        low, high = mean - threshold * std, mean + threshold * std
        explanation = f"rata-rata {_fmt_num(mean)} ± {threshold:g}×simpangan baku {_fmt_num(std)}"
    else:
        q1, q3 = float(valid.quantile(0.25)), float(valid.quantile(0.75))
        iqr = q3 - q1
        factor = float(rule.get("factor", 1.5))
        low, high = q1 - factor * iqr, q3 + factor * iqr
        explanation = f"IQR {_fmt_num(q1)}–{_fmt_num(q3)} dengan faktor {factor:g}"

    bounds = f"{_fmt_num(low)} s/d {_fmt_num(high)}"
    out: List[Finding] = []
    for pos, raw in enumerate(ctx.df[col]):
        number = numbers.iloc[pos]
        if pd.isna(number):
            continue
        if low <= float(number) <= high:
            continue
        out.append(
            _finding(
                ctx,
                pos,
                col,
                raw,
                render(rule["message"], column=col, row=ctx.row_of(pos), value=format_value(raw), bounds=bounds)
                + f" Metode {method.upper()}: {explanation}.",
                render(rule["suggestion"], column=col, row=ctx.row_of(pos), bounds=bounds),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Aturan: teks
# --------------------------------------------------------------------------- #
def rule_allowed_values(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    allowed = [str(v) for v in rule.get("values", [])]
    case_sensitive = bool(rule.get("case_sensitive", False))
    allow_blank = bool(rule.get("allow_blank", True))
    lookup = {v if case_sensitive else v.casefold() for v in allowed}
    options = ", ".join(allowed)
    out: List[Finding] = []

    for pos, raw in enumerate(ctx.df[col]):
        if _is_blank(raw):
            if allow_blank:
                continue
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    raw,
                    f"Nilai kosong, padahal kolom {col} wajib salah satu dari: {options}.",
                    f"Isi kolom {col} baris {ctx.row_of(pos)} dengan salah satu nilai baku: {options}.",
                )
            )
            continue
        text = str(raw).strip()
        key = text if case_sensitive else text.casefold()
        if key in lookup:
            continue
        close = _closest(text, allowed)
        hint = f" Mungkin maksudnya \"{close}\"." if close else ""
        out.append(
            _finding(
                ctx,
                pos,
                col,
                raw,
                render(rule["message"], column=col, row=ctx.row_of(pos), value=format_value(raw), options=options)
                + hint,
                render(rule["suggestion"], column=col, row=ctx.row_of(pos), options=options)
                + (f" Nilai terdekat: \"{close}\"." if close else ""),
            )
        )
    return out


def _closest(text: str, options: List[str]) -> Optional[str]:
    from difflib import get_close_matches

    match = get_close_matches(text.casefold(), [o.casefold() for o in options], n=1, cutoff=0.7)
    if not match:
        return None
    for option in options:
        if option.casefold() == match[0]:
            return option
    return None  # pragma: no cover


def rule_pattern(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    regex = re.compile(rule["regex"])
    full_match = bool(rule.get("full_match", True))
    allow_blank = bool(rule.get("allow_blank", True))
    hint = rule.get("hint") or ""
    hint_sentence = f" ({hint})" if hint else ""
    out: List[Finding] = []

    for pos, raw in enumerate(ctx.df[col]):
        if _is_blank(raw):
            if allow_blank:
                continue
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    raw,
                    f"Nilai kosong, padahal kolom {col} wajib diisi{hint_sentence}.",
                    f"Isi kolom {col} baris {ctx.row_of(pos)} sesuai format{hint_sentence}.",
                )
            )
            continue
        text = str(raw).strip()
        matched = regex.fullmatch(text) if full_match else regex.search(text)
        if matched:
            continue
        out.append(
            _finding(
                ctx,
                pos,
                col,
                raw,
                render(rule["message"], column=col, row=ctx.row_of(pos), value=format_value(raw), hint=hint_sentence),
                render(
                    rule["suggestion"],
                    column=col,
                    row=ctx.row_of(pos),
                    hint=hint_sentence,
                    hint_example=hint_sentence,
                )
                + " Hindari spasi ganda atau karakter tak terlihat.",
            )
        )
    return out


def rule_length(ctx: Ctx, rule: dict) -> List[Finding]:
    col = rule["columns"][0]
    if col not in ctx.df.columns:
        raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
    low, high = rule.get("min"), rule.get("max")
    allow_blank = bool(rule.get("allow_blank", True))
    bounds_text = f"{int(low) if low is not None else 0}–{int(high) if high is not None else '∞'} karakter"
    out: List[Finding] = []

    for pos, raw in enumerate(ctx.df[col]):
        if _is_blank(raw):
            if allow_blank:
                continue
        text = "" if _is_blank(raw) else str(raw).strip()
        length = len(text)
        if _is_blank(raw) and not allow_blank:
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    raw,
                    f"Nilai kosong, padahal kolom {col} harus {bounds_text}.",
                    f"Isi kolom {col} baris {ctx.row_of(pos)} dengan {bounds_text}.",
                )
            )
            continue
        too_short = low is not None and length < int(low)
        too_long = high is not None and length > int(high)
        if not (too_short or too_long):
            continue
        out.append(
            _finding(
                ctx,
                pos,
                col,
                raw,
                render(
                    rule["message"],
                    column=col,
                    row=ctx.row_of(pos),
                    length=length,
                    bounds=bounds_text,
                    value=format_value(raw, 60),
                ),
                render(rule["suggestion"], column=col, row=ctx.row_of(pos), bounds=bounds_text, length=length),
            )
        )
    return out


def rule_whitespace(ctx: Ctx, rule: dict) -> List[Finding]:
    out: List[Finding] = []
    for col in rule["columns"]:
        if col not in ctx.df.columns:
            raise ValueError(f"Kolom '{col}' tidak ditemukan pada data.")
        for pos, raw in enumerate(ctx.df[col]):
            if _is_blank(raw) or not isinstance(raw, str):
                continue
            if raw == raw.strip():
                continue
            out.append(
                _finding(
                    ctx,
                    pos,
                    col,
                    raw,
                    render(rule["message"], column=col, row=ctx.row_of(pos), value=format_value(raw, 60)),
                    render(rule["suggestion"], column=col, row=ctx.row_of(pos), value=format_value(raw, 60)),
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Aturan: lintas kolom
# --------------------------------------------------------------------------- #
def rule_business_rule(ctx: Ctx, rule: dict) -> List[Finding]:
    expression = rule["expression"]
    try:
        condition, undefined = evaluate(expression, ctx.df)
    except ExprError as exc:
        raise ValueError(str(exc)) from exc

    out: List[Finding] = []
    for pos in range(len(ctx.df)):
        if undefined.iloc[pos]:
            out.append(
                _finding(
                    ctx,
                    pos,
                    ", ".join(rule["columns"]) or None,
                    "",
                    f"Aturan {expression} tidak dapat diperiksa karena ada nilai kosong pada kolom terkait.",
                    f"Lengkapi nilai yang kosong di baris {ctx.row_of(pos)} agar aturan {expression} bisa diverifikasi.",
                    "warning",
                )
            )
            continue
        if bool(condition.iloc[pos]):
            continue
        out.append(
            _finding(
                ctx,
                pos,
                ", ".join(rule["columns"]) or None,
                _row_summary(ctx, pos),
                render(rule["message"], row=ctx.row_of(pos), expression=expression),
                render(rule["suggestion"], row=ctx.row_of(pos), expression=expression),
            )
        )
    return out


def _row_summary(ctx: Ctx, pos: int, limit: int = 3, max_total: int = 90) -> str:
    """Ringkasan isi baris (dipotong agar tetap ringkas di laporan)."""
    items = []
    for col in list(ctx.df.columns)[:limit]:
        items.append(f"{col}={format_value(ctx.df[col].iloc[pos], 18)}")
    text = "; ".join(items)
    return text if len(text) <= max_total else text[: max_total - 3] + "..."


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
RULES = {
    "required": rule_required,
    "required_if": rule_required_if,
    "unique": rule_unique,
    "duplicate": rule_duplicate,
    "date_format": rule_date_format,
    "date_order": rule_date_order,
    "range": rule_range,
    "dtype": rule_dtype,
    "outlier": rule_outlier,
    "allowed_values": rule_allowed_values,
    "pattern": rule_pattern,
    "length": rule_length,
    "whitespace": rule_whitespace,
    "business_rule": rule_business_rule,
}
