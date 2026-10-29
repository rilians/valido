"""Render pratinjau laporan Excel Valido menjadi gambar untuk dokumentasi.

Alur: audit dataset contoh → laporan .xlsx → PDF (LibreOffice) → PNG per sheet.

Pemakaian:
    python scripts/render_report_preview.py

Butuh: LibreOffice (`soffice`) dan PyMuPDF (`pip install pymupdf`).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from valido import build_report, load_config, load_dataset_info, run_audit  # noqa: E402

OUT_DIR = ROOT / "docs" / "screenshots"
SHEETS = {
    "report-01-ringkasan": "LAPORAN AUDIT KUALITAS DATA",
    "report-02-temuan": "DAFTAR BARIS BERMASALAH",
    "report-03-statistik": "STATISTIK PER ATURAN",
    "report-04-profil": "PROFIL KOLOM DATASET",
    "report-05-data-bersih": "PRATINJAU DATA BERSIH",
    "report-06-konfigurasi": "KONFIGURASI ATURAN",
}
DPI = 135
PADDING = 18


def build_sample_report(target: Path) -> Path:
    loaded = load_dataset_info(ROOT / "examples" / "data" / "transaksi_penjualan.xlsx", sheet="Transaksi")
    config = load_config(ROOT / "configs" / "contoh_aturan_transaksi.yaml")
    result = run_audit(loaded.df, config, first_data_row_excel=loaded.header_row + 2)
    return build_report(result, target, dataset_name=loaded.name, notes=loaded.notes)


def to_pdf(xlsx: Path, workdir: Path) -> Path:
    if not shutil.which("soffice"):
        raise SystemExit("LibreOffice tidak ditemukan. Pasang `libreoffice-calc` lalu coba lagi.")
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(workdir), str(xlsx)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=300,
    )
    return workdir / (xlsx.stem + ".pdf")


def main() -> int:
    import pymupdf
    from PIL import Image

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        print("→ Menyusun laporan contoh…")
        xlsx = build_sample_report(tmpdir / "laporan_valido.xlsx")
        (ROOT / "docs" / "contoh").mkdir(parents=True, exist_ok=True)
        shutil.copy(xlsx, ROOT / "docs" / "contoh" / "laporan_valido.xlsx")
        print("  ✔ docs/contoh/laporan_valido.xlsx")
        print("→ Mengonversi ke PDF…")
        pdf = to_pdf(xlsx, tmpdir)

        doc = pymupdf.open(pdf)
        pages = {}
        for index, page in enumerate(doc):
            text = page.get_text()
            for name, marker in SHEETS.items():
                if marker in text and name not in pages:
                    pages[name] = index

        for name, marker in SHEETS.items():
            if name not in pages:
                print(f"  ! sheet untuk '{marker}' tidak ditemukan di PDF")
                continue
            page = doc[pages[name]]
            pixmap = page.get_pixmap(dpi=DPI)
            raw = tmpdir / f"{name}.png"
            pixmap.save(str(raw))
            with Image.open(raw) as img:
                # Pangkas margin putih agar gambar fokus ke isi laporan.
                bbox = img.convert("L").point(lambda p: 0 if p > 247 else 255).getbbox()
                canvas = img.crop(bbox) if bbox else img
                canvas = canvas.convert("RGB")
                target = OUT_DIR / f"{name}.png"
                canvas.save(target, format="PNG", optimize=True)
            print(f"  ✔ {target.name:30s} {canvas.size[0]}x{canvas.size[1]}  {target.stat().st_size / 1024:5.0f} KB")
        doc.close()
    print("Selesai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
