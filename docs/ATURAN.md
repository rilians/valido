# Referensi Tipe Aturan Valido

Semua aturan ditulis dalam satu file YAML di bawah kunci `rules`. Setiap aturan mendukung kunci umum:

| Kunci | Wajib | Keterangan |
| --- | --- | --- |
| `type` | ✅ | Salah satu dari 14 tipe di bawah |
| `columns` | ✅ (kecuali tipe lintas kolom) | Daftar nama kolom persis seperti di file |
| `severity` | – | `error` (default), `warning`, `info` |
| `id` | – | Identitas unik aturan; dibuat otomatis bila kosong |
| `label` | – | Nama aturan pada laporan |
| `message` | – | Template alasan; boleh memakai placeholder |
| `suggestion` | – | Template saran perbaikan |

Placeholder yang tersedia pada `message`/`suggestion` antara lain:
`{column}`, `{columns}`, `{row}`, `{value}`, `{expected}`, `{bounds}`, `{count}`, `{first_row}`,
`{options}`, `{length}`, `{expression}`, `{when}`, `{first}`, `{second}`, `{first_value}`, `{second_value}`.
Placeholder yang tidak relevan akan kosong, bukan error.

Nama kolom yang mengandung spasi/tanda baca ditulis di antara backtick pada ekspresi:
`` `Harga Satuan` * Qty ``. Pada kunci `columns`, tulis apa adanya: `columns: [Harga Satuan]`.

---

## 1. `required` — wajib terisi

Menandai sel kosong, berisi spasi saja, atau berisi penanda null (`N/A`, `null`, `-`, `#N/A`, `none`, …).
Angka `0` dan boolean `False` **tidak** dianggap kosong.

```yaml
- id: wajib_email
  type: required
  columns: [Email]
  severity: error
```

## 2. `required_if` — wajib terisi bila kondisi terpenuhi

| Parameter | Keterangan |
| --- | --- |
| `when` | Ekspresi kondisi (wajib) |

```yaml
- id: tanggal_kirim_wajib
  type: required_if
  columns: [Tanggal Kirim]
  when: "Status.isin(['Dikirim', 'Selesai'])"
  severity: error
```

Baris yang kolom kondisinya kosong dilewati (tidak dianggap pelanggaran) agar tidak terjadi temuan palsu.

## 3. `unique` — nilai harus unik

| Parameter | Default | Keterangan |
| --- | --- | --- |
| `ignore_case` | `true` | `A1` dan `a1` dianggap sama |
| `ignore_whitespace` | `true` | Spasi awal/akhir diabaikan |

```yaml
- id: unik_id_transaksi
  type: unique
  columns: [ID Transaksi]
```

Semua baris dalam grup duplikat dilaporkan (termasuk kemunculan pertama) agar pengguna bisa memutuskan mana yang dipertahankan.

## 4. `duplicate` — baris duplikat

| Parameter | Default | Keterangan |
| --- | --- | --- |
| `columns` | seluruh kolom | Kombinasi kolom penentu identitas baris |
| `ignore_case` | `true` | Perbandingan tanpa membedakan huruf besar/kecil |

```yaml
- id: duplikat_transaksi
  type: duplicate
  columns: [Pelanggan, Produk, Tanggal, Total]
  severity: warning
```

## 5. `date_format` — format tanggal konsisten

| Parameter | Default | Keterangan |
| --- | --- | --- |
| `formats` | `[]` | Daftar pola `strptime` yang diizinkan. Kosong = deteksi format dominan otomatis |
| `strict` | `true` | `true`: hanya format dominan/pertama yang sah. `false`: semua format pada `formats` sah |

```yaml
- id: format_tanggal
  type: date_format
  columns: [Tanggal]
  formats: ["%Y-%m-%d"]
  severity: warning
```

Perilaku:
- Nilai yang sudah bertipe tanggal asli (sel tanggal Excel) dianggap sah.
- Nilai yang formatnya berbeda → `warning` (dengan contoh format yang benar).
- Nilai yang tidak dapat dibaca sebagai tanggal sama sekali (mis. `31/02/2025`) → `error`.

## 6. `date_order` — urutan tanggal logis

Membutuhkan **tepat dua kolom**: kolom kedua tidak boleh lebih awal dari kolom pertama.

```yaml
- id: urutan_tanggal_kirim
  type: date_order
  columns: [Tanggal, Tanggal Kirim]     # kirim >= pesan
  severity: error
```

Bila salah satu nilai tidak bisa dibaca sebagai tanggal, temuan dilaporkan sebagai `warning`
(karena urutan tidak dapat diverifikasi).

## 7. `range` — nilai numerik dalam batas

| Parameter | Default | Keterangan |
| --- | --- | --- |
| `min` | – | Batas bawah (isi minimal salah satu: `min`/`max`) |
| `max` | – | Batas atas |
| `allow_blank` | `true` | Bila `false`, sel kosong dilaporkan |
| `allow_non_numeric` | `false` | Bila `false`, teks yang bukan angka dilaporkan |

```yaml
- id: qty_rentang
  type: range
  columns: [Qty]
  min: 1
  max: 100
```

Nilai seperti `Rp1.250.000` atau `1,5` diparse otomatis (format Indonesia & internasional).

## 8. `dtype` — tipe data seragam

| Parameter | Nilai |
| --- | --- |
| `expected` | `number`, `integer`, `date`, `boolean`, `text` |
| `allow_blank` | default `true` |

```yaml
- id: harga_angka
  type: dtype
  columns: [Harga Satuan]
  expected: number
```

Berguna untuk menangkap angka yang "tercemar" teks (`12.000,-`, `1,2jt`) sebelum proses analisis.

## 9. `outlier` — nilai statistik ekstrem

| Parameter | Default | Keterangan |
| --- | --- | --- |
| `method` | `iqr` | `iqr` atau `zscore` |
| `factor` | `1.5` | Pengali IQR (1.5 = normal, 3.0 = ekstrem) |
| `threshold` | `3.0` | Ambang z-score |

```yaml
- id: total_pencilan
  type: outlier
  columns: [Total]
  severity: warning
  method: zscore
  threshold: 4.0
```

Perlu minimal 4 nilai numerik; pada dataset sangat kecil aturan ini dilewati (tanpa temuan).

## 10. `allowed_values` — daftar nilai baku

| Parameter | Default | Keterangan |
| --- | --- | --- |
| `values` | – | Daftar nilai yang sah (wajib) |
| `case_sensitive` | `false` | Bila `false`, `baru` = `Baru` |
| `allow_blank` | `true` | Bila `false`, sel kosong dilaporkan |

```yaml
- id: status_baku
  type: allowed_values
  columns: [Status]
  values: [Baru, Diproses, Dikirim, Selesai, Dibatalkan]
  case_sensitive: true
```

Valido menyertakan **nilai terdekat** (fuzzy match) pada alasan/saran, mis. `SELESAI` → “Mungkin maksudnya **Selesai**”.

## 11. `pattern` — pola teks (regex)

| Parameter | Default | Keterangan |
| --- | --- | --- |
| `regex` | – | Pola Python `re` (wajib, divalidasi saat konfigurasi dibaca) |
| `full_match` | `true` | `false` = cukup mengandung pola |
| `hint` | `""` | Petunjuk format yang ditampilkan pada alasan/saran |
| `allow_blank` | `true` | Bila `false`, sel kosong dilaporkan |

```yaml
- id: email_valid
  type: pattern
  columns: [Email]
  regex: '^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$'
  hint: "contoh: nama@perusahaan.co.id"

- id: telepon_valid
  type: pattern
  columns: [Telepon]
  severity: warning
  regex: '^(\+62|62|0)8[0-9]{7,12}$'
  hint: "contoh: 081234567890"
```

## 12. `length` — panjang teks

| Parameter | Keterangan |
| --- | --- |
| `min`, `max` | Batas jumlah karakter (minimal salah satu diisi) |
| `allow_blank` | default `true` |

```yaml
- id: nama_panjang
  type: length
  columns: [Pelanggan]
  min: 3
  max: 60
  severity: warning
```

## 13. `whitespace` — spasi/enter berlebih

Mendeteksi spasi atau baris baru di awal/akhir teks — penyebab paling umum kegagalan `VLOOKUP`/join.
Nilai ini **dapat diperbaiki otomatis** di sheet `Data_Bersih`.

```yaml
- id: spasi_berlebih
  type: whitespace
  columns: [Pelanggan, Kota, Produk]
  severity: info
```

## 14. `business_rule` — ekspresi antar-kolom

| Parameter | Keterangan |
| --- | --- |
| `expression` | Kondisi yang harus bernilai benar untuk setiap baris |

```yaml
- id: total_sesuai
  type: business_rule
  columns: [Qty, Harga Satuan, Total]
  expression: "Total == Qty * `Harga Satuan`"

- id: diskon_wajar
  type: business_rule
  columns: [Diskon, Total]
  expression: "Diskon <= 0.5 * Total"

- id: kirim_setelah_pesan
  type: business_rule
  columns: [Tanggal, Tanggal Kirim]
  expression: "notna(`Tanggal Kirim`) <= (Tanggal <= `Tanggal Kirim`)"
```

Operator dan fungsi yang tersedia:

- Perbandingan & logika: `==`, `!=`, `>`, `>=`, `<`, `<=`, `&`, `|`, `~`
- Aritmetika: `+`, `-`, `*`, `/`, `**`, `%`
- Fungsi: `abs`, `min`, `max`, `round`, `len`, `sum`, `isna`, `notna`, `to_number`
- Metode Series: `isin([...])`, `.str.contains(...)` (atribut privat `_` dilarang)

Bila kolom yang dirujuk memuat nilai kosong, baris tersebut dilaporkan dengan tingkat `warning`
(“tidak dapat diperiksa”) — bukan `error`, karena pelanggaran belum tentu terjadi.

---

## Urutan eksekusi & kegagalan aturan

1. Valido memvalidasi seluruh konfigurasi **sebelum** audit dimulai; kesalahan konfigurasi
   (tipe tidak dikenal, regex rusak, `min > max`, ekspresi berbahaya) langsung ditolak.
2. Setiap aturan dijalankan terpisah. Aturan yang gagal (mis. kolom tidak ada di file) **tidak**
   menghentikan aturan lain; statusnya tercatat sebagai `Dilewati` atau `Gagal` pada sheet
   `Statistik_Aturan` dan bagian catatan laporan.
3. Temuan diurutkan menurut nomor baris Excel, lalu tingkat keparahan (error → warning → info).

## Tingkat keparahan

| Tingkat | Arti | Bobot skor per baris |
| --- | --- | --- |
| `error` | Harus diperbaiki, memblokir validitas data | 1.00 |
| `warning` | Sebaiknya diperbaiki, berpotensi menyesatkan analisis | 0.40 |
| `info` | Perapian/kebersihan data | 0.12 |
