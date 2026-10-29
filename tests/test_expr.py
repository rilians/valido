"""Test evaluator ekspresi aturan bisnis."""

from __future__ import annotations

import pandas as pd
import pytest

from valido.expr import ExprError, evaluate


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "qty": [1, 2, 3],
            "harga": [1000, 2000, 3000],
            "total": [1000, 5000, 8000],
            "Total Bayar": [10, 20, 30],
            "status": ["Selesai", "Dikirim", "Baru"],
        }
    )


def test_evaluate_simple_expression(df):
    truth, undefined = evaluate("total == qty * harga", df)
    assert truth.tolist() == [True, False, False]
    assert not undefined.any()


def test_evaluate_backtick_column(df):
    truth, _ = evaluate("`Total Bayar` >= 20", df)
    assert truth.tolist() == [False, True, True]


def test_evaluate_isin_expression(df):
    truth, _ = evaluate("status.isin(['Selesai', 'Dikirim'])", df)
    assert truth.tolist() == [True, True, False]


def test_evaluate_with_nan_marks_undefined():
    frame = pd.DataFrame({"a": [1, None], "b": [1, 2]})
    truth, undefined = evaluate("a > b", frame)
    assert truth.tolist()[0] is False or truth.tolist()[0] == False  # noqa: E712
    assert undefined.tolist() == [False, True]


def test_evaluate_unknown_column(df):
    with pytest.raises(ExprError, match="tidak dikenal"):
        evaluate("tidak_ada_kolom > 0", df)


def test_evaluate_backtick_unknown_column(df):
    with pytest.raises(ExprError, match="tidak ditemukan"):
        evaluate("`Kolom Hantu` > 0", df)


def test_evaluate_invalid_syntax(df):
    with pytest.raises(ExprError):
        evaluate("total >>>> 1", df)


def test_evaluate_blocks_private_attribute(df):
    with pytest.raises(ExprError, match="tidak diizinkan"):
        evaluate("total.__class__", df)


def test_evaluate_scalar_expression(df):
    truth, undefined = evaluate("1 == 1", df)
    assert truth.all() and not undefined.any()


def test_evaluate_non_boolean_result(df):
    with pytest.raises(ExprError, match="bukan kondisi"):
        evaluate("qty + harga", df)


def test_empty_expression(df):
    with pytest.raises(ExprError):
        evaluate("   ", df)
