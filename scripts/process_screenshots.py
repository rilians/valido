"""Rapikan tangkapan layar Valido untuk dokumentasi.

Yang dilakukan:
1. Memotong area sidebar aplikasi (hanya menyisakan area konten).
2. Memangkas ruang kosong di sekeliling isi.
3. Memberi sudut membulat + bingkai halus agar rapi di README GitHub.
4. Menyimpan ulang sebagai PNG teroptimasi (ukuran maksimum dibatasi).

Pemakaian:
    python scripts/process_screenshots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "docs" / "screenshots"

SIDEBAR_COLOR = (244, 247, 249)   # #f4f7f9 — secondaryBackgroundColor Streamlit
SIDEBAR_TOLERANCE = 5
RADIUS = 22
PADDING = 22
BORDER = (226, 232, 240)
MAX_WIDTH = 2400                  # batasi lebar agar ringan di GitHub
MAX_HEIGHT = 2100


def _is_sidebar(pixel: tuple[int, int, int]) -> bool:
    return all(abs(pixel[i] - SIDEBAR_COLOR[i]) <= SIDEBAR_TOLERANCE for i in range(3))


def crop_sidebar(img: Image.Image, min_fraction: float = 0.80) -> Image.Image:
    """Buang kolom sidebar.

    Untuk setiap kolom piksel di sisi kiri, hitung proporsi baris yang berwarna
    latar sidebar (#f4f7f9). Sidebar hampir seluruh kolomnya berwarna itu,
    sedangkan area konten tidak — sehingga batasnya dapat ditentukan dengan aman.
    """
    rgb = img.convert("RGB")
    width, height = rgb.size
    step = max(height // 300, 1)          # sampling baris agar cepat
    rows = range(0, height, step)
    right_edge = 0
    for x in range(0, int(width * 0.45)):
        matches = sum(1 for y in rows if _is_sidebar(rgb.getpixel((x, y))))
        if matches / max(len(list(rows)), 1) >= min_fraction:
            right_edge = x
        elif x > width * 0.06 and right_edge and x - right_edge > 4:
            break                          # sudah keluar dari area sidebar
    if right_edge > width * 0.05:
        return rgb.crop((right_edge + 3, 0, width, height))
    return rgb


def trim_whitespace(img: Image.Image, threshold: int = 250) -> Image.Image:
    """Pangkas area putih kosong di sekeliling konten."""
    gray = img.convert("L")
    mask = gray.point(lambda p: 0 if p > threshold else 255)
    bbox = mask.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    pad = 8
    return img.crop(
        (
            max(left - pad, 0),
            max(top - pad, 0),
            min(right + pad, img.width),
            min(bottom + pad, img.height),
        )
    )


def frame(img: Image.Image) -> Image.Image:
    """Letakkan gambar di kanvas putih dengan sudut membulat dan bingkai."""
    width, height = img.size
    canvas = Image.new("RGB", (width + 2 * PADDING, height + 2 * PADDING), "white")
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, height - 1], radius=RADIUS, fill=255)
    canvas.paste(img, (PADDING, PADDING), mask)
    ImageDraw.Draw(canvas).rounded_rectangle(
        [PADDING, PADDING, PADDING + width - 1, PADDING + height - 1],
        radius=RADIUS,
        outline=BORDER,
        width=2,
    )
    return canvas


def resize(img: Image.Image) -> Image.Image:
    scale = min(MAX_WIDTH / img.width, MAX_HEIGHT / img.height, 1.0)
    if scale >= 1.0:
        return img
    return img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)


def process(path: Path) -> None:
    with Image.open(path) as original:
        img = original.convert("RGB")
        if path.name[:2].isdigit():          # tangkapan layar UI punya sidebar
            img = crop_sidebar(img)
        img = trim_whitespace(img)
        img = frame(img)
        img = resize(img)
        img.save(path, format="PNG", optimize=True)
    print(f"  ✔ {path.name:34s} {img.size[0]}x{img.size[1]}  {path.stat().st_size / 1024:5.0f} KB")


def main() -> int:
    files = sorted(SHOT_DIR.glob("*.png"))
    if not files:
        print("Tidak ada gambar di", SHOT_DIR)
        return 1
    print(f"Merapikan {len(files)} gambar…")
    for path in files:
        process(path)
    print("Selesai.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
