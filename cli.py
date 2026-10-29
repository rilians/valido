#!/usr/bin/env python3
"""Titik masuk CLI Valido.

Pemakaian:
    python cli.py audit data.xlsx --config aturan.yaml --out hasil/
    python cli.py init data.xlsx --out aturan.yaml
    python cli.py profile data.xlsx
    python cli.py rules

Implementasi lengkap ada di paket ``valido.cli`` (dipakai juga lewat
``python -m valido.cli`` atau console script ``valido`` setelah instalasi).
"""

from valido.cli import build_parser, main

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
