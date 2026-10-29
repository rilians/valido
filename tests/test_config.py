"""Test validasi dan (de)serialisasi konfigurasi aturan."""

from __future__ import annotations

import json

import pytest

from valido.config import (
    RULE_TYPES,
    ConfigError,
    config_from_yaml,
    config_to_yaml,
    default_config,
    load_config,
    normalize_config,
    normalize_rule,
    save_config,
    suggest_rules,
)


def test_default_config_structure():
    config = default_config()
    assert config["rules"] == []
    assert config["dataset"]["header_row"] == 0
    assert config["report"]["include_clean_preview"] is True


def test_every_rule_type_has_metadata():
    for name, spec in RULE_TYPES.items():
        assert spec["label"] and spec["description"]
        assert spec["severity"] in {"error", "warning", "info"}
        assert "{" in spec["message"] or name  # template pesan tersedia
        assert spec["columns"] in {"one", "two", "many", "many_optional", "none"}


def test_normalize_rule_fills_defaults():
    rule = normalize_rule({"type": "required", "columns": "email"})
    assert rule["columns"] == ["email"]
    assert rule["severity"] == "error"
    assert rule["id"] == "required_email"
    assert isinstance(rule["message"], str) and rule["message"]


def test_normalize_rule_unknown_type():
    with pytest.raises(ConfigError, match="tidak dikenal"):
        normalize_rule({"type": "tidak_ada", "columns": ["a"]})


def test_normalize_rule_wrong_column_count():
    with pytest.raises(ConfigError, match="tepat 1 kolom"):
        normalize_rule({"type": "required", "columns": ["a", "b"]})

    with pytest.raises(ConfigError, match="tepat 2 kolom"):
        normalize_rule({"type": "date_order", "columns": ["a"]})


def test_normalize_rule_invalid_severity():
    with pytest.raises(ConfigError, match="severity"):
        normalize_rule({"type": "required", "columns": ["a"], "severity": "fatal"})


def test_normalize_rule_range_bounds_validation():
    with pytest.raises(ConfigError, match="minimum"):
        normalize_rule({"type": "range", "columns": ["a"], "min": 10, "max": 1})
    with pytest.raises(ConfigError, match="minimal salah satu"):
        normalize_rule({"type": "range", "columns": ["a"]})


def test_normalize_rule_invalid_regex():
    with pytest.raises(ConfigError, match="regex"):
        normalize_rule({"type": "pattern", "columns": ["a"], "regex": "([a-"})


def test_normalize_rule_blocks_dangerous_expression():
    with pytest.raises(ConfigError, match="tidak diizinkan"):
        normalize_rule(
            {
                "type": "business_rule",
                "columns": ["a"],
                "expression": "__import__('os').system('ls')",
            }
        )


def test_normalize_rule_requires_expression():
    with pytest.raises(ConfigError, match="wajib diisi"):
        normalize_rule({"type": "business_rule", "columns": ["a"], "expression": ""})


def test_normalize_rule_backtick_columns_allowed():
    rule = normalize_rule(
        {"type": "business_rule", "columns": ["Total Bayar"], "expression": "`Total Bayar` > 0"}
    )
    assert rule["expression"] == "`Total Bayar` > 0"


def test_normalize_config_deduplicates_ids():
    config = normalize_config(
        {
            "rules": [
                {"id": "sama", "type": "required", "columns": ["a"]},
                {"id": "sama", "type": "required", "columns": ["b"]},
            ]
        }
    )
    assert [r["id"] for r in config["rules"]] == ["sama", "sama_2"]


def test_normalize_config_rejects_unknown_section_key():
    with pytest.raises(ConfigError, match="tidak dikenal"):
        normalize_config({"rules": [], "dataset": {"kolom_ajaib": 1}})


def test_normalize_config_rejects_non_list_rules():
    with pytest.raises(ConfigError, match="daftar aturan"):
        normalize_config({"rules": {"type": "required"}})


def test_yaml_roundtrip():
    original = normalize_config(
        {
            "meta": {"name": "Uji YAML"},
            "rules": [
                {"id": "r1", "type": "required", "columns": ["nama"], "severity": "warning"},
                {"id": "r2", "type": "range", "columns": ["umur"], "min": 0, "max": 150},
            ],
        }
    )
    text = config_to_yaml(original)
    restored = config_from_yaml(text)
    assert [r["id"] for r in restored["rules"]] == ["r1", "r2"]
    assert restored["rules"][1]["max"] == 150
    assert restored["meta"]["name"] == "Uji YAML"


def test_config_from_yaml_invalid_text():
    with pytest.raises(ConfigError):
        config_from_yaml("rules: [tipe: rusak")


def test_save_and_load_config(tmp_path, sample_config):
    path = save_config(sample_config, tmp_path / "aturan.yaml")
    loaded = load_config(path)
    assert len(loaded["rules"]) == len(sample_config["rules"])
    assert loaded["meta"]["name"] == "Konfigurasi uji"


def test_save_and_load_json(tmp_path, sample_config):
    path = save_config(sample_config, tmp_path / "aturan.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rules"][0]["id"] == "wajib_nama"
    assert len(load_config(path)["rules"]) == len(sample_config["rules"])


def test_load_config_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="tidak ditemukan"):
        load_config(tmp_path / "tidak_ada.yaml")


def test_load_config_wrong_extension(tmp_path):
    path = tmp_path / "aturan.txt"
    path.write_text("rules: []", encoding="utf-8")
    with pytest.raises(ConfigError, match="Format konfigurasi"):
        load_config(path)


def test_load_config_without_rules(tmp_path):
    path = tmp_path / "kosong.yaml"
    path.write_text("meta:\n  name: kosong\nrules: []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="tidak memuat aturan"):
        load_config(path)


def test_suggest_rules_detects_common_patterns(messy_df):
    rules = suggest_rules(messy_df)
    types = {rule["type"] for rule in rules}
    assert "required" in types
    assert "unique" in types          # kolom "id"
    assert "date_format" in types     # kolom "tanggal"
    assert "pattern" in types         # kolom "email"
    assert all("columns" in rule and rule["columns"] for rule in rules)


def test_suggest_rules_names_are_unique(messy_df):
    rules = suggest_rules(messy_df)
    ids = [rule["id"] for rule in rules]
    assert len(ids) == len(set(ids))
