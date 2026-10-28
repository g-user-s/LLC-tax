#!/usr/bin/env python3
"""Form 5472 + Pro Forma 1120 veri hazırlayıcı (foreign-owned U.S. DE).

Yalnızca standart kütüphane kullanır; ağ erişimi yoktur. Tüm veri yerelde kalır.

Kullanım:
    python3 generator.py --config config.json --transactions transactions.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

ZERO = Decimal("0")

# category -> (LLC nakit etkisi işareti, ilişkili taraf işlemi mi?)
# Gider kategorilerinde nakit etkisi yalnızca paid_by=llc ise uygulanır.
CATEGORIES = {
    "revenue":                   (+1, False),
    "software_expense":          (-1, False),
    "bank_fee":                  (-1, False),
    "other_expense":             (-1, False),
    "capital_contribution":      (+1, True),
    "owner_draw":                (-1, True),
    "loan_from_owner":           (+1, True),
    "loan_repayment_to_owner":   (-1, True),
    "interest_paid_to_owner":    (-1, True),
    "loan_to_owner":             (-1, True),
    "loan_repayment_from_owner": (+1, True),
}
EXPENSE_CATEGORIES = {"software_expense", "bank_fee", "other_expense"}
PAID_BY = {"llc", "owner"}
REQUIRED_COLUMNS = ["date", "description", "category", "amount_usd", "counterparty", "paid_by"]

EIN_RE = re.compile(r"^\d{2}-\d{7}$")
REF_ID_RE = re.compile(r"^[A-Za-z0-9]{1,50}$")


@dataclass
class Txn:
    line: int
    date: date
    description: str
    category: str
    amount: Decimal
    counterparty: str
    paid_by: str


# --------------------------------------------------------------------------- I/O

def load_config(path: Path, errors: list[str]) -> dict:
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"HATA: config bulunamadı: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"HATA: config geçersiz JSON: {e}")

    def need(obj: dict, key: str, where: str):
        if not str(obj.get(key, "")).strip():
            errors.append(f"config: '{where}.{key}' zorunlu")

    company, owner = cfg.get("company", {}), cfg.get("owner", {})
    if not isinstance(cfg.get("tax_year"), int):
        errors.append("config: 'tax_year' tam sayı olmalı")
    for k in ("name", "ein", "date_incorporated", "principal_business_activity",
              "principal_business_activity_code"):
        need(company, k, "company")
    for k in ("street", "city", "state", "zip"):
        need(company.get("address", {}), k, "company.address")
    for k in ("name", "country_of_citizenship", "country_of_tax_residence"):
        need(owner, k, "owner")
    for k in ("street", "city", "country"):
        need(owner.get("address", {}), k, "owner.address")

    if company.get("ein") and not EIN_RE.match(company["ein"]):
        errors.append("config: EIN formatı NN-NNNNNNN olmalı")
    if company.get("date_incorporated"):
        try:
            date.fromisoformat(company["date_incorporated"])
        except ValueError:
            errors.append("config: 'company.date_incorporated' YYYY-MM-DD olmalı")
    # 8b(2): ABD kimlik no (SSN/ITIN) yoksa reference ID zorunlu
    ref = str(owner.get("reference_id", "")).strip()
    if not str(owner.get("us_tin", "")).strip() and not ref:
        errors.append("config: owner.us_tin yoksa owner.reference_id zorunlu (Part II/III, 4b(2)/8b(2))")
    if ref and not REF_ID_RE.match(ref):
        errors.append("config: reference_id yalnızca harf/rakam, en fazla 50 karakter olmalı")
    need(company, "principal_countries_of_business", "company")
    need(owner, "principal_country_of_business", "owner")
    for where, val in (("owner.address.country", owner.get("address", {}).get("country", "")),
                       ("owner.country_of_citizenship", owner.get("country_of_citizenship", "")),
                       ("owner.country_of_tax_residence", owner.get("country_of_tax_residence", "")),
                       ("owner.principal_country_of_business", owner.get("principal_country_of_business", ""))):
        if 0 < len(val.strip()) <= 3:
            errors.append(f"config: '{where}' kısaltma olmamalı, ülkenin tam adını yazın")
    if owner.get("ownership_percent", 0) < 25:
        errors.append("config: owner.ownership_percent >= 25 olmalı (aksi halde 5472 raporlama mantığı farklı)")
    return cfg


def load_transactions(path: Path, tax_year: int, errors: list[str]) -> list[Txn]:
    try:
        f = path.open(encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        sys.exit(f"HATA: işlem dosyası bulunamadı: {path}")

    txns: list[Txn] = []
    with f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"HATA: CSV'de eksik sütun(lar): {', '.join(missing)}")

        for i, row in enumerate(reader, start=2):
            where = f"{path.name}:{i}"
            try:
                d = date.fromisoformat(row["date"].strip())
            except ValueError:
                errors.append(f"{where}: geçersiz tarih '{row['date']}'")
                continue
            if d.year != tax_year:
                errors.append(f"{where}: tarih {d} vergi yılı ({tax_year}) dışında")

            cat = row["category"].strip()
            if cat not in CATEGORIES:
                errors.append(f"{where}: bilinmeyen kategori '{cat}'")
                continue

            try:
                amt = Decimal(row["amount_usd"].strip())
            except InvalidOperation:
                errors.append(f"{where}: geçersiz tutar '{row['amount_usd']}'")
                continue
            if amt <= 0:
                errors.append(f"{where}: tutar pozitif olmalı (yön kategoriden belirlenir)")

            paid_by = row["paid_by"].strip().lower()
            if paid_by not in PAID_BY:
                errors.append(f"{where}: paid_by 'llc' veya 'owner' olmalı")
            if cat in ("capital_contribution", "loan_from_owner", "loan_repayment_from_owner") \
                    and paid_by != "owner":
                errors.append(f"{where}: '{cat}' için paid_by=owner olmalı")
            if cat in ("owner_draw", "loan_repayment_to_owner", "interest_paid_to_owner",
                       "loan_to_owner", "revenue") and paid_by != "llc":
                errors.append(f"{where}: '{cat}' için paid_by=llc olmalı")

            txns.append(Txn(i, d, row["description"].strip(), cat, amt,
                            row["counterparty"].strip(), paid_by))
    return txns


# ----------------------------------------------------------------------- Hesap

def compute(cfg: dict, txns: list[Txn], warnings: list[str]) -> dict:
    """Satır numaraları Form 5472 (Rev. 12-2023) ve talimatı (Rev. 12-2024) esas alır."""
    company, owner, opts = cfg["company"], cfg["owner"], cfg.get("options", {})
    year = cfg["tax_year"]
    whole = opts.get("round_to_whole_dollars", True)

    def money(x: Decimal):
        q = Decimal("1") if whole else Decimal("0.01")
        v = x.quantize(q, rounding=ROUND_HALF_UP)
        return int(v) if whole else float(v)

    def total(*cats):
        return sum((t.amount for t in txns if t.category in cats), ZERO)

    # --- Nakit / toplam varlık (yalnızca LLC hesabından geçen hareketler)
    cash = Decimal(str(company.get("opening_cash_balance_usd", 0)))
    for t in sorted(txns, key=lambda t: t.date):
        sign, _ = CATEGORIES[t.category]
        if t.category in EXPENSE_CATEGORIES and t.paid_by == "owner":
            continue  # LLC hesabından çıkmadı
        cash += sign * t.amount
        if cash < 0:
            warnings.append(f"satır {t.line}: {t.date} itibarıyla nakit bakiye negatif ({cash})")
    total_assets = cash  # Varsayım: LLC'nin tek varlığı nakit

    # --- Part V: sermaye/çekim. Reg. §1.6038A-2(b)(3)(xi); satır 21/35 yalnızca
    # vergilendirilebilir geliri etkileyen tutarlar içindir ((b)(3)(x)), bu yüzden Part IV'e girmez.
    contributions = total("capital_contribution")
    owner_paid_exp = sum((t.amount for t in txns
                          if t.category in EXPENSE_CATEGORIES and t.paid_by == "owner"), ZERO)
    draws = total("owner_draw")
    part_v_total = contributions + owner_paid_exp + draws

    # --- Part IV
    interest_paid = total("interest_paid_to_owner")
    borrowed_beg = Decimal(str(owner.get("opening_loan_balance_from_owner_usd", 0)))
    borrowed_end = borrowed_beg + total("loan_from_owner") - total("loan_repayment_to_owner")
    loaned_beg = Decimal(str(owner.get("opening_loan_balance_to_owner_usd", 0)))
    loaned_end = loaned_beg + total("loan_to_owner") - total("loan_repayment_from_owner")
    if borrowed_end < 0 or loaned_end < 0:
        warnings.append("borç bakiyesi negatif çıktı: açılış bakiyelerini/geri ödemeleri kontrol edin")
    has_loan = any(v != 0 for v in (borrowed_beg, borrowed_end, loaned_beg, loaned_end))

    line22 = borrowed_end                 # 9–21 toplamı; 17'de yalnızca 17b sütuna girer
    line36 = loaned_end + interest_paid   # 23–35 toplamı; 31'de yalnızca 31b sütuna girer
    # 1f: Part IV + VI (+ DE ise Part V) değerleri
    gross_payments = line22 + line36 + part_v_total

    # --- Defter özeti (formlara girmez; kontrol amaçlı)
    revenue = total("revenue")
    expenses = {c: total(c) for c in sorted(EXPENSE_CATEGORIES)}
    expenses["interest_paid_to_owner"] = interest_paid
    net_income = revenue - sum(expenses.values(), ZERO)

    def addr(a: dict) -> str:
        parts = [a.get("street"), a.get("city"), a.get("state"), a.get("province"),
                 a.get("zip"), a.get("country")]
        return ", ".join(p for p in parts if p)

    first_year = bool(company.get("first_year_filing_5472"))
    if not first_year and date.fromisoformat(company["date_incorporated"]).year == year:
        warnings.append("kuruluş yılı = vergi yılı ama first_year_filing_5472=false; kontrol edin")
    if has_loan:
        warnings.append("ortakla borç var: Part VII 42a/42b (faiz oranı AFR'nin %100–130 aralığında mı?) elle cevaplanmalı")
    if interest_paid:
        warnings.append("ortağa faiz ödendi: Part VII 40a (section 267A) kontrol edilmeli")

    m = money
    ftin = owner.get("foreign_tin") or "None"
    owner_addr = f"{owner['name']} — {addr(owner['address'])}"
    tax_year_txt = f"{year}-01-01 / {year}-12-31"

    pro_forma_1120 = [
        ("Header", "Üst kenara yazılacak ibare", "Foreign-owned U.S. DE"),
        ("Header", "Tax year", tax_year_txt),
        ("Name", "Corporation name", company["name"]),
        ("Address", "Number, street, city, state, ZIP", addr(company["address"])),
        ("B", "Employer identification number", company["ein"]),
        ("C", "Date incorporated (isteğe bağlı)", company["date_incorporated"]),
        ("D", "Total assets (5472 1c bu kalemden alınır)", m(total_assets)),
        ("E(1)", "Initial return", "X" if first_year else ""),
        ("Diğer", "Gelir/gider satırları", "BOŞ (yalnızca isim, adres, B ve E zorunlu)"),
    ]

    form_5472 = [
        ("Header", "", "Tax year beginning / ending", tax_year_txt),
        # Part I
        ("I", "1a", "Name & address of reporting corporation",
         f"{company['name']} — {addr(company['address'])}"),
        ("I", "1b", "Employer identification number", company["ein"]),
        ("I", "1c", "Total assets", m(total_assets)),
        ("I", "1d", "Principal business activity", company["principal_business_activity"]),
        ("I", "1e", "Principal business activity code", company["principal_business_activity_code"]),
        ("I", "1f", "Total value of gross payments (IV + V)", m(gross_payments)),
        ("I", "1g", "Total number of Forms 5472 filed", 1),
        ("I", "1h", "Total value of gross payments (all forms)", m(gross_payments)),
        ("I", "1i", "Consolidated filing", ""),
        ("I", "1j", "Initial year filing Form 5472", "X" if first_year else ""),
        ("I", "1k", "Total number of Parts VIII attached", 0),
        ("I", "1l", "Country of incorporation", "United States"),
        ("I", "1m", "Date of incorporation", company["date_incorporated"]),
        ("I", "1n", "Country(ies) where files tax return as resident", "United States"),
        ("I", "1o", "Principal country(ies) where business is conducted",
         company["principal_countries_of_business"]),
        ("I", "2", "Foreign person owns >= 50%", "X" if owner.get("ownership_percent", 0) >= 50 else ""),
        ("I", "3", "Foreign-owned U.S. DE", "X"),
        # Part II
        ("II", "4a", "Name & address of direct 25% foreign shareholder", owner_addr),
        ("II", "4b(1)", "U.S. identifying number", owner.get("us_tin", "")),
        ("II", "4b(2)", "Reference ID number", owner.get("reference_id", "")),
        ("II", "4b(3)", "FTIN", ftin),
        ("II", "4c", "Principal country(ies) of business", owner["principal_country_of_business"]),
        ("II", "4d", "Country of citizenship", owner["country_of_citizenship"]),
        ("II", "4e", "Country(ies) of tax residence", owner["country_of_tax_residence"]),
        # Part III
        ("III", "head", "Related party is a", "X  foreign person"),
        ("III", "8a", "Name & address of related party", owner_addr),
        ("III", "8b(1)", "U.S. identifying number", owner.get("us_tin", "")),
        ("III", "8b(2)", "Reference ID number", owner.get("reference_id", "")),
        ("III", "8b(3)", "FTIN", ftin),
        ("III", "8c", "Principal business activity", owner.get("principal_business_activity", "")),
        ("III", "8d", "Principal business activity code", owner.get("principal_business_activity_code", "")),
        ("III", "8e", "Relationship", "X  25% foreign shareholder"),
        ("III", "8f", "Principal country(ies) of business", owner["principal_country_of_business"]),
        ("III", "8g", "Country(ies) of tax residence", owner["country_of_tax_residence"]),
        # Part IV — yalnızca ilgili satırlar; diğerleri boş
        ("IV", "17a", "Amounts borrowed — beginning balance", m(borrowed_beg)),
        ("IV", "17b", "Amounts borrowed — ending balance", m(borrowed_end)),
        ("IV", "22", "Total (lines 9–21)", m(line22)),
        ("IV", "31a", "Amounts loaned — beginning balance", m(loaned_beg)),
        ("IV", "31b", "Amounts loaned — ending balance", m(loaned_end)),
        ("IV", "32", "Interest paid", m(interest_paid)),
        ("IV", "36", "Total (lines 23–35)", m(line36)),
        # Part V / VI
        ("V", "check", "Contributions/distributions — see attached statement",
         "X" if part_v_total else ""),
        ("VI", "check", "Nonmonetary / less-than-full consideration", ""),
        # Part VII — tüm filer'lar doldurur
        ("VII", "37", "Imports goods from foreign related party?", "No"),
        ("VII", "39", "Foreign parent in a cost sharing arrangement?", "No"),
        ("VII", "40a", "Interest/royalty disallowed under sec. 267A?", "No"),
        ("VII", "41a", "Claiming FDII deduction?", "No"),
        ("VII", "42a", "Loan with rate inside AFR safe-haven range?", "KONTROL ET" if has_loan else "No"),
        ("VII", "42b", "Loan with rate outside AFR safe-haven range?", "KONTROL ET" if has_loan else "No"),
        ("VII", "43a", "Covered debt instrument (Reg. 1.385-3)?", "No"),
    ]

    part_v_lines = [
        f"FORM 5472 — PART V STATEMENT — {company['name']} (EIN {company['ein']}) — Tax year {year}",
        f"Related party: {owner['name']} ({owner.get('ownership_percent')}% foreign owner)",
        "Reportable transactions under Regulations section 1.482-1(i)(7) not reported in Part IV.",
        "",
        f"{'Capital contributions from owner (cash):':<55}${m(contributions):>12,}",
        f"{'LLC expenses paid personally by owner (contribution):':<55}${m(owner_paid_exp):>12,}",
        f"{'Distributions to owner:':<55}${m(draws):>12,}",
        "",
        "Detail:",
    ]
    for t in sorted(txns, key=lambda t: t.date):
        is_owner_exp = t.category in EXPENSE_CATEGORIES and t.paid_by == "owner"
        if t.category in ("capital_contribution", "owner_draw") or is_owner_exp:
            kind = {"capital_contribution": "contribution", "owner_draw": "distribution"}.get(
                t.category, "owner-paid expense")
            part_v_lines.append(f"  {t.date}  {kind:<20} ${t.amount:>10,.2f}  {t.description}")

    return {
        "tax_year": year,
        "form_revision": "Form 5472 Rev. 12-2023 / Instructions Rev. 12-2024",
        "pro_forma_1120": [dict(zip(("line", "description", "value"), r)) for r in pro_forma_1120],
        "form_5472": [dict(zip(("part", "line", "description", "value"), r)) for r in form_5472],
        "part_v_statement": "\n".join(part_v_lines),
        "books_summary": {
            "opening_cash": m(Decimal(str(company.get("opening_cash_balance_usd", 0)))),
            "ending_cash": m(cash),
            "revenue": m(revenue),
            "expenses": {k: m(v) for k, v in expenses.items()},
            "net_income": m(net_income),
            "transaction_count": len(txns),
        },
    }


# ---------------------------------------------------------------------- Çıktı

def print_report(r: dict) -> None:
    def table(title, rows, cols):
        print(f"\n=== {title} ===")
        widths = [max(len(str(row[c])) for row in rows + [dict(zip(cols, cols))]) for c in cols]
        widths[-2] = min(widths[-2], 58)
        for row in [dict(zip(cols, [c.upper() for c in cols]))] + rows:
            cells = [str(row[c])[:widths[i]].ljust(widths[i]) for i, c in enumerate(cols)]
            print("  " + "  ".join(cells))

    table(f"PRO FORMA FORM 1120 — {r['tax_year']}", r["pro_forma_1120"],
          ["line", "description", "value"])
    table(f"FORM 5472 — {r['tax_year']} ({r['form_revision']})", r["form_5472"],
          ["part", "line", "description", "value"])
    print("\n=== PART V STATEMENT (ek sayfa) ===\n" + r["part_v_statement"])
    print("\n=== DEFTER ÖZETİ (formlara girmez) ===")
    print(json.dumps(r["books_summary"], indent=2, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(description="Form 5472 + Pro Forma 1120 veri hazırlayıcı")
    ap.add_argument("--config", default="config.json", type=Path)
    ap.add_argument("--transactions", default="transactions.csv", type=Path)
    ap.add_argument("--output-dir", default="output", type=Path)
    ap.add_argument("--no-write", action="store_true", help="Sadece konsola bas, dosya yazma")
    args = ap.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    cfg = load_config(args.config, errors)
    txns = load_transactions(args.transactions, cfg.get("tax_year", 0), errors)

    if errors:
        print("DOĞRULAMA HATALARI:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    report = compute(cfg, txns, warnings)
    print_report(report)

    if warnings:
        print("\nUYARILAR:")
        for w in warnings:
            print(f"  ! {w}")

    if not args.no_write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        year = report["tax_year"]
        json_path = args.output_dir / f"form_data_{year}.json"
        txt_path = args.output_dir / f"part_v_statement_{year}.txt"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        txt_path.write_text(report["part_v_statement"] + "\n", encoding="utf-8")
        print(f"\nYazıldı: {json_path}\nYazıldı: {txt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
