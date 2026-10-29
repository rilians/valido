"""Ambil tangkapan layar aplikasi Valido untuk dokumentasi (README).

Pemakaian:
    streamlit run app.py --server.port 8501      # jalankan aplikasi dulu
    python scripts/capture_screenshots.py        # hasil di docs/screenshots/

Butuh: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "screenshots"
URL = "http://localhost:8501"
VIEWPORT = {"width": 1720, "height": 1330}


def wait_ready(page: Page, timeout: int = 30_000) -> None:
    """Tunggu Streamlit selesai merender (indikator 'Running'/spinner hilang)."""
    page.wait_for_selector("text=Valido", timeout=timeout)
    page.wait_for_timeout(1200)
    for _ in range(40):
        busy = page.locator('[data-testid="stStatusWidget"]').count()
        if busy == 0:
            break
        page.wait_for_timeout(400)
    page.wait_for_timeout(900)


def click_text(page: Page, text: str, selector: str = "button", timeout: int = 25_000) -> bool:
    locator = page.locator(f'{selector}:visible:has-text("{text}")').first
    try:
        locator.wait_for(state="visible", timeout=timeout)
        locator.click(timeout=timeout)
    except PWTimeout:
        print(f"  ! elemen '{text}' tidak ditemukan")
        return False
    wait_ready(page)
    return True


def scroll_to_text(page: Page, text: str, offset: int = 170) -> bool:
    """Gulir jendela hingga teks tertentu berada di bagian atas viewport."""
    locator = page.get_by_text(text, exact=False).locator("visible=true").first
    try:
        locator.wait_for(state="visible", timeout=15_000)
    except PWTimeout:
        return False
    page.evaluate(
        """([el, offset]) => {
            el.scrollIntoView({block: 'start', behavior: 'instant'});
            window.scrollBy(0, -offset);
        }""",
        [locator.element_handle(), offset],
    )
    page.wait_for_timeout(1500)
    return True



# Bagian-bagian pada tab "Hasil & laporan": (nama file, judul awal, judul berikutnya)
RESULT_SECTIONS = [
    ("07-unduh-laporan", "#valido-unduh", "#valido-detail"),
    ("08-detail-temuan", "#valido-detail", "#valido-telusuri"),
    ("09-telusuri-baris", "#valido-telusuri", "#valido-statistik"),
    ("10-statistik-aturan", "#valido-statistik", "#valido-bersih"),
    ("11-data-bersih", "#valido-bersih", None),
]

# Streamlit menggulir isi aplikasi di dalam container, bukan di window.
SCROLL_CONTAINER = '[data-testid="stMain"], section.main'


def _container(page: Page):
    handle = page.query_selector(SCROLL_CONTAINER)
    if handle is None:
        handle = page.query_selector("body")
    return handle


def element_offset(page: Page, text: str) -> float | None:
    """Posisi vertikal elemen relatif terhadap konten yang dapat digulir.

    ``text`` boleh berupa teks yang terlihat atau selector CSS (#id / .kelas).
    """
    if text.startswith(("#", ".")):
        element = page.query_selector(text)
        if element is not None:
            element.scroll_into_view_if_needed()
            page.wait_for_timeout(150)
    else:
        element = page.get_by_text(text, exact=False).locator("visible=true").first.element_handle()
    if element is None:
        return None
    return page.evaluate(
        """([el, selector]) => {
            const container = document.querySelector(selector) || document.scrollingElement;
            const box = el.getBoundingClientRect();
            const cbox = container.getBoundingClientRect();
            return box.top - cbox.top + container.scrollTop;
        }""",
        [element, SCROLL_CONTAINER],
    )


def capture_result_sections(page: Page) -> None:
    """Ambil setiap bagian tab hasil sebagai gambar terpisah.

    Strategi: perluas viewport setinggi seluruh konten (tanpa menggulir), lalu
    satu tangkapan layar penuh dipotong menurut posisi penanda bagian. Hasilnya
    deterministik: judul setiap bagian tepat di awal gambar dan tidak ada isi
    bagian lain yang ikut.
    """
    from PIL import Image

    scale = 2  # device_scale_factor pada context
    sidebar_width = page.evaluate(
        """() => {
            const el = document.querySelector('[data-testid="stSidebar"]');
            return el ? Math.ceil(el.getBoundingClientRect().width) : 0;
        }"""
    )
    content_height = page.evaluate(
        """(selector) => {
            const container = document.querySelector(selector) || document.scrollingElement;
            return Math.ceil(container.scrollHeight);
        }""",
        SCROLL_CONTAINER,
    )
    tall = min(max(content_height + 80, VIEWPORT["height"]), 9000)
    page.set_viewport_size({"width": VIEWPORT["width"], "height": tall})
    page.wait_for_timeout(2500)  # beri waktu Streamlit menata ulang tata letak

    offsets: dict[str, float] = {}
    for _, start_marker, end_marker in RESULT_SECTIONS:
        for marker in (start_marker, end_marker):
            if marker and marker not in offsets:
                handle = page.query_selector(marker)
                if handle is not None:
                    offsets[marker] = page.evaluate(
                        """(el) => {
                            const container = document.querySelector('%s') || document.scrollingElement;
                            const box = el.getBoundingClientRect();
                            const cbox = container.getBoundingClientRect();
                            return box.top - cbox.top + container.scrollTop;
                        }"""
                        % SCROLL_CONTAINER,
                        handle,
                    )

    total_height = page.evaluate(
        """(selector) => {
            const container = document.querySelector(selector) || document.scrollingElement;
            return Math.ceil(container.scrollHeight);
        }""",
        SCROLL_CONTAINER,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    full = OUT_DIR / "_halaman-penuh.png"
    page.screenshot(path=str(full), full_page=True)

    with Image.open(full) as img:
        for name, start_marker, end_marker in RESULT_SECTIONS:
            if start_marker not in offsets:
                print(f"  ! penanda '{start_marker}' tidak ditemukan")
                continue
            top = max(offsets[start_marker] - 20, 0)
            bottom = offsets.get(end_marker, total_height) if end_marker else total_height
            bottom = min(bottom, total_height)
            box = (
                int(sidebar_width * scale),
                int(top * scale),
                img.width,
                int(bottom * scale),
            )
            if box[3] - box[1] < 100:
                print(f"  ! bagian '{name}' terlalu pendek, dilewati")
                continue
            target = OUT_DIR / f"{name}.png"
            img.crop(box).convert("RGB").save(target, format="PNG", optimize=True)
            width, height = _size(target)
            print(f"  ✔ {target.name:34s} {width}x{height}  {target.stat().st_size / 1024:6.0f} KB")
    full.unlink(missing_ok=True)

    # kembalikan ukuran viewport semula
    page.set_viewport_size(VIEWPORT)
    page.wait_for_timeout(800)


def shot(page: Page, name: str, full_page: bool = False, selector: str | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / f"{name}.png"
    if selector:
        element = page.locator(selector).first
        element.wait_for(state="visible", timeout=20_000)
        element.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        element.screenshot(path=str(target))
    else:
        page.screenshot(path=str(target), full_page=full_page)
    width, height = _size(target)
    print(f"  ✔ {target.name:34s} {width}x{height}  {target.stat().st_size / 1024:6.0f} KB")


def _size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as img:
        return img.size


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2, locale="id-ID")
        page = context.new_page()

        print("→ Membuka aplikasi…")
        page.goto(URL, wait_until="domcontentloaded")
        wait_ready(page)
        shot(page, "01-beranda")

        print("→ Memuat data + konfigurasi contoh…")
        if not click_text(page, "Muat data contoh + aturan contoh"):
            browser.close()
            return 1
        page.wait_for_timeout(5200)  # beri waktu notifikasi/toast hilang sendiri
        shot(page, "02-unggah-dan-pratinjau")

        print("→ Tab 2: aturan validasi…")
        click_text(page, "2 · Atur validasi", selector='[role="tab"]')
        shot(page, "03-aturan-validasi")

        print("→ Form tambah aturan manual…")
        try:
            page.get_by_text("Tambah aturan manual", exact=False).locator("visible=true").first.click()
            page.wait_for_timeout(1400)
            shot(page, "04-tambah-aturan")
            page.get_by_text("Tambah aturan manual", exact=False).locator("visible=true").first.click()
            page.wait_for_timeout(600)
        except PWTimeout:
            print("  ! panel tambah aturan tidak ditemukan")

        print("→ Tab 3: jalankan audit…")
        click_text(page, "3 · Jalankan audit", selector='[role="tab"]')
        shot(page, "05-jalankan-audit")
        if click_text(page, "🚀 Jalankan audit"):
            page.wait_for_timeout(2500)
            shot(page, "06-ringkasan-hasil")

        print("→ Tab 4: hasil & laporan…")
        click_text(page, "4 · Hasil & laporan", selector='[role="tab"]')
        page.wait_for_timeout(3000)
        print("→ Memotong bagian-bagian tab hasil…")
        capture_result_sections(page)

        context.close()
        browser.close()
    print("Selesai. Jalankan `python scripts/process_screenshots.py` untuk merapikan gambar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
