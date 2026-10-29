"""Membuat dataset contoh (bersih + sengaja bercela) untuk demo Valido.

Jalankan:  python scripts/make_sample_data.py
Output:    examples/data/transaksi_penjualan.xlsx dan .csv
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

OUT_DIR = Path(__file__).resolve().parents[1] / "examples" / "data"

NAMA = [
    "Andi Saputra", "Budi Santoso", "Citra Dewi", "Dewi Lestari", "Eko Prasetyo",
    "Fitri Handayani", "Gede Mahendra", "Hana Puspita", "Indra Wijaya", "Joko Susilo",
    "Kartika Sari", "Lukman Hakim", "Maya Anggraini", "Nanda Pratama", "Oki Setiawan",
    "Putri Ramadhani", "Rizky Firmansyah", "Sari Wulandari", "Taufik Hidayat", "Umi Kalsum",
]
KOTA = ["Jakarta", "Bandung", "Surabaya", "Depok", "Yogyakarta", "Semarang", "Medan", "Makassar"]
PRODUK = [
    ("Laptop Ultra 14", "Elektronik", 14_500_000),
    ("Headset Nirkabel", "Elektronik", 850_000),
    ("Kemeja Flanel", "Fashion", 275_000),
    ("Sepatu Lari", "Fashion", 745_000),
    ("Kopi Arabika 500g", "Makanan", 120_000),
    ("Madu Hutan 250ml", "Makanan", 95_000),
    ("Blender Kaca", "Rumah Tangga", 560_000),
    ("Setrika Uap", "Rumah Tangga", 389_000),
    ("Vitamin C 1000mg", "Kesehatan", 78_000),
    ("Masker Medis 50pcs", "Kesehatan", 45_000),
]
STATUS = ["Baru", "Diproses", "Dikirim", "Selesai", "Dibatalkan"]
METODE = ["Transfer Bank", "Kartu Kredit", "E-Wallet", "COD"]


def email_for(name: str) -> str:
    slug = name.lower().replace(" ", ".")
    return f"{slug}@{random.choice(['gmail.com', 'yahoo.co.id', 'mail.co.id', 'perusahaan.co.id'])}"


def phone() -> str:
    return "08" + "".join(str(random.randint(0, 9)) for _ in range(10))


def build_rows(total: int = 140) -> list[dict]:
    rows: list[dict] = []
    start = date(2025, 1, 3)

    for i in range(1, total + 1):
        nama = random.choice(NAMA)
        produk, kategori, harga = random.choice(PRODUK)
        qty = random.randint(1, 6)
        tanggal = start + timedelta(days=random.randint(0, 240))
        status = random.choice(STATUS)
        kirim = tanggal + timedelta(days=random.randint(1, 7)) if status in {"Dikirim", "Selesai"} else None
        rows.append(
            {
                "ID Transaksi": f"TRX-2025-{i:04d}",
                "Tanggal": tanggal.strftime("%Y-%m-%d"),
                "Pelanggan": nama,
                "Email": email_for(nama),
                "Telepon": phone(),
                "Kota": random.choice(KOTA),
                "Produk": produk,
                "Kategori": kategori,
                "Qty": qty,
                "Harga Satuan": harga,
                "Total": qty * harga,
                "Status": status,
                "Tanggal Kirim": kirim.strftime("%Y-%m-%d") if kirim else None,
                "Metode Bayar": random.choice(METODE),
                "Catatan": random.choice(["", "", "Gift wrap", "Kirim siang", "Fragile"]),
            }
        )
    return rows


def inject_problems(rows: list[dict]) -> list[dict]:
    """Sisipkan berbagai masalah kualitas data yang realistis."""
    # 1) Format tanggal tidak konsisten
    rows[3]["Tanggal"] = "05/02/2025"          # dd/mm/yyyy
    rows[11]["Tanggal"] = "12 Feb 2025"        # teks bulan
    rows[27]["Tanggal"] = "2025/03/19"         # yyyy/mm/dd
    rows[56]["Tanggal"] = "31/02/2025"         # tanggal mustahil
    rows[88]["Tanggal"] = "2025-13-45"         # tidak valid

    # 2) Nilai kosong pada kolom wajib
    rows[7]["Email"] = None
    rows[7]["Kota"] = ""
    rows[26]["Pelanggan"] = "   "
    rows[45]["Email"] = None
    rows[63]["Kota"] = "N/A"
    rows[101]["Status"] = None

    # 3) Email / telepon tidak valid
    rows[9]["Email"] = "budi.santoso[at]gmail.com"
    rows[18]["Email"] = "citra.dewi.gmail.com"
    rows[34]["Email"] = "dewi lestari@yahoo.com"
    rows[12]["Telepon"] = "+62 812-3456-7890"
    rows[41]["Telepon"] = "0812345"
    rows[77]["Telepon"] = "62812345678901"

    # 4) Nilai di luar batas
    rows[5]["Qty"] = -2
    rows[22]["Qty"] = 0
    rows[49]["Qty"] = 9999
    rows[16]["Harga Satuan"] = 0
    rows[71]["Harga Satuan"] = 980_000_000
    rows[93]["Total"] = -1_750_000

    # 5) Kategori / status tidak baku
    rows[14]["Kategori"] = "Elektronikk"
    rows[37]["Kategori"] = "Fashion "
    rows[59]["Status"] = "dikirim"
    rows[80]["Status"] = "SELESAI"
    rows[110]["Kategori"] = "Elektronik"

    # 6) Total tidak sama dengan Qty x Harga
    rows[20]["Total"] = rows[20]["Qty"] * rows[20]["Harga Satuan"] + 150_000
    rows[64]["Total"] = rows[64]["Qty"] * rows[64]["Harga Satuan"] - 90_000
    rows[112]["Total"] = 0

    # 7) Tanggal kirim lebih awal dari tanggal pesan
    rows[30]["Status"] = "Dikirim"
    rows[30]["Tanggal Kirim"] = "2025-01-01"
    rows[84]["Status"] = "Selesai"
    rows[84]["Tanggal Kirim"] = "2024-12-20"

    # 8) Status Dikirim/Selesai tetapi tanggal kirim kosong (aturan required_if)
    rows[68]["Status"] = "Dikirim"
    rows[68]["Tanggal Kirim"] = None

    # 9) Spasi berlebih
    rows[24]["Pelanggan"] = "  Eko Prasetyo "
    rows[52]["Kota"] = "Bandung  "
    rows[97]["Produk"] = " Kopi Arabika 500g"

    # 10) Nama terlalu pendek
    rows[43]["Pelanggan"] = "Al"

    # 11) Duplikat ID transaksi
    rows[120]["ID Transaksi"] = rows[19]["ID Transaksi"]
    rows[121]["ID Transaksi"] = rows[19]["ID Transaksi"]

    # 12) Baris duplikat penuh (kombinasi pelanggan+produk+tanggal)
    rows[130] = dict(rows[2])
    rows[131] = dict(rows[2])

    # 13) Nominal ekstrem (outlier)
    rows[136]["Qty"] = 40
    rows[136]["Total"] = 40 * rows[136]["Harga Satuan"]

    return rows


def main() -> None:
    rows = inject_problems(build_rows())
    df = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    xlsx_path = OUT_DIR / "transaksi_penjualan.xlsx"
    csv_path = OUT_DIR / "transaksi_penjualan.csv"

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Transaksi", index=False)

    df.to_csv(csv_path, index=False)

    print(f"✔ {xlsx_path}  ({len(df)} baris, {len(df.columns)} kolom)")
    print(f"✔ {csv_path}")


if __name__ == "__main__":
    main()
