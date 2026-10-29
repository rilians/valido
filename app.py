"""Valido — Automated Excel Data Auditor (aplikasi Streamlit).

Jalankan:  streamlit run app.py
"""

from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from valido import (
    RULE_TYPES,
    SEVERITIES,
    ConfigError,
    DatasetError,
    config_from_yaml,
    config_to_yaml,
    default_config,
    list_sheets,
    load_config,
    load_dataset_info,
    normalize_config,
    profile_columns,
    run_audit,
    suggest_rules,
)
from valido.config import RULE_TYPE_ORDER, SEVERITY_ICON, SEVERITY_LABEL
from valido.profile import column_value_counts, profile_display
from valido.report import build_report

APP_DIR = Path(__file__).resolve().parent
SAMPLE_FILES = {
    "Transaksi penjualan — Excel (.xlsx)": APP_DIR / "examples" / "data" / "transaksi_penjualan.xlsx",
    "Transaksi penjualan — CSV (.csv)": APP_DIR / "examples" / "data" / "transaksi_penjualan.csv",
}
SAMPLE_CONFIG = APP_DIR / "configs" / "contoh_aturan_transaksi.yaml"


def sample_rule_count() -> int:
    """Jumlah aturan pada file konfigurasi contoh (0 bila tidak tersedia)."""
    try:
        return len(load_config(SAMPLE_CONFIG)["rules"])
    except (ConfigError, OSError):
        return 0

st.set_page_config(
    page_title="Valido — Automated Excel Data Auditor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
  :root {
    --valido-navy: #0f2c4c;
    --valido-teal: #127475;
    --valido-mint: #d9eeef;
    --valido-sand: #f7f5ef;
  }
  .block-container { padding-top: 2.2rem; max-width: 1350px; }
  .valido-hero {
    background: linear-gradient(120deg, #0f2c4c 0%, #127475 72%, #1fa3a4 100%);
    border-radius: 18px;
    padding: 26px 30px;
    color: #ffffff;
    margin-bottom: 18px;
    box-shadow: 0 12px 30px rgba(15, 44, 76, 0.20);
  }
  .valido-hero h1 { font-size: 2.05rem; margin: 0; letter-spacing: -0.5px; color: #fff; }
  .valido-hero p { margin: 8px 0 0; font-size: 1.0rem; opacity: 0.93; max-width: 900px; }
  .valido-chip {
    display: inline-block; background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.28);
    padding: 3px 11px; border-radius: 999px; font-size: 0.76rem; margin-right: 6px; margin-top: 12px;
    letter-spacing: 0.2px;
  }
  .valido-card {
    background: #ffffff; border: 1px solid #e6e9ee; border-radius: 14px;
    padding: 16px 18px; height: 100%;
    box-shadow: 0 1px 2px rgba(16,24,40,0.04);
  }
  .valido-card .label { font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.7px; color: #6b7280; font-weight: 600; }
  .valido-card .value { font-size: 1.9rem; font-weight: 700; color: #0f2c4c; line-height: 1.15; }
  .valido-card .note { font-size: 0.78rem; color: #6b7280; }
  .valido-section {
    font-size: 1.12rem; font-weight: 700; color: #0f2c4c; margin: 6px 0 10px;
    border-left: 4px solid #127475; padding-left: 10px;
  }
  .severity-error { color: #9b1c1c; font-weight: 700; }
  .severity-warning { color: #8a5300; font-weight: 700; }
  .severity-info { color: #1d4ed8; font-weight: 700; }
  .valido-muted { color: #6b7280; font-size: 0.86rem; }
  div[data-testid="stMetricValue"] { color: #0f2c4c; }
  .stTabs [data-baseweb="tab-list"] { gap: 6px; }
  .stTabs [data-baseweb="tab"] {
    background: #eef2f6; border-radius: 10px 10px 0 0; padding: 8px 16px; font-weight: 600;
  }
  .stTabs [aria-selected="true"] { background: #127475 !important; color: #fff !important; }
  footer { visibility: hidden; }
</style>
"""

HERO = """
<div class="valido-hero">
  <h1>🔍 Valido</h1>
  <p><b>Automated Excel Data Auditor</b> — periksa kualitas file Excel atau CSV tanpa memeriksa baris satu per satu.
     Atur sendiri aturan validasinya, lalu unduh laporan berisi baris bermasalah, alasan, dan saran perbaikan.</p>
  <div>
    <span class="valido-chip">Deteksi data kosong</span>
    <span class="valido-chip">Duplikat</span>
    <span class="valido-chip">Format tanggal</span>
    <span class="valido-chip">Nilai di luar batas</span>
    <span class="valido-chip">Aturan bisnis</span>
    <span class="valido-chip">Laporan Excel</span>
  </div>
</div>
"""


# --------------------------------------------------------------------------- #
# State & util
# --------------------------------------------------------------------------- #
def init_state() -> None:
    st.session_state.setdefault("dataset", None)
    st.session_state.setdefault("config", default_config())
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("load_notes", [])
    st.session_state.setdefault("notices", [])
    st.session_state.setdefault("filters", {})


def card(label: str, value: str, note: str = "", accent: str = "") -> str:
    style = f"border-left:5px solid {accent};" if accent else ""
    return (
        f'<div class="valido-card" style="{style}">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="note">{note}</div></div>'
    )


def load_file(source: Any, name: str, sheet: Optional[str] = None, header_row: int = 0) -> None:
    try:
        loaded = load_dataset_info(source, sheet=sheet, header_row=header_row)
    except DatasetError as exc:
        st.error(f"Gagal membaca file: {exc}")
        return
    st.session_state.dataset = loaded
    st.session_state.load_notes = loaded.notes
    st.session_state.result = None
    config = st.session_state.config
    config["dataset"]["sheet"] = loaded.sheet
    config["dataset"]["header_row"] = loaded.header_row
    st.success(
        f"✅ **{loaded.name}** berhasil dimuat — {loaded.rows} baris × {loaded.columns} kolom"
        + (f" (sheet: {loaded.sheet})" if loaded.sheet else "")
    )


def suggest_and_store(use_profile: bool = True) -> None:
    dataset = st.session_state.dataset
    if dataset is None:
        return
    rules = suggest_rules(dataset.df)
    if not rules:
        st.warning("Tidak ada aturan usulan yang bisa dibuat otomatis untuk dataset ini.")
        return
    config = st.session_state.config
    existing_ids = {r["id"] for r in config["rules"]}
    added = [r for r in rules if r["id"] not in existing_ids]
    try:
        candidate = dict(config)
        candidate["rules"] = list(config["rules"]) + added
        merged = normalize_config(candidate)
    except ConfigError as exc:
        st.error(f"Aturan usulan tidak valid: {exc}")
        return
    st.session_state.config = merged
    st.success(f"✨ {len(added)} aturan usulan ditambahkan (total {len(merged['rules'])} aturan).")


def rule_columns_text(rule: dict) -> str:
    return ", ".join(rule.get("columns") or []) or "(lintas kolom)"


def render_rule_fields(rtype: str, prefix: str) -> Dict[str, Any]:
    """Bangun widget untuk parameter khusus tipe aturan; kembalikan nilainya."""
    spec = RULE_TYPES[rtype]
    values: Dict[str, Any] = {}
    for fname, fspec in spec["fields"].items():
        key = f"{prefix}_{fname}"
        label = fspec.get("label", fname)
        help_text = fspec.get("help")
        ftype = fspec.get("type")
        default = fspec.get("default")
        if ftype == "bool":
            values[fname] = st.checkbox(label, value=bool(default), key=key, help=help_text)
        elif ftype == "number":
            text = st.text_input(label, value="" if default is None else str(default), key=key, help=help_text or "Kosongkan bila tidak dibatasi.")
            try:
                values[fname] = float(text) if str(text).strip() != "" else None
            except ValueError:
                st.warning(f"{label}: '{text}' bukan angka, nilai diabaikan.")
                values[fname] = None
        elif ftype == "list":
            text = st.text_area(label, value=", ".join(default or []), key=key, help=help_text, height=70)
            values[fname] = [p.strip() for p in text.replace("\n", ",").split(",") if p.strip()]
        elif ftype == "select":
            choices = fspec.get("choices", [])
            index = choices.index(default) if default in choices else 0
            values[fname] = st.selectbox(label, options=choices, index=index, key=key, help=help_text)
        else:
            values[fname] = st.text_input(label, value=str(default or ""), key=key, help=help_text)
    return values


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar() -> None:
    with st.sidebar:
        st.markdown("### 🔍 Valido")
        st.caption("Automated Excel Data Auditor · v1.0.0")
        st.divider()

        dataset = st.session_state.dataset
        if dataset is not None:
            st.markdown("**Dataset aktif**")
            st.write(f"📄 {dataset.name}")
            st.caption(
                f"{dataset.rows} baris · {dataset.columns} kolom"
                + (f" · sheet {dataset.sheet}" if dataset.sheet else "")
            )
        else:
            st.info("Belum ada data yang dimuat.")

        config = st.session_state.config
        st.markdown("**Konfigurasi validasi**")
        st.caption(f"{len(config['rules'])} aturan aktif")
        for severity in ["error", "warning", "info"]:
            jumlah = sum(1 for r in config["rules"] if r["severity"] == severity)
            st.caption(f"{SEVERITY_ICON[severity]} {SEVERITY_LABEL[severity]}: {jumlah}")

        st.divider()
        st.markdown("**Data contoh**")
        if st.button("Muat data contoh + aturan contoh", use_container_width=True, type="secondary"):
            sample = SAMPLE_FILES["Transaksi penjualan — Excel (.xlsx)"]
            if not sample.exists():
                st.error("Data contoh tidak ditemukan. Jalankan `python scripts/make_sample_data.py`.")
            else:
                load_file(sample, sample.name)
                if SAMPLE_CONFIG.exists():
                    try:
                        st.session_state.config = load_config(SAMPLE_CONFIG)
                        st.session_state.notices.append(f"Konfigurasi contoh dimuat ({sample_rule_count()} aturan siap pakai).")
                    except ConfigError as exc:
                        st.warning(f"Konfigurasi contoh gagal dimuat: {exc}")
                st.rerun()

        st.divider()
        st.caption(
            "Aturan dapat diatur lewat UI, diunggah dari YAML, atau diunduh untuk dipakai ulang "
            "di CLI (`python cli.py audit`)."
        )


# --------------------------------------------------------------------------- #
# Tab 1 — Unggah data
# --------------------------------------------------------------------------- #
def tab_upload() -> None:
    st.markdown('<div class="valido-section">1 · Muat file Excel / CSV</div>', unsafe_allow_html=True)
    left, right = st.columns([1.15, 1])

    with left:
        uploaded = st.file_uploader(
            "Pilih file data (.xlsx, .xlsm, .csv)",
            type=["xlsx", "xlsm", "csv", "txt"],
            help="Maksimal 200 MB. File tidak dikirim ke mana pun — seluruh proses berjalan di sesi ini.",
        )
        if uploaded is not None:
            st.caption(f"File terpilih: **{uploaded.name}** ({uploaded.size / 1024:.0f} KB)")
            sheet_choice = None
            if uploaded.name.lower().endswith((".xlsx", ".xlsm")):
                try:
                    sheets = list_sheets(uploaded)
                except DatasetError as exc:
                    sheets = []
                    st.warning(str(exc))
                if sheets:
                    sheet_choice = st.selectbox("Sheet yang diaudit", sheets)
            header_row = st.number_input(
                "Baris header (0 = baris pertama)", min_value=0, max_value=30, value=0, step=1,
                help="Ubah bila file punya judul/laporan di beberapa baris atas.",
            )
            if st.button("📥 Muat data", type="primary", use_container_width=True):
                load_file(uploaded, uploaded.name, sheet=sheet_choice, header_row=int(header_row))

        st.markdown("---")
        st.markdown("**Atau pakai data contoh bawaan**")
        sample_name = st.selectbox("Data contoh", list(SAMPLE_FILES.keys()), label_visibility="collapsed")
        if st.button("Muat data contoh", use_container_width=True):
            sample = SAMPLE_FILES[sample_name]
            if not sample.exists():
                st.error("Data contoh belum dibuat. Jalankan `python scripts/make_sample_data.py`.")
            else:
                load_file(sample, sample.name)

    with right:
        dataset = st.session_state.dataset
        if dataset is None:
            st.info(
                "Unggah file untuk mulai. Valido membaca seluruh tabel, lalu memeriksa setiap sel "
                "berdasarkan aturan yang Anda aktifkan."
            )
            st.markdown(
                """
**Yang diperiksa Valido**
- 📌 Sel kosong pada kolom wajib
- 🔑 Nilai berulang & baris duplikat
- 📅 Format tanggal tidak konsisten
- 📏 Nilai di luar batas / daftar baku
- 🧠 Aturan bisnis antar-kolom
- 📄 Laporan Excel: temuan, bukti, dan saran perbaikan
                """
            )
        else:
            df = dataset.df
            st.markdown(
                card("Dataset", f"{dataset.rows:,}".replace(",", "."), "baris terbaca", "#127475")
                + "<div style='height:10px'></div>"
                + card("Kolom", f"{dataset.columns}", "kolom terdeteksi", "#0f2c4c"),
                unsafe_allow_html=True,
            )
            if st.session_state.load_notes:
                with st.expander("ℹ️ Catatan pembacaan file", expanded=False):
                    for note in st.session_state.load_notes:
                        st.write(f"- {note}")

    dataset = st.session_state.dataset
    if dataset is not None:
        st.markdown("---")
        st.markdown('<div class="valido-section">Pratinjau data & profil kolom</div>', unsafe_allow_html=True)
        prev_tab, profile_tab = st.tabs(["👀 Pratinjau 15 baris", "📊 Profil kolom"])
        with prev_tab:
            st.dataframe(dataset.df.head(15), use_container_width=True, height=340)
        with profile_tab:
            profile = profile_columns(dataset.df)
            st.dataframe(
                profile_display(profile),
                use_container_width=True,
                height=340,
                column_config={
                    "% Kosong": st.column_config.ProgressColumn(
                        "% Kosong", min_value=0, max_value=100, format="%.1f%%"
                    ),
                },
            )
            numeric_cols = [r["kolom"] for r in profile.to_dict("records") if r["tipe"] == "angka"]
            if numeric_cols:
                col = st.selectbox("Lihat distribusi nilai kolom numerik", numeric_cols)
                counts = column_value_counts(dataset.df, col, top=12)
                if not counts.empty:
                    st.bar_chart(counts.set_index("Nilai"), height=240)


# --------------------------------------------------------------------------- #
# Tab 2 — Atur validasi
# --------------------------------------------------------------------------- #
def tab_rules() -> None:
    dataset = st.session_state.dataset
    if dataset is None:
        st.info("Muat data terlebih dahulu pada tab **1 · Muat data**.")
        return

    df = dataset.df
    config = st.session_state.config

    st.markdown('<div class="valido-section">2 · Susun aturan validasi</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 1])
    if c1.button("✨ Buat aturan otomatis dari data", use_container_width=True, type="primary"):
        suggest_and_store()
    if c2.button("🧹 Kosongkan semua aturan", use_container_width=True):
        st.session_state.config["rules"] = []
        st.session_state.result = None
        st.rerun()
    if c3.button(f"📥 Muat aturan contoh ({sample_rule_count()} aturan)", use_container_width=True):
        if SAMPLE_CONFIG.exists():
            try:
                st.session_state.config = load_config(SAMPLE_CONFIG)
                st.session_state.notices.append("Aturan contoh dimuat.")
                st.rerun()
            except ConfigError as exc:
                st.error(str(exc))

    # ---- Tambah aturan manual ----
    with st.expander("➕ Tambah aturan manual", expanded=not config["rules"]):
        rtype = st.selectbox(
            "Tipe aturan",
            options=RULE_TYPE_ORDER,
            format_func=lambda t: f"{RULE_TYPES[t]['icon']}  {RULE_TYPES[t]['label']}  —  {RULE_TYPES[t]['description']}",
            key="builder_type",
        )
        spec = RULE_TYPES[rtype]
        st.caption(f"**{spec['label']}** · {spec['description']}")

        columns_needed = spec["columns"]
        selected: List[str] = []
        col_a, col_b = st.columns(2)
        options = [str(c) for c in df.columns]
        if columns_needed == "one":
            selected = [col_a.selectbox("Kolom yang diperiksa", options, key=f"bcol_{rtype}")]
        elif columns_needed == "two":
            first = col_a.selectbox("Kolom pertama (acuan)", options, key=f"bcol1_{rtype}")
            second = col_b.selectbox("Kolom kedua", options, index=min(1, len(options) - 1), key=f"bcol2_{rtype}")
            selected = [first, second]
        elif columns_needed in {"many", "many_optional"}:
            selected = st.multiselect(
                "Kolom yang diperiksa" + (" (kosongkan = seluruh kolom)" if columns_needed == "many_optional" else ""),
                options,
                default=options[: (2 if rtype == "date_order" else 1)] if options else [],
                key=f"bcols_{rtype}",
            )
        else:
            selected = st.multiselect(
                "Kolom terkait (untuk keterangan temuan, opsional)", options, key=f"bcols_opt_{rtype}"
            )

        with st.form(f"form_add_{rtype}"):
            params = render_rule_fields(rtype, prefix=f"f_{rtype}")
            fc1, fc2 = st.columns(2)
            severity = fc1.selectbox(
                "Tingkat keparahan", options=list(SEVERITIES),
                index=list(SEVERITIES).index(spec.get("severity", "error")),
                format_func=lambda s: f"{SEVERITY_ICON[s]} {SEVERITY_LABEL[s]}",
                key=f"fsev_{rtype}",
            )
            custom_label = fc2.text_input("Nama aturan (opsional)", key=f"flabel_{rtype}")
            submitted = st.form_submit_button("Tambah aturan", type="primary")

        if submitted:
            rule = {"type": rtype, "columns": selected, "severity": severity, **params}
            if custom_label.strip():
                rule["label"] = custom_label.strip()
            candidate = dict(st.session_state.config)
            candidate["rules"] = list(st.session_state.config["rules"]) + [rule]
            try:
                trial = normalize_config(candidate)
            except ConfigError as exc:
                st.error(f"Aturan belum bisa ditambahkan: {exc}")
            else:
                st.session_state.config = trial
                st.session_state.result = None
                st.success(f"Aturan '{trial['rules'][-1]['label']}' ditambahkan.")
                st.rerun()

    # ---- Daftar aturan aktif ----
    st.markdown('<div class="valido-section">Aturan aktif</div>', unsafe_allow_html=True)
    rules = st.session_state.config["rules"]
    if not rules:
        st.warning("Belum ada aturan. Gunakan *Buat aturan otomatis* atau tambahkan aturan manual.")
    else:
        summary_rows = [
            {
                "Nama aturan": rule["label"],
                "Tipe": RULE_TYPES.get(rule["type"], {}).get("label", rule["type"]),
                "Kolom": rule_columns_text(rule),
                "Tingkat": f"{SEVERITY_ICON[rule['severity']]} {SEVERITY_LABEL[rule['severity']]}",
                "ID": rule["id"],
            }
            for rule in rules
        ]
        st.dataframe(
            pd.DataFrame(summary_rows),
            use_container_width=True,
            height=min(60 + 35 * len(rules), 420),
            hide_index=True,
        )

        st.markdown("**Ubah / hapus aturan**")
        for index, rule in enumerate(list(rules)):
            label = f"{SEVERITY_ICON[rule['severity']]} {rule['label']} · {rule_columns_text(rule)}"
            with st.expander(label, expanded=False):
                detail = {
                    "ID": rule["id"],
                    "Tipe": rule["type"],
                    "Kolom": rule["columns"],
                    "Tingkat": rule["severity"],
                }
                for fname in RULE_TYPES[rule["type"]]["fields"]:
                    detail[fname] = rule.get(fname)
                st.json(detail)
                c1, c2 = st.columns([2, 1])
                new_severity = c1.selectbox(
                    "Tingkat keparahan",
                    options=list(SEVERITIES),
                    index=list(SEVERITIES).index(rule["severity"]),
                    format_func=lambda s: f"{SEVERITY_ICON[s]} {SEVERITY_LABEL[s]}",
                    key=f"sev_{index}_{rule['id']}",
                )
                if new_severity != rule["severity"]:
                    st.session_state.config["rules"][index]["severity"] = new_severity
                    st.session_state.result = None
                    st.rerun()
                if c2.button("🗑️ Hapus aturan", key=f"del_{index}_{rule['id']}", use_container_width=True):
                    st.session_state.config["rules"].pop(index)
                    st.session_state.result = None
                    st.rerun()

    # ---- Impor / ekspor konfigurasi ----
    st.markdown('<div class="valido-section">Impor & ekspor konfigurasi</div>', unsafe_allow_html=True)
    imp, exp = st.columns(2)
    with imp:
        cfg_file = st.file_uploader("Unggah konfigurasi aturan (.yaml / .json)", type=["yaml", "yml", "json"], key="cfg_upload")
        if cfg_file is not None and st.button("Terapkan konfigurasi", use_container_width=True):
            try:
                suffix = Path(cfg_file.name).suffix or ".yaml"
                tmp = APP_DIR / f".uploaded_config{suffix}"
                tmp.write_bytes(cfg_file.getvalue())
                st.session_state.config = load_config(tmp)
                tmp.unlink(missing_ok=True)
                st.session_state.result = None
                st.success(f"Konfigurasi diterapkan: {len(st.session_state.config['rules'])} aturan.")
                st.rerun()
            except (ConfigError, OSError) as exc:
                st.error(str(exc))
    with exp:
        st.download_button(
            "⬇️ Unduh konfigurasi (YAML)",
            data=config_to_yaml(st.session_state.config),
            file_name="aturan_valido.yaml",
            mime="text/yaml",
            use_container_width=True,
            disabled=not st.session_state.config["rules"],
        )
        with st.expander("Lihat / edit YAML langsung"):
            yaml_text = st.text_area(
                "Konten YAML",
                value=config_to_yaml(st.session_state.config),
                height=260,
                key="yaml_editor",
            )
            if st.button("Terapkan YAML", use_container_width=True):
                try:
                    st.session_state.config = config_from_yaml(yaml_text)
                    st.session_state.result = None
                    st.success("YAML berhasil diterapkan.")
                    st.rerun()
                except ConfigError as exc:
                    st.error(str(exc))


# --------------------------------------------------------------------------- #
# Tab 3 — Jalankan audit
# --------------------------------------------------------------------------- #
def tab_run() -> None:
    dataset = st.session_state.dataset
    config = st.session_state.config
    st.markdown('<div class="valido-section">3 · Jalankan audit</div>', unsafe_allow_html=True)

    if dataset is None:
        st.info("Muat data pada tab **1 · Muat data**.")
        return
    if not config["rules"]:
        st.warning("Belum ada aturan yang aktif. Buka tab **2 · Atur validasi**.")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(
            f"**{len(config['rules'])} aturan** akan dijalankan pada **{dataset.rows:,} baris** × "
            f"**{dataset.columns} kolom** ({dataset.rows * dataset.columns:,} sel diperiksa).".replace(",", "."),
            unsafe_allow_html=True,
        )
        st.caption("Audit berjalan di memori sesi ini; tidak ada data yang dikirim keluar.")
    with c2:
        generate_clean = st.checkbox("Sertakan pratinjau data bersih", value=True)

    if st.button("🚀 Jalankan audit", type="primary", use_container_width=True):
        with st.spinner("Mengaudit data..."):
            try:
                result = run_audit(
                    dataset.df,
                    config,
                    first_data_row_excel=dataset.header_row + 2,
                )
            except Exception as exc:  # tampilkan kesalahan utuh agar mudah dilaporkan
                st.error(f"Audit gagal: {exc}")
                with st.expander("Detail teknis"):
                    st.code(traceback.format_exc())
                return
        st.session_state.result = result
        st.session_state.include_clean = generate_clean
        if result.errors:
            st.warning(
                "Sebagian aturan tidak dapat dijalankan: "
                + "; ".join(f"{e['id']} ({e['message']})" for e in result.errors[:4])
            )
        st.success(
            f"Audit selesai — skor {result.score:.1f}/100 (grade {result.grade}), "
            f"{result.total_findings} temuan pada {result.affected_rows} baris."
        )

    result = st.session_state.result
    if result is not None:
        render_result_summary(result)
        st.info("Detail lengkap, filter, dan unduhan tersedia di tab **4 · Hasil & laporan**.")


def render_result_summary(result) -> None:
    st.markdown('<div class="valido-section">Ringkasan hasil</div>', unsafe_allow_html=True)
    counts = result.counts
    cols = st.columns(5)
    cols[0].markdown(
        card("Skor kesehatan", f"{result.score:.1f}", f"grade {result.grade} · {result.grade_label}", "#127475"),
        unsafe_allow_html=True,
    )
    cols[1].markdown(
        card("Baris bermasalah", f"{result.affected_rows}", f"dari {result.total_rows} baris", "#9b1c1c"),
        unsafe_allow_html=True,
    )
    cols[2].markdown(
        card("Error", f"{counts.get('error', 0)}", "wajib diperbaiki", "#9b1c1c"), unsafe_allow_html=True
    )
    cols[3].markdown(
        card("Peringatan", f"{counts.get('warning', 0)}", "perlu ditinjau", "#b45309"), unsafe_allow_html=True
    )
    cols[4].markdown(
        card("Perbaikan otomatis", f"{result.summary['auto_fixable']}", "usulan nilai pengganti", "#1d4ed8"),
        unsafe_allow_html=True,
    )
    st.progress(min(result.score / 100.0, 1.0), text=f"Skor {result.score:.1f}/100 — {result.summary['advice']}")

    if result.findings.empty:
        st.success("🎉 Tidak ada temuan. Seluruh baris lolos aturan yang dikonfigurasi.")
        return

    st.markdown('<div id="valido-akhir-ringkasan"></div>', unsafe_allow_html=True)
    left, right = st.columns([1, 1.4])
    with left:
        st.markdown("**Sebaran tingkat keparahan**")
        sev = pd.DataFrame(
            {
                "Tingkat": [SEVERITY_LABEL[s] for s in ["error", "warning", "info"]],
                "Temuan": [counts.get(s, 0) for s in ["error", "warning", "info"]],
            }
        ).set_index("Tingkat")
        st.bar_chart(sev, height=210, color="#127475")
    with right:
        st.markdown("**Aturan dengan temuan terbanyak**")
        top = (
            result.findings.groupby("Aturan")
            .size()
            .sort_values(ascending=False)
            .head(7)
            .rename("Jumlah temuan")
        )
        st.dataframe(top.to_frame(), use_container_width=True, height=210)


# --------------------------------------------------------------------------- #
# Tab 4 — Hasil & laporan
# --------------------------------------------------------------------------- #
def tab_results() -> None:
    result = st.session_state.result
    st.markdown('<div class="valido-section">4 · Hasil pemeriksaan & laporan</div>', unsafe_allow_html=True)
    if result is None:
        st.info("Belum ada hasil. Jalankan audit pada tab **3 · Jalankan audit**.")
        return

    render_report_downloads(result)

    st.markdown("---")
    st.markdown('<div id="valido-detail"></div>', unsafe_allow_html=True)
    st.markdown('<div class="valido-section">Detail baris bermasalah</div>', unsafe_allow_html=True)
    if result.findings.empty:
        st.success("Tidak ada baris bermasalah untuk ditampilkan.")
    else:
        findings = result.findings.reset_index()
        f1, f2, f3, f4 = st.columns([1.1, 1.1, 1.2, 1.6])
        severity_filter = f1.multiselect(
            "Tingkat", list(findings["Tingkat"].unique()), default=list(findings["Tingkat"].unique())
        )
        rule_filter = f2.multiselect("Aturan", sorted(findings["Aturan"].unique()))
        column_filter = f3.multiselect(
            "Kolom",
            sorted([c for c in findings["Kolom"].dropna().unique() if str(c).strip()]),
        )
        search = f4.text_input("Cari kata kunci (alasan/saran/nilai)", "")

        view = findings[findings["Tingkat"].isin(severity_filter)] if severity_filter else findings
        if rule_filter:
            view = view[view["Aturan"].isin(rule_filter)]
        if column_filter:
            view = view[view["Kolom"].isin(column_filter)]
        if search.strip():
            needle = search.lower()
            mask = (
                view["Alasan"].astype(str).str.lower().str.contains(needle, regex=False)
                | view["Saran Perbaikan"].astype(str).str.lower().str.contains(needle, regex=False)
                | view["Nilai Bermasalah"].astype(str).str.lower().str.contains(needle, regex=False)
                | view["ID Aturan"].astype(str).str.lower().str.contains(needle, regex=False)
            )
            view = view[mask]

        st.caption(f"Menampilkan {len(view)} dari {len(findings)} temuan.")
        st.dataframe(
            view.drop(columns=["No"], errors="ignore"),
            use_container_width=True,
            height=420,
            column_config={
                "Alasan": st.column_config.TextColumn(width="large"),
                "Saran Perbaikan": st.column_config.TextColumn(width="large"),
                "Baris Excel": st.column_config.NumberColumn(width="small"),
            },
        )

        st.markdown('<div id="valido-telusuri"></div>', unsafe_allow_html=True)
        st.markdown("**Telusuri satu baris**")
        row_options = sorted(view["Baris Excel"].unique().tolist())
        if row_options:
            picked = st.selectbox("Nomor baris Excel", row_options, key="inspect_row")
            detail = view[view["Baris Excel"] == picked]
            for _, item in detail.iterrows():
                st.markdown(
                    f"**Baris {picked} · {item['Aturan']}** — "
                    f"{SEVERITY_ICON.get(_severity_key(item['Tingkat']), '')} {item['Tingkat']}"
                )
                st.write(f"• Nilai bermasalah: `{item['Nilai Bermasalah']}`" + (f" (kolom **{item['Kolom']}**)" if item["Kolom"] else ""))
                st.write(f"• Alasan: {item['Alasan']}")
                st.write(f"• Saran: {item['Saran Perbaikan']}")
                if item["Perbaikan Otomatis"]:
                    st.write(f"• Perbaikan otomatis yang diusulkan: `{item['Perbaikan Otomatis']}`")
                st.divider()

            st.markdown("**Isi baris asli pada dataset**")
            pos = picked - result.summary.get("first_data_row_excel", 2)
            if 0 <= pos < len(result.df):
                row_df = result.df.iloc[[pos]].T.reset_index()
                row_df.columns = ["Kolom", "Nilai"]
                st.dataframe(row_df, use_container_width=True, height=220)

    st.markdown("---")
    st.markdown('<div id="valido-statistik"></div>', unsafe_allow_html=True)
    st.markdown('<div class="valido-section">Statistik per aturan</div>', unsafe_allow_html=True)
    if not result.rule_stats.empty:
        st.dataframe(result.rule_stats, use_container_width=True, height=340)

    st.markdown('<div id="valido-bersih"></div>', unsafe_allow_html=True)
    st.markdown('<div class="valido-section">Pratinjau data bersih</div>', unsafe_allow_html=True)
    changed = count_changed_cells(result.df, result.fixed_df)
    st.caption(
        f"{changed} sel dapat diperbaiki otomatis (trim spasi, normalisasi tanggal, konversi tipe, "
        "koreksi ke daftar baku, pembatasan ke rentang). Sel lain wajib ditinjau manual."
    )
    preview_clean = result.fixed_df.head(200).astype(object).where(result.fixed_df.head(200).notna(), "")
    st.dataframe(preview_clean, use_container_width=True, height=320)


def _severity_key(label: str) -> str:
    for key, value in SEVERITY_LABEL.items():
        if value == label:
            return key
    return "info"


def count_changed_cells(before: pd.DataFrame, after: pd.DataFrame) -> int:
    count = 0
    for col in before.columns:
        if col not in after.columns:
            continue
        for a, b in zip(before[col].tolist(), after[col].tolist()):
            a_blank = a is None or (isinstance(a, float) and pd.isna(a))
            b_blank = b is None or (isinstance(b, float) and pd.isna(b))
            if a_blank and b_blank:
                continue
            if str(a) != str(b):
                count += 1
    return count


def render_report_downloads(result) -> None:
    st.markdown('<div id="valido-unduh"></div>', unsafe_allow_html=True)
    st.markdown('<div class="valido-section">Unduh laporan</div>', unsafe_allow_html=True)
    dataset = st.session_state.dataset
    stamp = datetime.now().strftime("%Y%m%d_%H%M")

    with st.spinner("Menyiapkan berkas laporan..."):
        try:
            report_path = build_report(
                result,
                APP_DIR / "hasil" / f"laporan_valido_{stamp}.xlsx",
                dataset_name=dataset.name if dataset else "dataset",
                notes=st.session_state.load_notes,
                include_clean_preview=st.session_state.get("include_clean", True),
            )
            xlsx_bytes = report_path.read_bytes()
            csv_bytes = result.findings.to_csv(index=True, index_label="No", encoding="utf-8-sig").encode("utf-8-sig")
            clean_bytes = result.fixed_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            yaml_bytes = config_to_yaml(result.config).encode("utf-8")
        except Exception as exc:
            st.error(f"Gagal menyusun laporan: {exc}")
            return

    c1, c2, c3, c4 = st.columns(4)
    c1.download_button(
        "📄 Laporan Excel",
        data=xlsx_bytes,
        file_name=f"laporan_valido_{stamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )
    c2.download_button(
        "🧾 Temuan (CSV)",
        data=csv_bytes,
        file_name=f"temuan_valido_{stamp}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    c3.download_button(
        "🧼 Data bersih (CSV)",
        data=clean_bytes,
        file_name=f"data_bersih_valido_{stamp}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    c4.download_button(
        "⚙️ Konfigurasi (YAML)",
        data=yaml_bytes,
        file_name=f"aturan_valido_{stamp}.yaml",
        mime="text/yaml",
        use_container_width=True,
    )
    st.caption(
        "Laporan Excel berisi 6 sheet: **Ringkasan**, **Temuan_Detail**, **Statistik_Aturan**, "
        "**Profil_Kolom**, **Data_Bersih**, dan **Konfigurasi** (siap dipakai ulang lewat CLI)."
    )
    st.markdown('<div id="valido-pemisah-laporan"></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(HERO, unsafe_allow_html=True)
    sidebar()

    for message in st.session_state.notices:
        st.toast(message)
    st.session_state.notices = []

    tabs = st.tabs(["1 · Muat data", "2 · Atur validasi", "3 · Jalankan audit", "4 · Hasil & laporan"])
    with tabs[0]:
        tab_upload()
    with tabs[1]:
        tab_rules()
    with tabs[2]:
        tab_run()
    with tabs[3]:
        tab_results()

    st.markdown("---")
    st.caption(
        "Valido v1.0.0 · Python · pandas · openpyxl · Streamlit — seluruh proses berjalan lokal di sesi Anda."
    )


if __name__ == "__main__":
    main()
