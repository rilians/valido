"""Definisi, validasi, dan (de)serialisasi konfigurasi aturan audit Valido."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

SEVERITIES = ("error", "warning", "info")
SEVERITY_LABEL = {"error": "Error", "warning": "Peringatan", "info": "Info"}
SEVERITY_ICON = {"error": "🔴", "warning": "🟠", "info": "🔵"}
SEVERITY_WEIGHT = {"error": 3.0, "warning": 1.5, "info": 0.5}
# Bobot per baris dipakai untuk Skor Kesehatan Data (0-100).
ROW_SEVERITY_WEIGHT = {"error": 1.0, "warning": 0.4, "info": 0.12}

MAX_RULES = 200


class ConfigError(ValueError):
    """Dilempar bila konfigurasi aturan tidak valid."""


# --------------------------------------------------------------------------- #
# Katalog tipe aturan (dipakai mesin audit sekaligus UI Streamlit)
# --------------------------------------------------------------------------- #
RULE_TYPES: Dict[str, Dict[str, Any]] = {
    "required": {
        "label": "Wajib terisi",
        "icon": "📌",
        "description": "Menandai sel kosong atau berisi spasi / penanda null (null, N/A, -).",
        "columns": "one",
        "fields": {},
        "severity": "error",
        "message": "Kolom {column} wajib terisi, tetapi nilainya kosong.",
        "suggestion": "Lengkapi nilai kolom {column} pada baris {row}. Bila memang tidak berlaku, isi dengan penanda baku seperti \"TIDAK ADA\" agar konsisten.",
    },
    "unique": {
        "label": "Nilai unik",
        "icon": "🔑",
        "description": "Nilai pada kolom tidak boleh berulang (mis. kode pelanggan, NIK, nomor invoice).",
        "columns": "one",
        "fields": {
            "ignore_case": {"label": "Abaikan besar-kecil huruf", "type": "bool", "default": True},
            "ignore_whitespace": {"label": "Abaikan spasi di awal/akhir", "type": "bool", "default": True},
        },
        "severity": "error",
        "message": "Nilai {value} muncul {count} kali di kolom {column}; seharusnya unik.",
        "suggestion": "Pertahankan satu baris saja (baris {first_row}) dan hapus/ubah duplikatnya, atau tambahkan pembeda bila memang entitas berbeda.",
    },
    "duplicate": {
        "label": "Baris duplikat",
        "icon": "👯",
        "description": "Deteksi baris ganda berdasarkan kombinasi kolom kunci (kosongkan kolom = bandingkan semua kolom).",
        "columns": "many_optional",
        "fields": {
            "ignore_case": {"label": "Abaikan besar-kecil huruf", "type": "bool", "default": True},
        },
        "severity": "error",
        "message": "Kombinasi kolom {columns} duplikat: grup #{group}, muncul {count} kali (baris {rows}).",
        "suggestion": "Hapus atau gabungkan baris duplikat tersebut; jika keduanya valid, tambahkan kolom pembeda yang unik (mis. nomor urut transaksi).",
    },
    "date_format": {
        "label": "Format tanggal konsisten",
        "icon": "📅",
        "description": "Mendeteksi format tanggal dominan, lalu menandai nilai yang formatnya berbeda atau tidak bisa dibaca.",
        "columns": "one",
        "fields": {
            "formats": {
                "label": "Format yang diizinkan (opsional)",
                "type": "list",
                "default": [],
                "help": "Contoh: %Y-%m-%d, %d/%m/%Y. Kosongkan agar Valido mendeteksi format dominan otomatis.",
            },
            "strict": {"label": "Wajib satu format seragam", "type": "bool", "default": True},
        },
        "severity": "warning",
        "message": "Format tanggal tidak konsisten: {value} terbaca sebagai {found}, sedangkan format dominan adalah {expected}.",
        "suggestion": "Ubah nilai menjadi format tanggal baku {expected_human} (contoh: {example}).",
    },
    "range": {
        "label": "Rentang nilai",
        "icon": "📏",
        "description": "Nilai numerik harus berada di antara batas minimum dan maksimum.",
        "columns": "one",
        "fields": {
            "min": {"label": "Nilai minimum", "type": "number", "default": None},
            "max": {"label": "Nilai maksimum", "type": "number", "default": None},
            "allow_blank": {"label": "Boleh kosong", "type": "bool", "default": True},
            "allow_non_numeric": {"label": "Abaikan nilai non-angka", "type": "bool", "default": False},
        },
        "severity": "error",
        "message": "Nilai {value} di luar rentang yang diizinkan ({bounds}).",
        "suggestion": "Periksa kembali nilai kolom {column} pada baris {row}; pastikan berada dalam rentang {bounds} dan tidak salah ketik (mis. kelebihan/ kekurangan nol).",
    },
    "allowed_values": {
        "label": "Daftar nilai diizinkan",
        "icon": "✅",
        "description": "Nilai harus termasuk salah satu opsi baku (status, kategori, kode wilayah, dll.).",
        "columns": "one",
        "fields": {
            "values": {"label": "Nilai yang diizinkan", "type": "list", "default": [], "required": True},
            "case_sensitive": {"label": "Peka besar-kecil huruf", "type": "bool", "default": False},
            "allow_blank": {"label": "Boleh kosong", "type": "bool", "default": True},
        },
        "severity": "error",
        "message": "Nilai {value} tidak termasuk daftar yang diizinkan.",
        "suggestion": "Ganti dengan salah satu nilai baku: {options}. Perhatikan salah ketik dan spasi berlebih.",
    },
    "pattern": {
        "label": "Pola teks (regex)",
        "icon": "🔤",
        "description": "Validasi bentuk teks seperti email, nomor telepon, kode pos, atau SKU.",
        "columns": "one",
        "fields": {
            "regex": {"label": "Pola regex", "type": "text", "default": r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", "required": True},
            "full_match": {"label": "Harus cocok seluruh teks", "type": "bool", "default": True},
            "hint": {"label": "Petunjuk format untuk pengguna", "type": "text", "default": ""},
            "allow_blank": {"label": "Boleh kosong", "type": "bool", "default": True},
        },
        "severity": "error",
        "message": "Nilai {value} tidak sesuai pola yang diminta{hint}.",
        "suggestion": "Perbaiki format kolom {column} pada baris {row}{hint_example}.",
    },
    "dtype": {
        "label": "Tipe data",
        "icon": "🔢",
        "description": "Pastikan seluruh isi kolom bertipe sama (angka, bilangan bulat, tanggal, boolean, teks).",
        "columns": "one",
        "fields": {
            "expected": {
                "label": "Tipe yang diharapkan",
                "type": "select",
                "default": "number",
                "choices": ["number", "integer", "date", "boolean", "text"],
            },
            "allow_blank": {"label": "Boleh kosong", "type": "bool", "default": True},
        },
        "severity": "error",
        "message": "Nilai {value} bukan bertipe {expected}.",
        "suggestion": "Ubah nilai kolom {column} pada baris {row} menjadi {expected_label} tanpa simbol/teks tambahan.",
    },
    "length": {
        "label": "Panjang teks",
        "icon": "✂️",
        "description": "Batasi jumlah karakter (mis. nama 3-60 karakter, kode pos 5 digit).",
        "columns": "one",
        "fields": {
            "min": {"label": "Panjang minimum", "type": "number", "default": None},
            "max": {"label": "Panjang maksimum", "type": "number", "default": None},
            "allow_blank": {"label": "Boleh kosong", "type": "bool", "default": True},
        },
        "severity": "warning",
        "message": "Panjang teks {length} karakter, di luar batas {bounds}.",
        "suggestion": "Sesuaikan isi kolom {column} pada baris {row} agar panjangnya {bounds}.",
    },
    "whitespace": {
        "label": "Spasi berlebih",
        "icon": "🧹",
        "description": "Menandai spasi/enter di awal atau akhir teks yang sering merusak proses pencocokan (join).",
        "columns": "many",
        "fields": {},
        "severity": "info",
        "message": "Nilai {value} mengandung spasi/enter di awal atau akhir.",
        "suggestion": "Hapus spasi berlebih (trim) pada kolom {column} baris {row}. Valido menyiapkan perbaikannya di sheet Data_Bersih.",
    },
    "business_rule": {
        "label": "Aturan bisnis (ekspresi)",
        "icon": "🧠",
        "description": "Ekspresi antar-kolom, mis. harga_jual >= harga_modal atau diskon <= 0.5 * harga.",
        "columns": "none",
        "fields": {
            "expression": {
                "label": "Ekspresi yang harus bernilai benar",
                "type": "text",
                "default": "harga_jual >= harga_modal",
                "required": True,
                "help": "Gunakan nama kolom apa adanya. Untuk nama berspasi, apit dengan backtick: `Total Bayar` > 0.",
            },
        },
        "severity": "error",
        "message": "Aturan bisnis tidak terpenuhi: {expression}.",
        "suggestion": "Periksa kembali nilai kolom terkait pada baris {row}; sesuaikan agar aturan {expression} terpenuhi.",
    },
    "required_if": {
        "label": "Wajib terisi bila kondisi",
        "icon": "🔀",
        "description": "Kolom tertentu wajib diisi hanya ketika kondisi terpenuhi (mis. status = Selesai maka tanggal_kirim wajib ada).",
        "columns": "many",
        "fields": {
            "when": {
                "label": "Kondisi (ekspresi)",
                "type": "text",
                "default": "status == 'Selesai'",
                "required": True,
            },
        },
        "severity": "error",
        "message": "Kolom {column} wajib diisi karena kondisi {when} terpenuhi.",
        "suggestion": "Lengkapi kolom {column} pada baris {row}, atau perbaiki kondisi/kategorinya bila baris ini seharusnya tidak memenuhi {when}.",
    },
    "date_order": {
        "label": "Urutan tanggal",
        "icon": "⏱️",
        "description": "Tanggal pada kolom kedua tidak boleh lebih awal dari kolom pertama (mis. tanggal_kirim >= tanggal_pesan).",
        "columns": "two",
        "fields": {},
        "severity": "error",
        "message": "Tanggal {second} ({second_value}) lebih awal daripada {first} ({first_value}).",
        "suggestion": "Tukar atau perbaiki salah satu tanggal pada baris {row} sehingga urutannya logis.",
    },
    "outlier": {
        "label": "Pencilan (outlier)",
        "icon": "📈",
        "description": "Deteksi nilai statistik ekstrem dengan metode IQR atau z-score.",
        "columns": "one",
        "fields": {
            "method": {"label": "Metode", "type": "select", "default": "iqr", "choices": ["iqr", "zscore"]},
            "factor": {"label": "Faktor IQR (1.5 = normal, 3.0 = ekstrem)", "type": "number", "default": 1.5},
            "threshold": {"label": "Ambang z-score", "type": "number", "default": 3.0},
        },
        "severity": "warning",
        "message": "Nilai {value} terdeteksi sebagai pencilan (batas wajar {bounds}).",
        "suggestion": "Pastikan nilai kolom {column} baris {row} bukan salah input (kelebihan nol, nilai placeholder 999999, atau satuan berbeda).",
    },
}

RULE_TYPE_ORDER: List[str] = list(RULE_TYPES.keys())

EXPECTED_LABEL = {
    "number": "angka",
    "integer": "bilangan bulat",
    "date": "tanggal",
    "boolean": "boolean (Ya/Tidak)",
    "text": "teks",
}


# --------------------------------------------------------------------------- #
# Nilai bawaan
# --------------------------------------------------------------------------- #
DATASET_DEFAULTS = {
    "sheet": None,
    "header_row": 0,
    "trim_strings": False,
    "skip_empty_rows": True,
}

REPORT_DEFAULTS = {
    "title": "Laporan Audit Kualitas Data",
    "auditor": "Valido",
    "max_detail_rows": 5000,
    "clean_preview_rows": 200,
    "include_clean_preview": True,
}


def default_config(name: str = "Konfigurasi Audit Valido") -> dict:
    """Konfigurasi kosong dengan nilai bawaan lengkap."""
    return {
        "meta": {"name": name, "version": 1},
        "dataset": deepcopy(DATASET_DEFAULTS),
        "report": deepcopy(REPORT_DEFAULTS),
        "rules": [],
    }


# --------------------------------------------------------------------------- #
# Normalisasi & validasi
# --------------------------------------------------------------------------- #
def _coerce_value(field: str, spec: dict, raw: Any, rule_label: str) -> Any:
    ftype = spec.get("type", "text")
    if ftype == "number":
        if raw is None or raw == "":
            return None
        try:
            num = float(raw)
        except (TypeError, ValueError):
            raise ConfigError(f"{rule_label}: nilai '{field}' harus berupa angka, diterima {raw!r}.")
        return int(num) if num.is_integer() else num
    if ftype == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "ya", "yes", "y", "on"}
        return bool(raw)
    if ftype == "list":
        if raw is None:
            return []
        if isinstance(raw, str):
            parts = raw.replace("\n", ",").split(",")
            return [p.strip() for p in parts if p.strip()]
        if isinstance(raw, (list, tuple, set)):
            out = []
            for item in raw:
                text = "" if item is None else str(item).strip()
                if text:
                    out.append(text)
            return out
        return [str(raw).strip()]
    if ftype == "select":
        value = str(raw).strip()
        choices = spec.get("choices", [])
        if value not in choices:
            raise ConfigError(
                f"{rule_label}: nilai '{field}' harus salah satu dari {choices}, diterima {value!r}."
            )
        return value
    return "" if raw is None else str(raw)


def _compile_check(expression: str, rule_label: str, field: str = "expression") -> str:
    import ast

    import re

    expression = expression.strip()
    if not expression:
        raise ConfigError(f"{rule_label}: '{field}' tidak boleh kosong.")
    # Nama kolom ber-backtick diganti placeholder agar bisa diurai AST.
    proxy = re.sub(r"`[^`]+`", "_kolom", expression)
    try:
        tree = ast.parse(proxy, mode="eval")
    except SyntaxError as exc:
        raise ConfigError(f"{rule_label}: ekspresi '{expression}' tidak valid ({exc.msg}).") from exc
    blocked = {"__import__", "eval", "exec", "open", "compile", "globals", "locals", "input"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in blocked:
            raise ConfigError(f"{rule_label}: kata '{node.id}' tidak diizinkan di dalam ekspresi.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ConfigError(f"{rule_label}: akses atribut '{node.attr}' tidak diizinkan.")
    return expression


def normalize_rule(raw: dict, index: int = 0) -> dict:
    """Validasi satu aturan mentah dan lengkapi nilai bawaannya."""
    if not isinstance(raw, dict):
        raise ConfigError(f"Aturan #{index + 1} harus berupa objek/dict, diterima {type(raw).__name__}.")
    rtype = raw.get("type")
    if rtype not in RULE_TYPES:
        raise ConfigError(
            f"Aturan #{index + 1}: tipe {rtype!r} tidak dikenal. "
            f"Tipe yang tersedia: {', '.join(RULE_TYPE_ORDER)}."
        )
    spec = RULE_TYPES[rtype]
    rule = deepcopy(raw)

    # Kolom
    columns = rule.get("columns", [])
    if isinstance(columns, str):
        columns = [columns]
    if columns is None:
        columns = []
    columns = [str(c).strip() for c in columns if str(c).strip()]
    if spec["columns"] == "one" and len(columns) != 1:
        raise ConfigError(
            f"Aturan #{index + 1} ({spec['label']}) membutuhkan tepat 1 kolom, diterima {len(columns)}."
        )
    if spec["columns"] == "two" and len(columns) != 2:
        raise ConfigError(
            f"Aturan #{index + 1} ({spec['label']}) membutuhkan tepat 2 kolom, diterima {len(columns)}."
        )
    if spec["columns"] == "many" and len(columns) < 1:
        raise ConfigError(f"Aturan #{index + 1} ({spec['label']}) membutuhkan minimal 1 kolom.")
    rule["columns"] = columns

    # Identitas & tingkat keparahan
    rule_id = str(rule.get("id") or "").strip()
    if not rule_id:
        suffix = "_".join(c.lower().replace(" ", "_") for c in columns) or "global"
        rule_id = f"{rtype}_{suffix}"
    rule["id"] = rule_id
    severity = str(rule.get("severity") or spec.get("severity", "error")).lower()
    if severity not in SEVERITIES:
        raise ConfigError(
            f"Aturan '{rule_id}': severity {severity!r} tidak dikenal. Pilih: {', '.join(SEVERITIES)}."
        )
    rule["severity"] = severity
    rule["type"] = rtype
    rule["label"] = str(rule.get("label") or spec["label"])

    # Parameter khusus tipe aturan
    for fname, fspec in spec["fields"].items():
        if fname in rule and rule[fname] is not None:
            rule[fname] = _coerce_value(fname, fspec, rule[fname], f"Aturan '{rule_id}'")
        else:
            rule[fname] = deepcopy(fspec.get("default"))
        if fspec.get("required") and rule[fname] in (None, "", []):
            raise ConfigError(f"Aturan '{rule_id}': parameter '{fname}' wajib diisi.")

    # Pesan & saran
    rule["message"] = str(rule.get("message") or spec.get("message", ""))
    rule["suggestion"] = str(rule.get("suggestion") or spec.get("suggestion", ""))

    # Validasi tambahan per tipe
    if rtype in {"range", "length"}:
        lo, hi = rule.get("min"), rule.get("max")
        if lo is not None and hi is not None and float(lo) > float(hi):
            raise ConfigError(f"Aturan '{rule_id}': nilai minimum ({lo}) lebih besar dari maksimum ({hi}).")
        if lo is None and hi is None:
            raise ConfigError(f"Aturan '{rule_id}': isi minimal salah satu dari 'min' atau 'max'.")
    if rtype == "pattern":
        import re

        try:
            re.compile(rule["regex"])
        except re.error as exc:
            raise ConfigError(f"Aturan '{rule_id}': regex tidak valid ({exc}).") from exc
    if rtype in {"business_rule", "required_if"}:
        field = "expression" if rtype == "business_rule" else "when"
        rule[field] = _compile_check(rule[field], f"Aturan '{rule_id}'", field)
    if rtype == "outlier":
        factor = rule.get("factor") or 1.5
        rule["factor"] = float(factor)
        rule["threshold"] = float(rule.get("threshold") or 3.0)
        if rule["factor"] <= 0:
            raise ConfigError(f"Aturan '{rule_id}': 'factor' harus lebih besar dari 0.")

    return rule


def normalize_config(raw: dict | None) -> dict:
    """Validasi konfigurasi penuh dan kembalikan versi yang sudah dinormalkan."""
    if raw is None:
        return default_config()
    if not isinstance(raw, dict):
        raise ConfigError("Konfigurasi harus berupa objek/dict.")

    config = default_config()
    meta = raw.get("meta") or {}
    if isinstance(meta, dict):
        config["meta"].update({k: v for k, v in meta.items() if k in {"name", "version", "description", "author"}})

    dataset = raw.get("dataset") or {}
    if isinstance(dataset, dict):
        unknown = set(dataset) - set(DATASET_DEFAULTS)
        if unknown:
            raise ConfigError(f"Bagian 'dataset' memuat kunci tidak dikenal: {sorted(unknown)}.")
        for key, value in dataset.items():
            if key == "header_row":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise ConfigError("'dataset.header_row' harus berupa angka (0 = baris pertama).")
                if value < 0:
                    raise ConfigError("'dataset.header_row' tidak boleh negatif.")
            config["dataset"][key] = value

    report = raw.get("report") or {}
    if isinstance(report, dict):
        unknown = set(report) - set(REPORT_DEFAULTS)
        if unknown:
            raise ConfigError(f"Bagian 'report' memuat kunci tidak dikenal: {sorted(unknown)}.")
        config["report"].update(report)

    rules = raw.get("rules") or []
    if not isinstance(rules, list):
        raise ConfigError("'rules' harus berupa daftar aturan.")
    if len(rules) > MAX_RULES:
        raise ConfigError(f"Jumlah aturan melebihi batas {MAX_RULES}.")
    normalized = [normalize_rule(rule, i) for i, rule in enumerate(rules)]

    seen = set()
    for rule in normalized:
        base, n = rule["id"], 2
        while rule["id"] in seen:
            rule["id"] = f"{base}_{n}"
            n += 1
        seen.add(rule["id"])

    config["rules"] = normalized
    return config


# --------------------------------------------------------------------------- #
# (De)serialisasi
# --------------------------------------------------------------------------- #
def config_from_yaml(text: str) -> dict:
    import yaml

    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML tidak valid: {exc}") from exc
    return normalize_config(raw)


def config_to_yaml(config: dict) -> str:
    import yaml

    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True, default_flow_style=False)


def load_config(path: str | Path) -> dict:
    """Baca konfigurasi dari file .yaml/.yml/.json lalu normalkan."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"File konfigurasi tidak ditemukan: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        config = config_from_yaml(text)
    elif suffix == ".json":
        try:
            config = normalize_config(json.loads(text))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"JSON tidak valid: {exc}") from exc
    else:
        raise ConfigError("Format konfigurasi harus .yaml, .yml, atau .json.")
    if not config["rules"]:
        raise ConfigError(f"File konfigurasi {path.name} tidak memuat aturan apa pun.")
    return config


def save_config(config: dict, path: str | Path) -> Path:
    """Simpan konfigurasi (YAML atau JSON sesuai ekstensi)."""
    path = Path(path)
    config = normalize_config(config)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(config_to_yaml(config), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Saran aturan otomatis
# --------------------------------------------------------------------------- #
_ID_HINTS = ("id", "kode", "code", "nik", "no", "nomor", "invoice", "sku", "ref", "kunci", "key")
_DATE_HINTS = ("tanggal", "tgl", "date", "waktu", "time", "created", "updated", "lahir", "expired", "jatuh_tempo")
_AMOUNT_HINTS = ("harga", "price", "total", "amount", "jumlah", "nilai", "biaya", "cost", "gaji", "saldo", "qty", "kuantitas", "diskon")
_EMAIL_HINTS = ("email", "mail", "surel")
_PHONE_HINTS = ("telepon", "telp", "phone", "hp", "whatsapp", "kontak", "mobile")


def suggest_rules(df, profile=None) -> List[dict]:
    """Buat draf aturan yang masuk akal berdasarkan isi dataset.

    Aturan yang diusulkan: wajib terisi untuk kolom yang hampir penuh, nilai unik
    untuk kolom mirip ID, format tanggal untuk kolom tanggal, rentang untuk kolom
    nominal, dan pola untuk email/telepon.
    """
    from .profile import profile_columns  # impor lokal untuk menghindari siklus

    profile = profile if profile is not None else profile_columns(df)
    total = max(len(df), 1)
    rules: List[dict] = []

    for row in profile.to_dict("records"):
        col = row["kolom"]
        lowered = str(col).lower()
        missing_ratio = row["kosong"] / total

        if row["kosong"] > 0 and missing_ratio <= 0.20:
            rules.append(
                {
                    "type": "required",
                    "columns": [col],
                    "severity": "error",
                    "id": f"wajib_{_slug(col)}",
                }
            )
        if any(hint in lowered for hint in _ID_HINTS) and row["unik"] > 1:
            rules.append({"type": "unique", "columns": [col], "severity": "error", "id": f"unik_{_slug(col)}"})
        if any(hint in lowered for hint in _DATE_HINTS) and "angka" not in row["tipe"]:
            rules.append(
                {
                    "type": "date_format",
                    "columns": [col],
                    "severity": "warning",
                    "id": f"tanggal_{_slug(col)}",
                    "formats": [],
                    "strict": True,
                }
            )
        if any(hint in lowered for hint in _AMOUNT_HINTS):
            if "angka" in row["tipe"]:
                # Hanya usulkan rentang bila batas bawahnya jelas (nilai tak negatif).
                if row["min"] is not None and row["min"] >= 0:
                    rules.append(
                        {
                            "type": "range",
                            "columns": [col],
                            "severity": "error",
                            "id": f"rentang_{_slug(col)}",
                            "min": 0,
                        }
                    )
            else:
                rules.append(
                    {"type": "dtype", "columns": [col], "severity": "error", "id": f"tipe_{_slug(col)}", "expected": "number"}
                )
        if any(hint in lowered for hint in _EMAIL_HINTS):
            rules.append(
                {
                    "type": "pattern",
                    "columns": [col],
                    "severity": "error",
                    "id": f"email_{_slug(col)}",
                    "regex": r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$",
                    "hint": "contoh: nama@perusahaan.co.id",
                }
            )
        if any(hint in lowered for hint in _PHONE_HINTS):
            rules.append(
                {
                    "type": "pattern",
                    "columns": [col],
                    "severity": "warning",
                    "id": f"telepon_{_slug(col)}",
                    "regex": r"^(\+62|62|0)8[0-9]{7,12}$",
                    "hint": "contoh: 081234567890",
                }
            )

    return rules


def _slug(text: str) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in str(text).lower())
    return "_".join(part for part in slug.split("_") if part)
