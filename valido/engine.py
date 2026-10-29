"""Mesin audit Valido: menjalankan seluruh aturan dan merangkum hasilnya."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .config import (
    EXPECTED_LABEL,
    ROW_SEVERITY_WEIGHT,
    SEVERITY_LABEL,
    normalize_config,
)
from .rules import RULES, Ctx
from .utils import format_value, is_blank, parse_date, parse_number, to_iso_date

FINDING_COLUMNS = [
    "Baris Excel",
    "Kolom",
    "Nilai Bermasalah",
    "Tingkat",
    "Aturan",
    "ID Aturan",
    "Tipe Aturan",
    "Alasan",
    "Saran Perbaikan",
    "Perbaikan Otomatis",
]

STATS_COLUMNS = ["Aturan", "ID Aturan", "Tipe Aturan", "Tingkat", "Baris Terdampak", "Jumlah Temuan", "Status", "Catatan"]

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

GRADE_TABLE = [
    (90, "A", "Sangat baik", "Data siap dipakai."),
    (75, "B", "Baik", "Hanya perlu perbaikan kecil pada beberapa baris."),
    (60, "C", "Cukup", "Perlu pembersihan sebelum dipakai untuk pelaporan."),
    (40, "D", "Buruk", "Banyak masalah kualitas data, prioritaskan perbaikan."),
    (0, "E", "Kritis", "Data belum layak dipakai; audit ulang setelah perbaikan."),
]


@dataclass
class RuleOutcome:
    rule_id: str
    label: str
    type: str
    severity: str
    findings: List[dict] = field(default_factory=list)
    status: str = "Lolos"
    note: str = ""


@dataclass
class AuditResult:
    """Hasil lengkap satu sesi audit."""

    df: pd.DataFrame
    config: dict
    findings: pd.DataFrame
    rule_stats: pd.DataFrame
    summary: dict
    fixed_df: pd.DataFrame
    errors: List[dict] = field(default_factory=list)
    excused: List[dict] = field(default_factory=list)

    # -- properti ringkas -------------------------------------------------- #
    @property
    def total_rows(self) -> int:
        return int(self.summary.get("total_rows", len(self.df)))

    @property
    def total_findings(self) -> int:
        return int(self.summary.get("total_findings", 0))

    @property
    def affected_rows(self) -> int:
        return int(self.summary.get("affected_rows", 0))

    @property
    def score(self) -> float:
        return float(self.summary.get("score", 0.0))

    @property
    def grade(self) -> str:
        return str(self.summary.get("grade", "-"))

    @property
    def grade_label(self) -> str:
        return str(self.summary.get("grade_label", "-"))

    @property
    def counts(self) -> Dict[str, int]:
        return self.summary.get("counts", {"error": 0, "warning": 0, "info": 0})

    def problems_only(self) -> pd.DataFrame:
        return self.findings

    def rows_with_issues(self) -> List[int]:
        return self.summary.get("rows_with_issues", [])


def _grade_for(score: float) -> Tuple[str, str, str]:
    for threshold, grade, label, advice in GRADE_TABLE:
        if score >= threshold:
            return grade, label, advice
    return "E", "Kritis", ""  # pragma: no cover


def _suggest_fix(raw: Any, rule: dict) -> Optional[Any]:
    """Usulan perbaikan otomatis untuk satu sel (None = perlu tindakan manual)."""
    rtype = rule["type"]
    if is_blank(raw):
        return None

    if rtype == "whitespace" and isinstance(raw, str):
        fixed = raw.strip()
        return fixed if fixed != raw else None

    if rtype == "date_format":
        iso = to_iso_date(raw)
        return iso if iso and iso != raw else None

    if rtype == "dtype":
        expected = rule.get("expected")
        if expected in {"number", "integer"}:
            number = parse_number(raw)
            if number is None:
                return None
            return int(number) if float(number).is_integer() else number
        if expected == "date":
            return to_iso_date(raw)
        if expected == "boolean":
            token = str(raw).strip().lower()
            if token in {"ya", "yes", "y", "true", "1", "t", "benar"}:
                return "Ya"
            if token in {"tidak", "no", "n", "false", "0", "salah"}:
                return "Tidak"
        return None

    if rtype == "range":
        number = parse_number(raw)
        if number is None:
            return None
        low, high = rule.get("min"), rule.get("max")
        if low is not None and number < float(low):
            return int(low) if float(low).is_integer() else float(low)
        if high is not None and number > float(high):
            return int(high) if float(high).is_integer() else float(high)
        return None

    if rtype == "allowed_values":
        from .rules import _closest

        return _closest(str(raw).strip(), [str(v) for v in rule.get("values", [])])

    if rtype == "length":
        high = rule.get("max")
        text = str(raw)
        if high is not None and len(text.strip()) > int(high):
            return text.strip()[: int(high)].strip()
        return None

    return None


def _normalize_for_audit(df: pd.DataFrame, trim_strings: bool = False) -> pd.DataFrame:
    """Siapkan salinan dataframe untuk diaudit.

    Valido sengaja **mempertahankan tipe asli** setiap sel (teks tetap teks).
    Jika angka/tanggal tersimpan sebagai teks, itu justru temuan kualitas data
    yang perlu dilaporkan (lihat aturan ``dtype`` dan ``date_format``). Setiap
    aturan melakukan parsing sendiri sesuai kebutuhannya.
    """
    out = df.copy()
    if trim_strings:
        for col in out.columns:
            out[col] = out[col].map(lambda v: v.strip() if isinstance(v, str) else v)
    return out


def run_audit(
    df: pd.DataFrame,
    config: dict | None = None,
    first_data_row_excel: int = 2,
) -> AuditResult:
    """Jalankan seluruh aturan pada ``df``.

    Parameters
    ----------
    df : DataFrame yang akan diaudit.
    config : konfigurasi hasil ``load_config`` / ``normalize_config``.
    first_data_row_excel : nomor baris Excel untuk baris data pertama (default 2,
        karena baris 1 adalah header).
    """
    config = normalize_config(config)
    if not isinstance(df, pd.DataFrame):
        raise TypeError("run_audit membutuhkan pandas.DataFrame.")

    audit_df = _normalize_for_audit(df, bool(config["dataset"].get("trim_strings", False)))
    audit_df.attrs.update(getattr(df, "attrs", {}))

    excel_rows = [first_data_row_excel + i for i in range(len(audit_df))]
    ctx = Ctx(df=audit_df, excel_rows=excel_rows)

    outcomes: List[RuleOutcome] = []
    errors: List[dict] = []

    for rule in config["rules"]:
        outcome = RuleOutcome(
            rule_id=rule["id"],
            label=rule["label"],
            type=rule["type"],
            severity=rule["severity"],
        )
        missing = [c for c in rule["columns"] if c not in audit_df.columns]
        handler = RULES.get(rule["type"])
        if handler is None:  # pragma: no cover - dijaga oleh normalize_config
            outcome.status = "Dilewati"
            outcome.note = f"Tipe aturan '{rule['type']}' belum didukung."
            errors.append({"id": rule["id"], "type": rule["type"], "message": outcome.note})
            outcomes.append(outcome)
            continue
        if missing:
            outcome.status = "Dilewati"
            outcome.note = f"Kolom tidak ditemukan: {', '.join(missing)}."
            errors.append({"id": rule["id"], "type": rule["type"], "message": outcome.note})
            outcomes.append(outcome)
            continue
        try:
            findings = handler(ctx, rule)
        except Exception as exc:  # aturan gagal tidak boleh menghentikan audit
            outcome.status = "Gagal"
            outcome.note = str(exc)
            errors.append({"id": rule["id"], "type": rule["type"], "message": str(exc)})
            outcomes.append(outcome)
            continue

        outcome.findings = findings
        outcome.status = "Bermasalah" if findings else "Lolos"
        outcome.note = f"{len(findings)} temuan"
        outcomes.append(outcome)

    # --- Susun tabel temuan ------------------------------------------------ #
    records: List[dict] = []
    fixes: Dict[Tuple[int, str], Any] = {}
    for outcome, rule in zip(outcomes, config["rules"]):
        for item in outcome.findings:
            severity = item.get("severity") or outcome.severity
            column = item.get("column") or ""
            position = int(item["row"])
            fixed = _suggest_fix(item.get("value"), rule) if column and "," not in column else None
            if fixed is not None and column in audit_df.columns:
                fixes.setdefault((position, column), fixed)
            records.append(
                {
                    "Baris Excel": int(item.get("excel_row", first_data_row_excel + position)),
                    "Kolom": column,
                    "Nilai Bermasalah": format_value(item.get("value"), 150),
                    "Tingkat": SEVERITY_LABEL.get(severity, severity),
                    "Aturan": outcome.label,
                    "ID Aturan": rule["id"],
                    "Tipe Aturan": rule["type"],
                    "Alasan": item.get("reason", ""),
                    "Saran Perbaikan": item.get("suggestion", ""),
                    "Perbaikan Otomatis": "" if fixed is None else format_value(fixed, 60),
                    "_severity": severity,
                    "_position": position,
                }
            )

    if records:
        findings_df = pd.DataFrame.from_records(records)
        order = findings_df["_severity"].map(SEVERITY_ORDER).fillna(9)
        findings_df = (
            findings_df.assign(_order=order)
            .sort_values(["_position", "_order", "ID Aturan"], kind="mergesort")
            .drop(columns=["_order", "_position", "_severity"])
            .reset_index(drop=True)
        )
        findings_df.index = findings_df.index + 1
        findings_df.index.name = "No"
    else:
        findings_df = pd.DataFrame(columns=FINDING_COLUMNS)
        findings_df.index.name = "No"

    # --- Ringkasan per aturan --------------------------------------------- #
    stats_rows = []
    for outcome, rule in zip(outcomes, config["rules"]):
        affected_positions = {int(f["row"]) for f in outcome.findings}
        stats_rows.append(
            {
                "Aturan": rule["label"],
                "ID Aturan": rule["id"],
                "Tipe Aturan": rule["type"],
                "Tingkat": SEVERITY_LABEL.get(outcome.severity, outcome.severity),
                "Baris Terdampak": len(affected_positions),
                "Jumlah Temuan": len(outcome.findings),
                "Status": outcome.status,
                "Catatan": outcome.note,
                "_severity": outcome.severity,
                "_ratio": len(affected_positions) / max(len(audit_df), 1),
            }
        )
    rule_stats = (
        pd.DataFrame(stats_rows)
        if stats_rows
        else pd.DataFrame(columns=STATS_COLUMNS)
    )
    if not rule_stats.empty:
        rule_stats = rule_stats.drop(columns=["_severity", "_ratio"]).reset_index(drop=True)
        rule_stats.index = rule_stats.index + 1
        rule_stats.index.name = "No"

    # --- Skor kesehatan data ---------------------------------------------- #
    # Dihitung dari proporsi baris bermasalah, dibobot tingkat keparahan dan
    # jumlah pelanggaran per baris. Baris tanpa temuan tidak menurunkan skor.
    row_profile: Dict[int, Dict[str, float]] = {}
    severity_rows = {"error": set(), "warning": set(), "info": set()}
    for outcome in outcomes:
        for item in outcome.findings:
            sev = item.get("severity") or outcome.severity
            position = int(item["row"])
            severity_rows.setdefault(sev, set()).add(position)
            entry = row_profile.setdefault(position, {"weight": 0.0, "count": 0})
            entry["weight"] = max(entry["weight"], ROW_SEVERITY_WEIGHT.get(sev, 0.5))
            entry["count"] += 1

    if len(audit_df):
        penalty = sum(rec["weight"] + 0.06 * max(rec["count"] - 1, 0) for rec in row_profile.values()) / len(audit_df)
    else:  # pragma: no cover - dataset kosong ditolak loader
        penalty = 0.0
    score = round(max(0.0, min(100.0, 100.0 * (1.0 - min(1.0, penalty)))), 1)
    grade, grade_label, advice = _grade_for(score)

    counts = {"error": 0, "warning": 0, "info": 0}
    for outcome in outcomes:
        for item in outcome.findings:
            sev = item.get("severity") or outcome.severity
            counts[sev] = counts.get(sev, 0) + 1

    affected_rows_sorted = sorted({int(f["row"]) for outcome in outcomes for f in outcome.findings})
    blank_cells = int(audit_df.map(is_blank).to_numpy().sum()) if len(audit_df) else 0
    empty_columns = [str(c) for c in audit_df.columns if len(audit_df) and audit_df[c].map(is_blank).all()]

    summary = {
        "total_rows": int(len(audit_df)),
        "first_data_row_excel": int(first_data_row_excel),
        "total_cells": int(audit_df.shape[0] * audit_df.shape[1]),
        "total_columns": int(audit_df.shape[1]),
        "columns": [str(c) for c in audit_df.columns],
        "total_findings": int(len(findings_df)),
        "affected_rows": len(affected_rows_sorted),
        "rows_with_issues": [first_data_row_excel + p for p in affected_rows_sorted],
        "counts": counts,
        "rows_by_severity": {k: len(v) for k, v in severity_rows.items()},
        "rules_total": len(config["rules"]),
        "rules_passed": sum(1 for o in outcomes if o.status == "Lolos"),
        "rules_failed": sum(1 for o in outcomes if o.status == "Bermasalah"),
        "rules_skipped": sum(1 for o in outcomes if o.status in {"Dilewati", "Gagal"}),
        "score": score,
        "grade": grade,
        "grade_label": grade_label,
        "advice": advice,
        "blank_cells": blank_cells,
        "empty_columns": empty_columns,
        "auto_fixable": int(len(fixes)),
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    fixed_df = apply_fixes(audit_df, fixes)
    return AuditResult(
        df=audit_df,
        config=config,
        findings=findings_df,
        rule_stats=rule_stats,
        summary=summary,
        fixed_df=fixed_df,
        errors=errors,
    )


def apply_fixes(df: pd.DataFrame, fixes: Dict[Tuple[int, str], Any]) -> pd.DataFrame:
    """Terapkan perbaikan otomatis yang aman ke salinan dataframe."""
    out = df.copy()
    for (position, column), value in fixes.items():
        if column not in out.columns or position >= len(out):
            continue
        index = out.index[position]
        try:
            if pd.api.types.is_numeric_dtype(out[column]) and isinstance(value, str):
                continue
            out.at[index, column] = value
        except (TypeError, ValueError):  # pragma: no cover - pertahanan tipe
            continue
    return out


def explain_rule(rule: dict) -> str:
    """Penjelasan singkat aturan untuk laporan/kartu UI."""
    from .config import RULE_TYPES

    spec = RULE_TYPES.get(rule["type"], {})
    cols = ", ".join(rule.get("columns") or []) or "seluruh kolom"
    return f"{spec.get('label', rule['type'])} — {spec.get('description', '')} (kolom: {cols})"
