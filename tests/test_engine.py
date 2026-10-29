"""Test mesin audit: agregasi temuan, skor, statistik, dan perbaikan otomatis."""

from __future__ import annotations

import pandas as pd
import pytest

from valido.config import normalize_config
from valido.engine import FINDING_COLUMNS, STATS_COLUMNS, apply_fixes, run_audit


def test_findings_table_structure(messy_df, sample_config):
    result = run_audit(messy_df, sample_config)
    assert list(result.findings.columns) == FINDING_COLUMNS
    assert result.findings.index.name == "No"
    assert len(result.findings) == result.summary["total_findings"]
    assert result.findings["Baris Excel"].between(2, len(messy_df) + 1).all()


def test_counts_match_summary(messy_df, sample_config):
    result = run_audit(messy_df, sample_config)
    labels = result.findings["Tingkat"].value_counts().to_dict()
    assert result.counts["error"] == labels.get("Error", 0)
    assert result.counts["warning"] == labels.get("Peringatan", 0)
    assert result.counts["info"] == labels.get("Info", 0)
    assert sum(result.counts.values()) == len(result.findings)


def test_rule_stats_structure(messy_df, sample_config):
    result = run_audit(messy_df, sample_config)
    assert list(result.rule_stats.columns) == STATS_COLUMNS
    assert len(result.rule_stats) == len(sample_config["rules"])
    assert set(result.rule_stats["Status"]).issubset({"Lolos", "Bermasalah"})
    total = int(result.rule_stats["Jumlah Temuan"].sum())
    assert total == len(result.findings)


def test_findings_sorted_by_row(messy_df, sample_config):
    result = run_audit(messy_df, sample_config)
    rows = result.findings["Baris Excel"].tolist()
    assert rows == sorted(rows)


def test_required_and_range_findings_present(messy_df, sample_config):
    result = run_audit(messy_df, sample_config)
    email_blanks = result.findings[
        (result.findings["ID Aturan"] == "wajib_email")
    ]
    assert len(email_blanks) == 1
    qty_out = result.findings[result.findings["ID Aturan"] == "qty_rentang"]
    assert sorted(qty_out["Baris Excel"].tolist()) == [3, 7]


def test_business_rule_and_date_order(messy_df, sample_config):
    result = run_audit(messy_df, sample_config)
    assert not result.findings[result.findings["ID Aturan"] == "total_benar"].empty
    urutan = result.findings[result.findings["ID Aturan"] == "urutan_tanggal"]
    assert 6 in urutan["Baris Excel"].tolist()


def test_scores_and_grade(messy_df, sample_config, clean_df, clean_config):
    dirty = run_audit(messy_df, sample_config)
    clean = run_audit(clean_df, clean_config)
    assert 0 <= dirty.score <= 100
    assert dirty.score < clean.score
    assert clean.score == 100.0
    assert clean.grade == "A"
    assert clean.total_findings == 0
    assert dirty.grade in {"A", "B", "C", "D", "E"}
    assert dirty.summary["advice"]


def test_clean_dataset_has_no_findings(clean_df, clean_config):
    result = run_audit(clean_df, clean_config)
    assert result.findings.empty
    assert result.rule_stats["Status"].tolist() == ["Lolos"] * 3
    assert result.affected_rows == 0


def test_missing_column_is_reported_not_raised(messy_df):
    config = normalize_config({"rules": [{"type": "required", "columns": ["kolom_hantu"]}]})
    result = run_audit(messy_df, config)
    assert result.errors and result.errors[0]["id"] == "required_kolom_hantu"
    assert result.rule_stats.iloc[0]["Status"] == "Dilewati"
    assert result.summary["rules_skipped"] == 1


def test_failing_rule_is_reported(messy_df):
    config = normalize_config(
        {"rules": [{"type": "business_rule", "columns": ["qty"], "expression": "kolom_hantu > 0"}]}
    )
    result = run_audit(messy_df, config)
    assert result.errors
    assert result.rule_stats.iloc[0]["Status"] == "Gagal"


def test_auto_fix_applied_to_clean_frame():
    df = pd.DataFrame(
        {
            "nama": ["  Ani ", "Budi"],
            "tanggal": ["05/02/2025", "2025-03-03"],
            "kota": ["bandugn", "Depok"],
            "qty": [500, 5],
        }
    )
    config = normalize_config(
        {
            "rules": [
                {"type": "whitespace", "columns": ["nama"]},
                {"type": "date_format", "columns": ["tanggal"], "formats": ["%Y-%m-%d"]},
                {"type": "allowed_values", "columns": ["kota"], "values": ["Bandung", "Depok"]},
                {"type": "range", "columns": ["qty"], "min": 1, "max": 100},
            ]
        }
    )
    result = run_audit(df, config)
    fixed = result.fixed_df
    assert fixed.loc[0, "nama"] == "Ani"
    assert pd.Timestamp(fixed.loc[0, "tanggal"]) == pd.Timestamp("2025-02-05")
    assert fixed.loc[0, "kota"] == "Bandung"
    assert fixed.loc[0, "qty"] == 100
    assert result.summary["auto_fixable"] >= 4
    assert not result.findings["Perbaikan Otomatis"].isna().all()


def test_apply_fixes_handles_missing_column():
    df = pd.DataFrame({"a": [1]})
    fixed = apply_fixes(df, {(0, "tidak_ada"): 5, (99, "a"): 7})
    assert fixed.loc[0, "a"] == 1


def test_excel_row_offset():
    df = pd.DataFrame({"nama": [None]})
    config = normalize_config({"rules": [{"type": "required", "columns": ["nama"]}]})
    result = run_audit(df, config, first_data_row_excel=5)
    assert result.findings.iloc[0]["Baris Excel"] == 5
    assert result.summary["rows_with_issues"] == [5]


def test_severity_override_per_rule():
    df = pd.DataFrame({"nama": [None]})
    config = normalize_config(
        {"rules": [{"type": "required", "columns": ["nama"], "severity": "info"}]}
    )
    result = run_audit(df, config)
    assert result.counts["info"] == 1
    assert result.counts["error"] == 0


def test_profile_columns_of_result(messy_df, sample_config):
    from valido.profile import profile_columns, profile_display

    result = run_audit(messy_df, sample_config)
    profile = profile_columns(result.df)
    assert len(profile) == result.df.shape[1]
    assert {"kolom", "tipe", "kosong", "unik"}.issubset(profile.columns)
    display = profile_display(profile)
    assert "Kolom" in display.columns and "% Kosong" in display.columns


def test_empty_dataframe_behaviour():
    df = pd.DataFrame(columns=["nama"])
    config = normalize_config({"rules": [{"type": "required", "columns": ["nama"]}]})
    result = run_audit(df, config)
    assert result.findings.empty
    assert result.score == 100.0
