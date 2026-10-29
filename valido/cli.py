#!/usr/bin/env python3
"""Valido CLI — audit kualitas data Excel/CSV dari terminal.

Contoh:
    python cli.py audit examples/data/transaksi_penjualan.xlsx \
        --config configs/contoh_aturan_transaksi.yaml --out hasil/

    python cli.py init examples/data/transaksi_penjualan.xlsx --out aturan.yaml
    python cli.py rules
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import (
    RULE_TYPES,
    ConfigError,
    DatasetError,
    build_report,
    config_to_yaml,
    default_config,
    export_findings_csv,
    list_sheets,
    load_config,
    load_dataset_info,
    run_audit,
    save_config,
    suggest_rules,
)
from .config import SEVERITY_LABEL
from .loader import load_dataset
from .profile import profile_columns, profile_display

BANNER = r"""
 __     __    _ _     _
 \ \   / /_ _| (_) __| | ___
  \ \ / / _` | | |/ _` |/ _ \   VALIDO
   \ V / (_| | | | (_| | (_) |  Automated Excel Data Auditor
    \_/ \__,_|_|_|\__,_|\___/
"""


def cmd_rules(_: argparse.Namespace) -> int:
    print(BANNER)
    print(f"{len(RULE_TYPES)} tipe aturan tersedia:\n")
    for key, spec in RULE_TYPES.items():
        print(f"  • {spec['icon']}  {key:<16} {spec['label']}")
        print(f"     {spec['description']}")
        if spec["fields"]:
            fields = ", ".join(f"{k} ({v.get('type')})" for k, v in spec["fields"].items())
            print(f"     parameter: {fields}")
        print()
    return 0


def cmd_sheets(args: argparse.Namespace) -> int:
    try:
        sheets = list_sheets(args.file)
    except DatasetError as exc:
        print(f"✖ {exc}", file=sys.stderr)
        return 2
    if not sheets:
        print("File CSV tidak memiliki sheet.")
        return 0
    print(f"{len(sheets)} sheet: " + ", ".join(sheets))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    try:
        loaded = load_dataset_info(args.file, sheet=args.sheet)
    except DatasetError as exc:
        print(f"✖ {exc}", file=sys.stderr)
        return 2

    config = default_config(name=f"Draf aturan {loaded.name}")
    config["rules"] = suggest_rules(loaded.df)
    config["dataset"]["sheet"] = loaded.sheet
    out = Path(args.out)
    save_config(config, out)

    print(BANNER)
    print(f"Dataset : {loaded.name} — {loaded.rows} baris × {loaded.columns} kolom")
    print(f"Draf    : {out}  ({len(config['rules'])} aturan usulan)")
    print("\nTinjau dan sesuaikan aturan tersebut, lalu jalankan:")
    print(f"  python cli.py audit {args.file} --config {out}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        loaded = load_dataset_info(
            args.file,
            sheet=args.sheet,
            header_row=args.header_row,
        )
    except DatasetError as exc:
        print(f"✖ {exc}", file=sys.stderr)
        return 2

    print(BANNER)
    print(f"Dataset : {loaded.name}" + (f" [sheet: {loaded.sheet}]" if loaded.sheet else ""))
    print(f"Ukuran  : {loaded.rows} baris × {loaded.columns} kolom")
    for note in loaded.notes:
        print(f"  ℹ {note}")

    try:
        config = load_config(args.config) if args.config else None
    except ConfigError as exc:
        print(f"✖ Konfigurasi tidak valid: {exc}", file=sys.stderr)
        return 2

    if config is None:
        print("\nTidak ada konfigurasi diberikan — memakai aturan usulan otomatis.")
        config = default_config(name=f"Audit otomatis {loaded.name}")
        config["rules"] = suggest_rules(loaded.df)
        auto_path = out_dir / "aturan_otomatis.yaml"
        save_config(config, auto_path)
        print(f"  ℹ Konfigurasi otomatis disimpan: {auto_path}")

    if not config["rules"]:
        print("✖ Tidak ada aturan untuk dijalankan. Buat konfigurasi dengan `python cli.py init`.", file=sys.stderr)
        return 2

    result = run_audit(
        loaded.df,
        config,
        first_data_row_excel=loaded.header_row + 2,
    )

    report_path = out_dir / args.report_name
    build_report(result, report_path, dataset_name=loaded.name, notes=loaded.notes)
    csv_path = export_findings_csv(result, out_dir / "temuan_valido.csv")

    summary = result.summary
    counts = summary["counts"]
    print("\n" + "─" * 68)
    print(f" SKOR KESEHATAN DATA : {summary['score']:.1f}/100  (grade {summary['grade']} — {summary['grade_label']})")
    print(f" Baris diperiksa     : {summary['total_rows']}  |  Bermasalah: {summary['affected_rows']}")
    print(f" Temuan              : {summary['total_findings']}  "
          f"(🔴 {counts['error']} error · 🟠 {counts['warning']} peringatan · 🔵 {counts['info']} info)")
    print(f" Aturan              : {summary['rules_total']} dijalankan, "
          f"{summary['rules_passed']} lolos, {summary['rules_failed']} bermasalah, {summary['rules_skipped']} dilewati")
    print("─" * 68)

    if not result.findings.empty:
        top = (
            result.findings.groupby("Aturan")
            .size()
            .sort_values(ascending=False)
            .head(5)
        )
        print(" Masalah terbanyak:")
        for label, count in top.items():
            print(f"   • {label}: {count} temuan")
        print("\n 5 temuan pertama:")
        preview = result.findings.head(5)
        for _, row in preview.iterrows():
            print(
                f"   baris {row['Baris Excel']:>4} | {row['Tingkat']:<10} | {row['Kolom'] or '-':<18} | "
                f"{str(row['Alasan'])[:70]}"
            )
    else:
        print(" ✅ Tidak ada temuan. Data lolos seluruh aturan.")

    print(f"\n Laporan Excel : {report_path}")
    print(f" Temuan CSV    : {csv_path}")

    if args.profile:
        print("\n PROFIL KOLOM")
        display = profile_display(profile_columns(loaded.df))
        print(display.to_string(index=False))

    if result.errors:
        print("\n ⚠ Aturan yang tidak dapat dijalankan:", file=sys.stderr)
        for error in result.errors:
            print(f"   - {error['id']}: {error['message']}", file=sys.stderr)

    if args.print_config:
        print("\n" + config_to_yaml(result.config))
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    try:
        df = load_dataset(args.file, sheet=args.sheet)
    except DatasetError as exc:
        print(f"✖ {exc}", file=sys.stderr)
        return 2
    print(BANNER)
    print(profile_display(profile_columns(df)).to_string(index=False))
    usulan = suggest_rules(df)
    if usulan:
        print(f"\n{len(usulan)} aturan yang diusulkan untuk dataset ini (pakai `init` untuk menyimpannya).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="valido",
        description="Valido — Automated Excel Data Auditor: periksa kualitas Excel/CSV secara otomatis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="Jalankan audit dan hasilkan laporan Excel")
    p_audit.add_argument("file", help="File Excel (.xlsx/.xlsm) atau CSV")
    p_audit.add_argument("--config", "-c", help="File konfigurasi aturan .yaml/.json")
    p_audit.add_argument("--sheet", "-s", help="Nama sheet untuk file Excel")
    p_audit.add_argument("--header-row", type=int, default=0, help="Indeks baris header (0 = paling atas)")
    p_audit.add_argument("--out", "-o", default="hasil_audit", help="Folder keluaran (default: hasil_audit)")
    p_audit.add_argument("--report-name", default="laporan_valido.xlsx", help="Nama file laporan Excel")
    p_audit.add_argument("--profile", action="store_true", help="Tampilkan profil kolom setelah audit")
    p_audit.add_argument("--print-config", action="store_true", help="Cetak konfigurasi yang dipakai (YAML)")
    p_audit.set_defaults(func=cmd_audit)

    p_init = sub.add_parser("init", help="Buat draf konfigurasi aturan otomatis dari dataset")
    p_init.add_argument("file", help="File Excel atau CSV")
    p_init.add_argument("--sheet", "-s", help="Nama sheet")
    p_init.add_argument("--out", "-o", default="aturan_valido.yaml", help="File konfigurasi keluaran")
    p_init.set_defaults(func=cmd_init)

    p_profile = sub.add_parser("profile", help="Tampilkan profil kolom dataset")
    p_profile.add_argument("file", help="File Excel atau CSV")
    p_profile.add_argument("--sheet", "-s", help="Nama sheet")
    p_profile.set_defaults(func=cmd_profile)

    p_sheets = sub.add_parser("sheets", help="Daftar sheet pada file Excel")
    p_sheets.add_argument("file", help="File Excel")
    p_sheets.set_defaults(func=cmd_sheets)

    p_rules = sub.add_parser("rules", help="Daftar tipe aturan yang tersedia")
    p_rules.set_defaults(func=cmd_rules)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
