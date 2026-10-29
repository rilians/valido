"""Valido — Automated Excel Data Auditor.

Paket ini berisi mesin audit (rule engine), pembaca file, dan penyusun laporan
Excel untuk memeriksa kualitas dataset Excel/CSV secara otomatis.

Alur pemakaian singkat::

    from valido import load_dataset, load_config, run_audit, build_report

    df = load_dataset("data.xlsx")
    cfg = load_config("valido_config.yaml")
    result = run_audit(df, cfg)
    build_report(result, cfg, "laporan_valido.xlsx")
"""

from __future__ import annotations

from .config import (
    ConfigError,
    RULE_TYPES,
    SEVERITIES,
    default_config,
    load_config,
    normalize_config,
    save_config,
    suggest_rules,
    config_to_yaml,
    config_from_yaml,
)
from .engine import AuditResult, run_audit
from .loader import DatasetError, LoadedDataset, list_sheets, load_dataset, load_dataset_info
from .profile import profile_columns
from .report import (
    build_report,
    export_clean_csv,
    export_findings_csv,
)

__all__ = [
    "AuditResult",
    "ConfigError",
    "DatasetError",
    "LoadedDataset",
    "RULE_TYPES",
    "SEVERITIES",
    "build_report",
    "config_from_yaml",
    "config_to_yaml",
    "default_config",
    "export_clean_csv",
    "export_findings_csv",
    "list_sheets",
    "load_config",
    "load_dataset",
    "load_dataset_info",
    "normalize_config",
    "profile_columns",
    "run_audit",
    "save_config",
    "suggest_rules",
]

__version__ = "1.0.0"
