"""Smoke test aplikasi Streamlit dengan AppTest.

Test ini memastikan alur utama UI berjalan: memuat data contoh, membangun aturan,
menjalankan audit, dan menyiapkan berkas unduhan — tanpa exception.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app.py"
SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "data" / "transaksi_penjualan.xlsx"

pytestmark = pytest.mark.skipif(
    not APP.exists() or not SAMPLE.exists(),
    reason="butuh app.py dan data contoh",
)

AppTest = pytest.importorskip("streamlit.testing.v1", reason="butuh streamlit >= 1.28").AppTest


def _new_app() -> "AppTest":
    at = AppTest.from_file(str(APP), default_timeout=180)
    at.run()
    assert not at.exception
    return at


def _click(at, label: str) -> None:
    for button in at.button:
        if button.label == label:
            button.click()
            at.run()
            assert not at.exception
            return
    raise AssertionError(f"tombol '{label}' tidak ditemukan")


def test_app_renders_without_data():
    at = _new_app()
    assert [tab.label for tab in at.tabs] == [
        "1 · Muat data",
        "2 · Atur validasi",
        "3 · Jalankan audit",
        "4 · Hasil & laporan",
    ]
    assert any("Belum ada data" in info.value for info in at.info)


def test_app_load_sample_and_audit():
    at = _new_app()
    _click(at, "Muat data contoh + aturan contoh")

    dataset = at.session_state["dataset"]
    assert dataset is not None and dataset.rows > 100
    config = at.session_state["config"]
    assert len(config["rules"]) >= 15

    _click(at, "🚀 Jalankan audit")
    result = at.session_state["result"]
    assert result is not None
    assert 0 <= result.score <= 100
    assert result.total_findings > 0
    assert not result.findings.empty


def test_app_reports_are_downloadable():
    at = _new_app()
    _click(at, "Muat data contoh + aturan contoh")
    _click(at, "🚀 Jalankan audit")

    labels = [button.label for button in at.get("download_button")]
    assert "📄 Laporan Excel" in labels
    assert "🧾 Temuan (CSV)" in labels
    assert "⚙️ Konfigurasi (YAML)" in labels


def test_app_suggest_rules_button():
    at = _new_app()
    _click(at, "Muat data contoh + aturan contoh")
    before = len(at.session_state["config"]["rules"])
    _click(at, "✨ Buat aturan otomatis dari data")
    # Aturan usulan yang ID-nya sudah ada tidak diduplikasi.
    assert len(at.session_state["config"]["rules"]) >= before


def test_app_rejects_uploading_garbage_config(tmp_path):
    at = _new_app()
    _click(at, "Muat data contoh + aturan contoh")
    editor = at.text_area(key="yaml_editor")
    editor.set_value("rules:\n  - type: tipe_tidak_ada\n    columns: [a]\n")
    at.run()
    for button in at.button:
        if button.label == "Terapkan YAML":
            button.click()
            at.run()
            break
    assert at.error  # pesan kesalahan konfigurasi ditampilkan
    assert len(at.session_state["config"]["rules"]) >= 15  # konfigurasi lama tidak rusak
