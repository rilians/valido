"""Evaluator ekspresi aman untuk aturan bisnis (`business_rule`, `required_if`).

Ekspresi ditulis seperti di pandas::

    harga_jual >= harga_modal
    diskon <= 0.5 * harga_jual
    `Total Bayar` > 0

Evaluasi memakai ``eval`` tanpa akses builtins, setelah nama kolom dipetakan ke
alias internal, sehingga file konfigurasi tidak bisa dipakai menjalankan kode
berbahaya.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, Tuple

import pandas as pd

BACKTICK_RE = re.compile(r"`([^`]+)`")

SAFE_FUNCS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "len": len,
    "str": str,
    "float": float,
    "int": int,
    "bool": bool,
    "sum": sum,
    "isna": pd.isna,
    "notna": pd.notna,
    "to_number": None,  # diisi di _build_env
}

ALLOWED_CONSTANTS = {"True", "False", "None", "nan", "NaN"}


class ExprError(ValueError):
    """Ekspresi tidak bisa dievaluasi terhadap dataset."""


def _build_env(df: pd.DataFrame) -> Tuple[Dict[str, Any], Dict[str, str], str]:
    """Siapkan namespace evaluasi + peta nama kolom -> alias."""
    from .utils import parse_number

    env: Dict[str, Any] = dict(SAFE_FUNCS)
    env["to_number"] = lambda s: s.map(parse_number) if hasattr(s, "map") else parse_number(s)
    env["nan"] = float("nan")
    env["NaN"] = float("nan")
    alias: Dict[str, str] = {}
    for i, col in enumerate(df.columns):
        name = f"_c{i}"
        series = _maybe_numeric(df[col])
        env[name] = series
        alias[str(col)] = name
        if isinstance(col, str) and col.isidentifier() and col not in env:
            env[col] = series
    return env, alias, ""


_NUMERIC_TEXT_RE = re.compile(r"^[-+]?[\d.,]+$")


def _maybe_numeric(series: pd.Series) -> pd.Series:
    """Ubah kolom teks yang seluruh isinya angka ("1.250.000") menjadi numerik.

    Hanya untuk keperluan evaluasi ekspresi; data asli tidak diubah.
    """
    from .utils import is_blank, parse_number

    if pd.api.types.is_numeric_dtype(series):
        return series
    if series.dtype != object:
        return series
    values = [v for v in series.tolist() if not is_blank(v)]
    if not values:
        return series
    numeric_like = all(
        isinstance(v, (int, float)) or (isinstance(v, str) and _NUMERIC_TEXT_RE.match(v.strip()))
        for v in values
    )
    if not numeric_like:
        return series
    return series.map(parse_number)


def prepare_expression(expression: str, alias: Dict[str, str]) -> str:
    """Ganti nama kolom ber-backtick dengan alias yang aman dievaluasi."""

    def repl(match: re.Match) -> str:
        name = match.group(1).strip()
        if name not in alias:
            raise ExprError(f"Kolom '{name}' tidak ditemukan pada data.")
        return alias[name]

    return BACKTICK_RE.sub(repl, expression)


def _check_names(tree: ast.AST, env: Dict[str, Any], expression: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in env and node.id not in ALLOWED_CONSTANTS:
                raise ExprError(
                    f"Nama '{node.id}' tidak dikenal dalam ekspresi '{expression}'. "
                    "Pastikan nama kolom ditulis sama persis (gunakan backtick bila mengandung spasi)."
                )
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ExprError(f"Akses atribut '{node.attr}' tidak diizinkan.")


def evaluate(expression: str, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """Evaluasi ekspresi terhadap ``df``.

    Returns
    -------
    (benar, tidak_terdefinisi) : dua Series boolean sepanjang ``df``.
    """
    expression = (expression or "").strip()
    if not expression:
        raise ExprError("Ekspresi kosong.")

    env, alias, _ = _build_env(df)
    reverse_alias = {v: k for k, v in alias.items()}
    prepared = prepare_expression(expression, alias)

    try:
        tree = ast.parse(prepared, mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"Ekspresi '{expression}' tidak valid: {exc.msg}.") from exc
    _check_names(tree, env, expression)

    try:
        result = eval(compile(tree, "<valido-rule>", "eval"), {"__builtins__": {}}, env)  # noqa: S307
    except ExprError:
        raise
    except Exception as exc:  # pragma: no cover - pesan bergantung tipe error
        raise ExprError(f"Gagal mengevaluasi '{expression}': {exc}") from exc

    if isinstance(result, pd.Series):
        series = result
    elif isinstance(result, (bool, int, float)):
        series = pd.Series([bool(result)] * len(df), index=df.index)
    else:
        raise ExprError(
            f"Ekspresi '{expression}' menghasilkan tipe {type(result).__name__}, bukan kondisi benar/salah."
        )

    if str(series.dtype) == "bool":
        truth = series.astype(bool)
    elif str(series.dtype) == "boolean":
        truth = series.fillna(False).astype(bool)
    elif series.dtype == object:
        unique = set(series.dropna().unique())
        if not unique.issubset({True, False}):
            raise ExprError(
                f"Ekspresi '{expression}' menghasilkan nilai non-logika "
                f"({', '.join(map(str, list(unique)[:3]))}), bukan kondisi benar/salah."
            )
        truth = series.fillna(False).astype(bool)
    else:
        raise ExprError(
            f"Ekspresi '{expression}' menghasilkan tipe {series.dtype}, bukan kondisi benar/salah. "
            "Gunakan operator perbandingan (==, !=, >, <, >=, <=)."
        )

    # Baris yang memuat nilai kosong pada kolom terkait dianggap "tidak terdefinisi"
    # sehingga bisa dilaporkan terpisah sebagai peringatan.
    referenced = {
        reverse_alias.get(node.id, node.id)
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and (node.id in reverse_alias or node.id in df.columns)
    }
    na_mask = pd.Series(False, index=df.index)
    for col in referenced:
        na_mask = na_mask | df[col].isna()

    undefined = truth.isna() | na_mask
    return truth.fillna(False).astype(bool), undefined
