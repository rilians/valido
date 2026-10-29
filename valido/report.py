"""Penyusun laporan Excel hasil audit Valido (OpenPyXL)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.worksheet import Worksheet

from .config import SEVERITY_ICON, SEVERITY_LABEL
from .profile import PROFILE_LABELS, profile_columns

# --------------------------------------------------------------------------- #
# Palet & gaya
# --------------------------------------------------------------------------- #
NAVY = "0F2C4C"
TEAL = "127475"
TEAL_LIGHT = "D9EEEF"
INK = "1F2937"
GREY = "6B7280"
BORDER_GREY = "D1D5DB"
WHITE = "FFFFFF"

SEVERITY_FILL = {
    "Error": "FDE2E1",
    "Peringatan": "FDF0D5",
    "Info": "E3EFFB",
}
SEVERITY_FONT = {
    "Error": "9B1C1C",
    "Peringatan": "8A5300",
    "Info": "1D4ED8",
}
GRADE_FILL = {"A": "D1FAE5", "B": "E0F2FE", "C": "FEF3C7", "D": "FFE4E6", "E": "FECACA"}

THIN = Side(style="thin", color=BORDER_GREY)
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", start_color=color, end_color=color)


def _write_title(ws: Worksheet, row: int, text: str, span: int = 8, size: int = 16) -> int:
    ws.cell(row=row, column=1, value=text)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    cell = ws.cell(row=row, column=1)
    cell.font = Font(bold=True, size=size, color=WHITE)
    cell.fill = _fill(NAVY)
    cell.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[row].height = 26 if size >= 14 else 22
    return row + 1


def _write_section(ws: Worksheet, row: int, text: str, span: int = 8) -> int:
    ws.cell(row=row, column=1, value=text)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    cell = ws.cell(row=row, column=1)
    cell.font = Font(bold=True, size=11, color=NAVY)
    cell.fill = _fill(TEAL_LIGHT)
    cell.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[row].height = 20
    return row + 1


def _write_note(ws: Worksheet, row: int, text: str, span: int = 8, italic: bool = True) -> int:
    ws.cell(row=row, column=1, value=text)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    cell = ws.cell(row=row, column=1)
    cell.font = Font(size=9, italic=italic, color=GREY)
    cell.alignment = Alignment(vertical="center", wrap_text=False, indent=1)
    return row + 1


def _write_table(
    ws: Worksheet,
    df: pd.DataFrame,
    start_row: int,
    start_col: int = 1,
    with_index: bool = False,
    severity_col: Optional[str] = None,
    widths: Optional[Sequence[int]] = None,
    auto_filter: bool = True,
    wrap_columns: Iterable[str] = (),
    freeze: bool = True,
) -> int:
    """Tulis DataFrame ke worksheet lengkap dengan header dan format dasar."""
    if df is None or df.empty:
        return start_row

    frame = df.reset_index() if with_index else df.copy()
    index_label = df.index.name or "No"
    if with_index:
        frame = frame.rename(columns={frame.columns[0]: index_label})

    headers = [str(c) for c in frame.columns]
    wrap_set = set(wrap_columns)

    for j, header in enumerate(headers):
        cell = ws.cell(row=start_row, column=start_col + j, value=header)
        cell.font = Font(bold=True, color=WHITE, size=10)
        cell.fill = _fill(TEAL)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BOX
    ws.row_dimensions[start_row].height = 30

    for i, record in enumerate(frame.itertuples(index=False), start=1):
        excel_row = start_row + i
        for j, value in enumerate(record):
            header = headers[j]
            cell = ws.cell(row=excel_row, column=start_col + j, value=value)
            cell.border = BOX
            cell.font = Font(size=10, color=INK)
            wrap = header in wrap_set
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=wrap,
                horizontal="left" if isinstance(value, str) else "center" if value is not None else "left",
            )
            if severity_col and header == severity_col and isinstance(value, str):
                for label in SEVERITY_FILL:
                    if label in value:
                        cell.fill = _fill(SEVERITY_FILL[label])
                        cell.font = Font(size=10, bold=True, color=SEVERITY_FONT[label])
                        break
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if isinstance(value, float) and not float(value).is_integer():
                    cell.number_format = "#,##0.00"
                else:
                    cell.number_format = "#,##0"

    # Perkirakan tinggi baris untuk kolom yang di-wrap agar teks panjang tetap terbaca.
    if wrap_columns and widths:
        wrap_index = {headers.index(name): widths[headers.index(name)] for name in wrap_columns if name in headers}
        for i, record in enumerate(frame.itertuples(index=False), start=1):
            lines = 1
            for j, width in wrap_index.items():
                text = "" if record[j] is None else str(record[j])
                lines = max(lines, -(-len(text) // max(int(width) - 2, 8)))
            ws.row_dimensions[start_row + i].height = min(max(15, 13.5 * min(lines, 9)), 130)

    last_row = start_row + len(frame)
    if auto_filter and len(frame) > 0:
        ws.auto_filter.ref = (
            f"{get_column_letter(start_col)}{start_row}:"
            f"{get_column_letter(start_col + len(headers) - 1)}{last_row}"
        )
    if freeze:
        ws.freeze_panes = ws.cell(row=start_row + 1, column=start_col)

    if widths:
        for j, width in enumerate(widths):
            ws.column_dimensions[get_column_letter(start_col + j)].width = width

    return last_row + 2


def _merged_coordinates(ws: Worksheet) -> set[str]:
    coords: set[str] = set()
    for rng in ws.merged_cells.ranges:
        for row in ws.iter_rows(min_row=rng.min_row, max_row=rng.max_row, min_col=rng.min_col, max_col=rng.max_col):
            for cell in row:
                coords.add(cell.coordinate)
    return coords


def _setup_print(ws: Worksheet, landscape: bool = True) -> None:
    """Siapkan halaman agar laporan rapi saat dicetak/diekspor ke PDF."""
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5


def _autofit(ws: Worksheet, caps: dict[str, int] | None = None, default: int = 22) -> None:
    """Sesuaikan lebar kolom berdasarkan isi sel (sel gabungan diabaikan)."""
    caps = caps or {}
    merged = _merged_coordinates(ws)
    for column_cells in ws.columns:
        letter = get_column_letter(column_cells[0].column)
        longest = 0
        for cell in column_cells[:400]:
            if cell.value is None or cell.coordinate in merged:
                continue
            longest = max(longest, min(len(str(cell.value)), caps.get(letter, 60)))
        ws.column_dimensions[letter].width = max(9, min(default if longest == 0 else longest + 2, caps.get(letter, 60)))


# --------------------------------------------------------------------------- #
# Lembar: Ringkasan
# --------------------------------------------------------------------------- #
def _recommendations(result) -> List[str]:
    if result.findings.empty:
        return ["Tidak ada masalah yang ditemukan. Data lolos seluruh aturan yang dikonfigurasi."]
    grouped = (
        result.findings.groupby(["Aturan", "ID Aturan"], sort=False)
        .agg(jumlah=("Baris Excel", "size"), baris=("Baris Excel", lambda s: sorted(set(s))[:5]))
        .reset_index()
        .sort_values("jumlah", ascending=False)
    )
    out: List[str] = []
    for _, row in grouped.head(6).iterrows():
        contoh = ", ".join(str(r) for r in row["baris"])
        out.append(f"{row['Aturan']}: {row['jumlah']} temuan — periksa baris {contoh}.")
    return out


def _sheet_summary(ws: Worksheet, result, dataset_name: str, notes: List[str], span: int = 8) -> None:
    summary = result.summary
    ws.sheet_view.showGridLines = False
    row = _write_title(ws, 1, "LAPORAN AUDIT KUALITAS DATA — VALIDO", span=span)
    subtitle = (
        f"File: {dataset_name}   |   Baris: {summary['total_rows']:,}   |   Kolom: {summary['total_columns']}   |   "
        f"Dibuat: {summary['generated_at']}   |   Auditor: {result.config['report'].get('auditor', 'Valido')}"
    ).replace(",", ".")
    row = _write_note(ws, row, subtitle, span=span, italic=False)

    # Kartu KPI
    kpis = [
        ("SKOR KESEHATAN DATA", f"{summary['score']:.1f} / 100", f"Grade {summary['grade']} — {summary['grade_label']}"),
        ("TOTAL BARIS", f"{summary['total_rows']:,}".replace(",", "."), f"{summary['total_columns']} kolom"),
        ("BARIS BERMASALAH", f"{summary['affected_rows']:,}".replace(",", "."), f"{_pct(summary['affected_rows'], summary['total_rows'])} dari total baris"),
        ("TOTAL TEMUAN", f"{summary['total_findings']:,}".replace(",", "."), f"{summary['rules_total']} aturan dijalankan"),
        ("PERBAIKAN OTOMATIS", f"{summary['auto_fixable']:,}".replace(",", "."), "tersedia di sheet Data_Bersih"),
    ]
    row += 1
    for j, (label, value, note) in enumerate(kpis):
        col = 1 + j * 2 if span >= 10 else 1 + j
        target_col = 1 + j * 2
        ws.merge_cells(start_row=row, start_column=target_col, end_row=row, end_column=target_col + 1)
        cell = ws.cell(row=row, column=target_col, value=label)
        cell.font = Font(bold=True, size=9, color=WHITE)
        cell.fill = _fill(TEAL)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.merge_cells(start_row=row + 1, start_column=target_col, end_row=row + 1, end_column=target_col + 1)
        cell = ws.cell(row=row + 1, column=target_col, value=value)
        cell.font = Font(bold=True, size=15, color=NAVY)
        cell.fill = _fill(GRADE_FILL.get(summary["grade"], "F3F4F6") if j == 0 else "F8FAFC")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.merge_cells(start_row=row + 2, start_column=target_col, end_row=row + 2, end_column=target_col + 1)
        cell = ws.cell(row=row + 2, column=target_col, value=note)
        cell.font = Font(size=8, color=GREY)
        cell.fill = _fill(GRADE_FILL.get(summary["grade"], "F3F4F6") if j == 0 else "F8FAFC")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[row + 1].height = 30
    row += 4

    # Temuan per tingkat
    row = _write_section(ws, row, "TEMUAN PER TINGKAT KEPARAHAN", span=span)
    header = ["Tingkat", "Jumlah Temuan", "Arti"]
    for j, text in enumerate(header):
        cell = ws.cell(row=row, column=1 + j, value=text)
        cell.font = Font(bold=True, size=10, color=WHITE)
        cell.fill = _fill(TEAL)
        cell.border = BOX
        cell.alignment = Alignment(horizontal="left")
    if j == 1:
        pass
    meaning = {
        "error": "Harus diperbaiki — memblokir validitas data.",
        "warning": "Sebaiknya diperbaiki — berpotensi menimbulkan kesalahan analisis.",
        "info": "Informasi — perapian/kebersihan data.",
    }
    for i, severity in enumerate(["error", "warning", "info"], start=1):
        label = SEVERITY_LABEL[severity]
        count = summary["counts"].get(severity, 0)
        values = [f"{SEVERITY_ICON[severity]} {label}", count, meaning[severity]]
        for j, value in enumerate(values):
            cell = ws.cell(row=row + i, column=1 + j, value=value)
            cell.border = BOX
            cell.font = Font(size=10, color=INK, bold=(j == 0))
            cell.fill = _fill(SEVERITY_FILL[label])
            if j == 1:
                cell.alignment = Alignment(horizontal="center")
    ws.merge_cells(start_row=row + 1, start_column=3, end_row=row + 1, end_column=span)
    ws.merge_cells(start_row=row + 2, start_column=3, end_row=row + 2, end_column=span)
    ws.merge_cells(start_row=row + 3, start_column=3, end_row=row + 3, end_column=span)
    row += 5

    # Status aturan + ringkasan eksekusi
    row = _write_section(ws, row, "RINGKASAN EKSEKUSI ATURAN", span=span)
    facts = [
        ("Aturan dijalankan", summary["rules_total"]),
        ("Aturan lolos", summary["rules_passed"]),
        ("Aturan menemukan masalah", summary["rules_failed"]),
        ("Aturan dilewati/gagal", summary["rules_skipped"]),
        ("Sel kosong terdeteksi", summary["blank_cells"]),
        ("Kolom tanpa isi", ", ".join(summary["empty_columns"]) or "-"),
    ]
    for i, (label, value) in enumerate(facts):
        cell_label = ws.cell(row=row + i, column=1, value=label)
        cell_label.font = Font(size=10, color=INK)
        cell_label.border = BOX
        cell_value = ws.cell(row=row + i, column=2, value=value)
        cell_value.font = Font(size=10, bold=True, color=NAVY)
        cell_value.border = BOX
        cell_value.alignment = Alignment(horizontal="center")
    row += len(facts) + 1

    # Saran tindak lanjut
    row = _write_section(ws, row, "SARAN TINDAK LANJUT (PRIORITAS)", span=span)
    for i, text in enumerate(_recommendations(result), start=0):
        ws.merge_cells(start_row=row + i, start_column=1, end_row=row + i, end_column=span)
        cell = ws.cell(row=row + i, column=1, value=f"{i + 1}. {text}")
        cell.font = Font(size=10, color=INK)
        cell.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
        ws.row_dimensions[row + i].height = 18
    row += max(len(_recommendations(result)), 1) + 1

    if result.config["rules"]:
        row = _write_section(ws, row, "ATURAN YANG DIJALANKAN", span=span)
        rules_rows = []
        for rule in result.config["rules"]:
            rules_rows.append(
                {
                    "ID Aturan": rule["id"],
                    "Nama": rule["label"],
                    "Tipe": rule["type"],
                    "Kolom": ", ".join(rule["columns"]) or "(lintas kolom)",
                    "Tingkat": SEVERITY_LABEL[rule["severity"]],
                }
            )
        row = _write_table(
            ws,
            pd.DataFrame(rules_rows),
            row,
            severity_col="Tingkat",
            widths=[24, 26, 18, 30, 14],
            auto_filter=False,
            freeze=False,
        )

    if notes:
        row = _write_section(ws, row, "CATATAN PEMBACAAN FILE", span=span)
        for i, note in enumerate(notes):
            ws.merge_cells(start_row=row + i, start_column=1, end_row=row + i, end_column=span)
            cell = ws.cell(row=row + i, column=1, value=f"• {note}")
            cell.font = Font(size=9, color=GREY)
            cell.alignment = Alignment(indent=1)

    if result.errors:
        row += len(notes) + 1
        row = _write_section(ws, row, "ATURAN YANG TIDAK DAPAT DIJALANKAN", span=span)
        for i, error in enumerate(result.errors):
            ws.merge_cells(start_row=row + i, start_column=1, end_row=row + i, end_column=span)
            cell = ws.cell(row=row + i, column=1, value=f"• {error['id']}: {error['message']}")
            cell.font = Font(size=9, color="9B1C1C")
            cell.alignment = Alignment(indent=1)

    # Lebar kolom tetap agar kartu KPI (masing-masing 2 kolom) rata.
    ws.column_dimensions["A"].width = 32
    for i in range(2, span + 1):
        ws.column_dimensions[get_column_letter(i)].width = 16
    _setup_print(ws)


def _pct(part: int, total: int) -> str:
    if not total:
        return "0%"
    return f"{100.0 * part / total:.1f}%".replace(".", ",")


# --------------------------------------------------------------------------- #
# Lembar: Temuan
# --------------------------------------------------------------------------- #
def _sheet_findings(ws: Worksheet, result, span: int = 10) -> None:
    ws.sheet_view.showGridLines = False
    row = _write_title(ws, 1, "DAFTAR BARIS BERMASALAH & SARAN PERBAIKAN", span=span, size=13)
    row = _write_note(
        ws,
        row,
        "Kolom 'Baris Excel' mengacu pada nomor baris asli pada file sumber. Gunakan filter pada header untuk menyaring "
        "per tingkat/aturan, lalu perbaiki sesuai kolom Saran Perbaikan. Kolom 'Perbaikan Otomatis' berisi usulan nilai "
        "pengganti yang aman (silakan tinjau sebelum dipakai).",
        span=span,
    )
    if result.findings.empty:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
        cell = ws.cell(row=row, column=1, value="✅ Tidak ada temuan — seluruh baris lolos aturan yang dikonfigurasi.")
        cell.font = Font(size=11, bold=True, color="065F46")
        cell.fill = _fill("D1FAE5")
        cell.alignment = Alignment(indent=1, vertical="center")
        ws.row_dimensions[row].height = 24
        return

    df = result.findings.copy()
    df["Tingkat"] = df["Tingkat"].map(lambda v: f"{SEVERITY_ICON.get(_sev_key(v), '')} {v}".strip())
    widths = [6, 11, 20, 26, 13, 22, 16, 15, 58, 58, 26]
    _setup_print(ws)
    _write_table(
        ws,
        df,
        row,
        with_index=True,
        severity_col="Tingkat",
        widths=widths,
        wrap_columns=("Alasan", "Saran Perbaikan", "Nilai Bermasalah", "Perbaikan Otomatis"),
    )


def _sev_key(label: str) -> str:
    for key, value in SEVERITY_LABEL.items():
        if value == label:
            return key
    return "info"


# --------------------------------------------------------------------------- #
# Lembar: Statistik aturan & Profil kolom
# --------------------------------------------------------------------------- #
def _sheet_rule_stats(ws: Worksheet, result) -> None:
    ws.sheet_view.showGridLines = False
    row = _write_title(ws, 1, "STATISTIK PER ATURAN", span=8, size=13)
    row = _write_note(ws, row, "Membantu melihat aturan mana yang paling banyak menemukan masalah pada dataset ini.", span=8)
    if result.rule_stats.empty:
        ws.cell(row=row, column=1, value="Belum ada aturan yang dijalankan.")
        return
    df = result.rule_stats.copy()
    df["Tingkat"] = df["Tingkat"].map(lambda v: f"{SEVERITY_ICON.get(_sev_key(v), '')} {v}".strip())
    df["Status"] = df["Status"].map(
        {"Lolos": "✅ Lolos", "Bermasalah": "⚠️ Bermasalah", "Dilewati": "⏭️ Dilewati", "Gagal": "❌ Gagal"}
    ).fillna(df["Status"])
    _setup_print(ws)
    _write_table(
        ws,
        df,
        row,
        with_index=True,
        severity_col="Tingkat",
        widths=[6, 26, 26, 16, 13, 16, 16, 18, 34],
        wrap_columns=("Catatan",),
    )
    # Sorot baris berstatus bermasalah
    for r in range(row + 1, row + 1 + len(df)):
        status = str(ws.cell(row=r, column=8).value or "")
        if status.startswith("⚠️"):
            for c in range(1, 10):
                cell = ws.cell(row=r, column=c)
                if cell.fill.fgColor.rgb in (None, "00000000"):
                    cell.fill = _fill("FFFBEB")


def _sheet_profile(ws: Worksheet, result) -> None:
    ws.sheet_view.showGridLines = False
    row = _write_title(ws, 1, "PROFIL KOLOM DATASET", span=9, size=13)
    row = _write_note(ws, row, "Kondisi awal setiap kolom sebelum perbaikan: tipe, kelengkapan, dan nilai unik.", span=9)
    profile = profile_columns(result.df)
    if profile.empty:
        return
    display = profile.rename(columns=PROFILE_LABELS)
    display["Min"] = display["Min"].map(lambda v: None if v is None or pd.isna(v) else v)
    display["Maks"] = display["Maks"].map(lambda v: None if v is None or pd.isna(v) else v)
    _setup_print(ws)
    _write_table(
        ws,
        display,
        row,
        widths=[26, 22, 12, 12, 12, 14, 14, 14, 55],
        wrap_columns=("Contoh Nilai",),
        auto_filter=True,
    )


# --------------------------------------------------------------------------- #
# Lembar: Konfigurasi & data bersih
# --------------------------------------------------------------------------- #
def _sheet_config(ws: Worksheet, result) -> None:
    from .config import config_to_yaml

    ws.sheet_view.showGridLines = False
    row = _write_title(ws, 1, "KONFIGURASI ATURAN (DAPAT DIPAKAI ULANG)", span=8, size=13)
    row = _write_note(
        ws,
        row,
        "Simpan isi di bawah sebagai file .yaml, lalu jalankan ulang audit dengan konfigurasi yang sama "
        "(streamlit: unggah di panel konfigurasi · CLI: python cli.py audit data.xlsx --config aturan.yaml).",
        span=8,
    )
    _setup_print(ws, landscape=False)
    yaml_text = config_to_yaml(result.config)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    cell = ws.cell(row=row, column=1, value=yaml_text)
    cell.font = Font(name="Consolas", size=9, color=INK)
    cell.alignment = Alignment(vertical="top", wrap_text=True)
    cell.fill = _fill("F8FAFC")
    lines = yaml_text.count("\n") + 1
    ws.row_dimensions[row].height = min(15 * lines, 540)


def _sheet_clean(ws: Worksheet, result, preview_rows: int = 200) -> None:
    ws.sheet_view.showGridLines = False
    row = _write_title(ws, 1, "PRATINJAU DATA BERSIH (PERBAIKAN AMAN DITERAPKAN)", span=8, size=13)
    row = _write_note(
        ws,
        row,
        f"Menampilkan {min(preview_rows, len(result.fixed_df))} dari {len(result.fixed_df)} baris setelah perbaikan otomatis "
        "yang tidak ambigu (trim spasi, normalisasi format tanggal, konversi tipe, koreksi nilai ke daftar baku, "
        "pembatasan nilai ke rentang). Sel yang belum dapat diperbaiki otomatis tetap dibiarkan dan wajib ditinjau manual.",
        span=8,
    )
    _setup_print(ws)
    preview = result.fixed_df.head(preview_rows).copy()
    preview.insert(0, "Baris Excel", range(result.summary.get("first_data_row_excel", 2),
                                           result.summary.get("first_data_row_excel", 2) + len(preview)))
    for col in preview.columns:
        if pd.api.types.is_datetime64_any_dtype(preview[col]):
            preview[col] = preview[col].dt.strftime("%Y-%m-%d")
        else:
            preview[col] = preview[col].map(lambda v: None if (isinstance(v, float) and pd.isna(v)) else v)
    _write_table(
        ws,
        preview,
        row,
        widths=[12] + [22] * max(len(preview.columns) - 1, 1),
        auto_filter=True,
    )


# --------------------------------------------------------------------------- #
# API publik
# --------------------------------------------------------------------------- #
def build_report(
    result,
    output: str | Path = "laporan_valido.xlsx",
    dataset_name: Optional[str] = None,
    notes: Optional[List[str]] = None,
    include_clean_preview: bool = True,
) -> Path:
    """Susun file laporan Excel multi-sheet dari :class:`AuditResult`."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    config = result.config
    dataset_name = dataset_name or getattr(result.df, "attrs", {}).get("source", {}).get("name", "dataset")
    notes = list(notes or [])
    source = getattr(result.df, "attrs", {}).get("source", {})
    if source and source.get("name") != dataset_name:
        dataset_name = source.get("name", dataset_name)
    if source.get("sheet"):
        notes.insert(0, f"Sheet yang diaudit: {source['sheet']}.")

    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "Ringkasan"
    _sheet_summary(ws_summary, result, dataset_name, notes, span=10)

    ws_findings = wb.create_sheet("Temuan_Detail")
    _sheet_findings(ws_findings, result, span=11)

    ws_stats = wb.create_sheet("Statistik_Aturan")
    _sheet_rule_stats(ws_stats, result)

    ws_profile = wb.create_sheet("Profil_Kolom")
    _sheet_profile(ws_profile, result)

    if include_clean_preview and config["report"].get("include_clean_preview", True):
        ws_clean = wb.create_sheet("Data_Bersih")
        _sheet_clean(ws_clean, result, int(config["report"].get("clean_preview_rows", 200)))

    ws_config = wb.create_sheet("Konfigurasi")
    _sheet_config(ws_config, result)

    # Metadata dokumen
    wb.properties.title = config["report"].get("title", "Laporan Audit Kualitas Data")
    wb.properties.creator = config["report"].get("auditor", "Valido")
    wb.properties.description = (
        f"Audit kualitas data oleh Valido. Skor {result.summary['score']}/100 "
        f"(grade {result.summary['grade']}), {result.summary['total_findings']} temuan."
    )
    wb.active = 0

    try:
        wb.save(output)
    except PermissionError as exc:  # pragma: no cover - bergantung OS
        raise PermissionError(
            f"File {output} sedang dipakai aplikasi lain (mungkin terbuka di Excel). Tutup lalu coba lagi."
        ) from exc
    return output


def export_findings_csv(result, output: str | Path = "temuan_valido.csv") -> Path:
    """Ekspor tabel temuan ke CSV (UTF-8 BOM agar rapi di Excel)."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.findings.to_csv(output, index=True, index_label="No", encoding="utf-8-sig")
    return output


def export_clean_csv(result, output: str | Path = "data_bersih_valido.csv") -> Path:
    """Ekspor pratinjau data bersih ke CSV."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.fixed_df.to_csv(output, index=False, encoding="utf-8-sig")
    return output
