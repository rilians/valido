"""Test antarmuka baris perintah Valido."""

from __future__ import annotations

from pathlib import Path

from valido import cli


def test_cli_rules_command(capsys):
    assert cli.main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "business_rule" in out
    assert "required" in out


def test_cli_sheets_command(xlsx_file, capsys):
    assert cli.main(["sheets", str(xlsx_file)]) == 0
    out = capsys.readouterr().out
    assert "Data" in out and "Ringkas" in out


def test_cli_audit_with_config(xlsx_file, config_file, tmp_path, capsys):
    out_dir = tmp_path / "hasil"
    code = cli.main(
        [
            "audit",
            str(xlsx_file),
            "--config",
            str(config_file),
            "--sheet",
            "Data",
            "--out",
            str(out_dir),
        ]
    )
    assert code == 0
    assert (out_dir / "laporan_valido.xlsx").exists()
    assert (out_dir / "temuan_valido.csv").exists()
    out = capsys.readouterr().out
    assert "SKOR KESEHATAN DATA" in out
    assert "Laporan Excel" in out


def test_cli_audit_without_config_uses_suggestions(csv_file, tmp_path, capsys):
    out_dir = tmp_path / "auto"
    code = cli.main(["audit", str(csv_file), "--out", str(out_dir)])
    assert code == 0
    assert (out_dir / "aturan_otomatis.yaml").exists()
    assert (out_dir / "laporan_valido.xlsx").exists()


def test_cli_audit_invalid_config(csv_file, tmp_path, capsys):
    bad = tmp_path / "rusak.yaml"
    bad.write_text("rules:\n  - type: tidak_ada\n    columns: [a]\n", encoding="utf-8")
    code = cli.main(["audit", str(csv_file), "--config", str(bad), "--out", str(tmp_path / "x")])
    assert code == 2


def test_cli_audit_missing_file(tmp_path, capsys):
    code = cli.main(["audit", str(tmp_path / "hilang.csv")])
    assert code == 2


def test_cli_init_creates_config(csv_file, tmp_path, capsys):
    target = tmp_path / "draf.yaml"
    assert cli.main(["init", str(csv_file), "--out", str(target)]) == 0
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "rules:" in text
    assert "type:" in text


def test_cli_profile(csv_file, capsys):
    assert cli.main(["profile", str(csv_file)]) == 0
    out = capsys.readouterr().out
    assert "Tipe Terdeteksi" in out


def test_cli_audit_with_profile_flag(csv_file, config_file, tmp_path, capsys):
    code = cli.main(
        ["audit", str(csv_file), "--config", str(config_file), "--out", str(tmp_path / "p"), "--profile"]
    )
    assert code == 0
    assert "PROFIL KOLOM" in capsys.readouterr().out


def test_cli_print_config(csv_file, config_file, tmp_path, capsys):
    code = cli.main(
        ["audit", str(csv_file), "--config", str(config_file), "--out", str(tmp_path / "q"), "--print-config"]
    )
    assert code == 0
    assert "rules:" in capsys.readouterr().out
