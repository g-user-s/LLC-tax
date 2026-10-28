#!/usr/bin/env python3
"""Komut satırı sürümü: config.json + transactions.csv -> satır matrisi (+ isteğe bağlı PDF).

Grafik arayüz için: python3 app.py

Kullanım:
    python3 generator.py --config config.json --transactions transactions.csv [--pdf]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from llc_tax import engine


def load_case(config: Path, transactions: Path) -> dict:
    try:
        case = json.loads(config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"HATA: config bulunamadı: {config}")
    except json.JSONDecodeError as e:
        sys.exit(f"HATA: config geçersiz JSON: {e}")
    try:
        with transactions.open(encoding="utf-8-sig", newline="") as f:
            case["transactions"] = list(csv.DictReader(f))
    except FileNotFoundError:
        sys.exit(f"HATA: işlem dosyası bulunamadı: {transactions}")
    return case


def print_table(title: str, rows: list[dict]) -> None:
    print(f"\n=== {title} ===")
    cols = list(rows[0].keys())
    widths = [min(max(len(str(r[c])) for r in rows + [dict(zip(cols, cols))]), 60) for c in cols]
    for r in [dict(zip(cols, [c.upper() for c in cols]))] + rows:
        print("  " + "  ".join(str(r[c])[:w].ljust(w) for c, w in zip(cols, widths)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Form 5472 + Pro Forma 1120 veri hazırlayıcı")
    ap.add_argument("--config", default="config.json", type=Path)
    ap.add_argument("--transactions", default="transactions.csv", type=Path)
    ap.add_argument("--output-dir", default="output", type=Path)
    ap.add_argument("--pdf", action="store_true", help="Doldurulmuş PDF'leri de üret")
    args = ap.parse_args()

    case = load_case(args.config, args.transactions)
    errors, txns = engine.validate(case)
    if errors:
        print("DOĞRULAMA HATALARI:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    result = engine.compute(case, txns)
    print_table(f"PRO FORMA FORM 1120 — {result['tax_year']}", result["rows_1120"])
    print_table(f"FORM 5472 — {result['tax_year']} ({result['form_revision']})", result["rows_5472"])
    print("\n=== PART V STATEMENT ===\n" + "\n".join(result["part_v_statement"]))
    print("\n=== DEFTER ÖZETİ (formlara girmez) ===")
    for k, v in result["books"].items():
        print(f"  {k:<40} {v:>10,}")
    if result["warnings"]:
        print("\nUYARILAR:")
        for w in result["warnings"]:
            print(f"  ! {w}")

    if args.pdf:
        from llc_tax import pdf_fill
        out_dir = args.output_dir / str(result["tax_year"])
        out = pdf_fill.generate(case, result, out_dir)
        for f in out["files"]:
            print(f"Yazıldı: {out_dir / f}")
        for m in out["missing"]:
            print(f"EKSİK: {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
