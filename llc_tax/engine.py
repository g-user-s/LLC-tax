"""Doğrulama ve hesaplama motoru (foreign-owned U.S. DE, tek üyeli LLC).

Satır numaraları Form 5472 (Rev. 12-2023) ve talimatı (Rev. 12-2024) esas alır.
Girdi tek bir "case" sözlüğüdür; arayüz, CLI ve PDF doldurucu bunu paylaşır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
FORM_REVISION = "Form 5472 Rev. 12-2023 / Instructions Rev. 12-2024"

# category -> (Türkçe etiket, LLC nakit etkisi işareti, ilişkili taraf işlemi mi?)
# Gider kategorilerinde nakit etkisi yalnızca paid_by=llc ise uygulanır.
CATEGORIES = {
    "revenue":                   ("Gelir (App Store / Google Play)", +1, False),
    "software_expense":          ("Yazılım / abonelik gideri", -1, False),
    "bank_fee":                  ("Banka ücreti", -1, False),
    "other_expense":             ("Diğer gider", -1, False),
    "capital_contribution":      ("Sermaye (ortaktan LLC'ye)", +1, True),
    "owner_draw":                ("Kişisel çekim (LLC'den ortağa)", -1, True),
    "loan_from_owner":           ("Ortaktan alınan borç", +1, True),
    "loan_repayment_to_owner":   ("Ortağa borç geri ödemesi", -1, True),
    "interest_paid_to_owner":    ("Ortağa ödenen faiz", -1, True),
    "loan_to_owner":             ("Ortağa verilen borç", -1, True),
    "loan_repayment_from_owner": ("Ortaktan borç tahsilatı", +1, True),
    "internal_transfer":         ("LLC hesapları arası transfer (yok sayılır)", 0, False),
}
EXPENSE_CATEGORIES = {"software_expense", "bank_fee", "other_expense"}
OWNER_PAYS = {"capital_contribution", "loan_from_owner", "loan_repayment_from_owner"}
LLC_PAYS = {"owner_draw", "loan_repayment_to_owner", "interest_paid_to_owner",
            "loan_to_owner", "revenue", "internal_transfer"}

# Uygulamayı kullanabilmek için hepsi "evet" olmalı.
ELIGIBILITY = [
    ("nm_llc", "LLC New Mexico eyaletinde kuruldu."),
    ("single_member", "LLC'nin tek bir sahibi (üyesi) var."),
    ("no_election", "IRS'e corporation olarak vergilendirilme seçimi yapılmadı (Form 8832 / 2553 verilmedi)."),
    ("owner_nonresident", "Sahip ABD vatandaşı, green card sahibi veya ABD vergi mukimi değil."),
    ("owner_not_in_us", "Sahip yıl içinde ABD'de yaşamadı ve işi ABD dışından yürüttü."),
    ("app_store_income", "LLC'nin geliri yalnızca App Store / Google Play kaynaklı."),
    ("no_us_presence", "LLC'nin ABD'de ofisi, çalışanı veya adına iş yapan bir temsilcisi yok."),
]

EIN_RE = re.compile(r"^\d{2}-\d{7}$")
REF_ID_RE = re.compile(r"^[A-Za-z0-9]{1,50}$")


@dataclass
class Txn:
    idx: int
    date: date
    description: str
    category: str
    amount: Decimal
    counterparty: str
    paid_by: str


def empty_case(year: int) -> dict:
    return {
        "tax_year": year,
        "eligibility": {k: False for k, _ in ELIGIBILITY},
        "company": {
            "name": "", "ein": "",
            "address": {"street": "", "city": "", "state": "NM", "zip": ""},
            "date_incorporated": "",
            "principal_business_activity": "Software publishers",
            "principal_business_activity_code": "513210",
            "principal_countries_of_business": "United States",
            "first_year_filing_5472": False,
            "opening_cash_balance_usd": "0",
            "ending_cash_balance_usd_actual": "",
        },
        "owner": {
            "name": "",
            "address": {"street": "", "city": "", "province": "", "zip": "", "country": ""},
            "us_tin": "", "foreign_tin": "", "reference_id": "",
            "country_of_citizenship": "", "country_of_tax_residence": "",
            "principal_country_of_business": "",
            "principal_business_activity": "", "principal_business_activity_code": "",
            "opening_loan_balance_from_owner_usd": "0",
            "opening_loan_balance_to_owner_usd": "0",
        },
        "part_vii": {"q42a": "", "q42b": ""},
        "transactions": [],
    }


def dec(v, default=ZERO) -> Decimal:
    s = str(v if v is not None else "").replace(",", "").replace("$", "").strip()
    if not s:
        return default
    return Decimal(s)


# ----------------------------------------------------------------- Doğrulama

def validate(case: dict) -> tuple[list[str], list[Txn]]:
    errors: list[str] = []
    company, owner = case.get("company", {}), case.get("owner", {})
    year = case.get("tax_year")

    def need(obj: dict, key: str, label: str):
        if not str(obj.get(key, "")).strip():
            errors.append(f"{label} zorunlu")

    elig = case.get("eligibility", {})
    if not all(elig.get(k) for k, _ in ELIGIBILITY):
        errors.append("Uygunluk: tüm koşullar sağlanmadan form hazırlanamaz")

    if not isinstance(year, int) or not 2018 <= year <= 2100:
        errors.append("Vergi yılı geçersiz")

    need(company, "name", "Şirket: LLC adı")
    need(company, "ein", "Şirket: EIN")
    need(company, "date_incorporated", "Şirket: kuruluş tarihi")
    need(company, "principal_business_activity", "Şirket: faaliyet tanımı")
    need(company, "principal_business_activity_code", "Şirket: faaliyet kodu")
    need(company, "principal_countries_of_business", "Şirket: işin yürütüldüğü ülke(ler)")
    caddr = company.get("address", {})
    for k, lbl in (("street", "sokak/adres"), ("city", "şehir"), ("state", "eyalet"), ("zip", "ZIP")):
        need(caddr, k, f"Şirket adresi: {lbl}")
    if company.get("ein") and not EIN_RE.match(company["ein"].strip()):
        errors.append("Şirket: EIN formatı 12-3456789 şeklinde olmalı")
    if company.get("date_incorporated"):
        try:
            inc = date.fromisoformat(company["date_incorporated"])
            if isinstance(year, int) and inc.year > year:
                errors.append("Şirket: kuruluş tarihi vergi yılından sonra olamaz")
        except ValueError:
            errors.append("Şirket: kuruluş tarihi YYYY-AA-GG olmalı")
    for k, lbl in (("opening_cash_balance_usd", "yıl başı banka bakiyesi"),
                   ("ending_cash_balance_usd_actual", "yıl sonu banka bakiyesi")):
        try:
            dec(company.get(k))
        except InvalidOperation:
            errors.append(f"Şirket: {lbl} sayı olmalı")

    need(owner, "name", "Ortak: ad soyad")
    oaddr = owner.get("address", {})
    for k, lbl in (("street", "adres"), ("city", "şehir"), ("country", "ülke")):
        need(oaddr, k, f"Ortak adresi: {lbl}")
    need(owner, "country_of_citizenship", "Ortak: vatandaşlık ülkesi")
    need(owner, "country_of_tax_residence", "Ortak: vergi mukimi olduğu ülke")
    need(owner, "principal_country_of_business", "Ortak: iş yaptığı ülke")
    # 4b(2)/8b(2): ABD kimlik no (SSN/ITIN) yoksa reference ID zorunlu
    ref = str(owner.get("reference_id", "")).strip()
    if not str(owner.get("us_tin", "")).strip() and not ref:
        errors.append("Ortak: ITIN/SSN yoksa Reference ID zorunlu")
    if ref and not REF_ID_RE.match(ref):
        errors.append("Ortak: Reference ID yalnızca harf/rakam, en fazla 50 karakter olmalı")
    for lbl, val in (("adres ülkesi", oaddr.get("country", "")),
                     ("vatandaşlık ülkesi", owner.get("country_of_citizenship", "")),
                     ("vergi mukimi ülke", owner.get("country_of_tax_residence", "")),
                     ("iş yaptığı ülke", owner.get("principal_country_of_business", ""))):
        if 0 < len(val.strip()) <= 3:
            errors.append(f"Ortak: {lbl} kısaltma olmamalı, tam adı yazın (örn. Turkey)")
    for k in ("opening_loan_balance_from_owner_usd", "opening_loan_balance_to_owner_usd"):
        try:
            dec(owner.get(k))
        except InvalidOperation:
            errors.append("Ortak: yıl başı borç bakiyesi sayı olmalı")

    txns: list[Txn] = []
    for i, row in enumerate(case.get("transactions", []), start=1):
        where = f"İşlem #{i}"
        try:
            d = date.fromisoformat(str(row.get("date", "")).strip())
        except ValueError:
            errors.append(f"{where}: geçersiz tarih '{row.get('date')}'")
            continue
        if isinstance(year, int) and d.year != year:
            errors.append(f"{where}: tarih {d} vergi yılı ({year}) dışında")
        cat = str(row.get("category", "")).strip()
        if cat not in CATEGORIES:
            errors.append(f"{where}: kategori seçilmedi ({row.get('description', '')})")
            continue
        try:
            amt = dec(row.get("amount_usd"))
        except InvalidOperation:
            errors.append(f"{where}: geçersiz tutar '{row.get('amount_usd')}'")
            continue
        if amt <= 0:
            errors.append(f"{where}: tutar pozitif olmalı (yön kategoriden belirlenir)")
        paid_by = str(row.get("paid_by", "")).strip().lower()
        if paid_by not in ("llc", "owner"):
            errors.append(f"{where}: ödeyen 'LLC' veya 'Ortak' olmalı")
        if cat in OWNER_PAYS and paid_by != "owner":
            errors.append(f"{where}: '{CATEGORIES[cat][0]}' için ödeyen Ortak olmalı")
        if cat in LLC_PAYS and paid_by != "llc":
            errors.append(f"{where}: '{CATEGORIES[cat][0]}' için ödeyen LLC olmalı")
        txns.append(Txn(i, d, str(row.get("description", "")).strip(), cat, amt,
                        str(row.get("counterparty", "")).strip(), paid_by))
    return errors, txns


# ------------------------------------------------------------------- Hesap

def compute(case: dict, txns: list[Txn]) -> dict:
    company, owner = case["company"], case["owner"]
    year = case["tax_year"]
    warnings: list[str] = []

    def total(*cats):
        return sum((t.amount for t in txns if t.category in cats), ZERO)

    def m(x: Decimal) -> int:
        return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    # Nakit / toplam varlık (yalnızca LLC hesabından geçen hareketler)
    opening = dec(company.get("opening_cash_balance_usd"))
    cash = opening
    for t in sorted(txns, key=lambda t: t.date):
        sign = CATEGORIES[t.category][1]
        if t.category in EXPENSE_CATEGORIES and t.paid_by == "owner":
            continue  # LLC hesabından çıkmadı
        cash += sign * t.amount
        if cash < 0:
            warnings.append(f"İşlem #{t.idx}: {t.date} itibarıyla nakit bakiye negatif ({cash})")
    actual = str(company.get("ending_cash_balance_usd_actual", "")).strip()
    if actual and abs(dec(actual) - cash) >= 1:
        warnings.append(f"Hesaplanan yıl sonu bakiyesi ({cash:,.2f}) banka bakiyesinden "
                        f"({dec(actual):,.2f}) farklı: eksik/hatalı işlem olabilir")
    total_assets = cash  # Varsayım: LLC'nin tek varlığı nakit

    # Part V: sermaye/çekim. Reg. §1.6038A-2(b)(3)(xi); satır 21/35 yalnızca
    # vergilendirilebilir geliri etkileyen tutarlar içindir ((b)(3)(x)).
    contributions = total("capital_contribution")
    owner_paid_exp = sum((t.amount for t in txns
                          if t.category in EXPENSE_CATEGORIES and t.paid_by == "owner"), ZERO)
    draws = total("owner_draw")
    part_v_total = contributions + owner_paid_exp + draws

    # Part IV
    interest_paid = total("interest_paid_to_owner")
    borrowed_beg = dec(owner.get("opening_loan_balance_from_owner_usd"))
    borrowed_end = borrowed_beg + total("loan_from_owner") - total("loan_repayment_to_owner")
    loaned_beg = dec(owner.get("opening_loan_balance_to_owner_usd"))
    loaned_end = loaned_beg + total("loan_to_owner") - total("loan_repayment_from_owner")
    if borrowed_end < 0 or loaned_end < 0:
        warnings.append("Borç bakiyesi negatif çıktı: yıl başı bakiyelerini ve geri ödemeleri kontrol edin")
    has_borrowed = borrowed_beg != 0 or borrowed_end != 0 or total("loan_from_owner") != 0
    has_loaned = loaned_beg != 0 or loaned_end != 0 or total("loan_to_owner") != 0
    has_loan = has_borrowed or has_loaned

    line22 = borrowed_end                 # 9–21 toplamı; 17'de yalnızca 17b sütuna girer
    line36 = loaned_end + interest_paid   # 23–35 toplamı; 31'de yalnızca 31b sütuna girer
    gross = line22 + line36 + part_v_total  # 1f: Part IV + VI (+ DE ise Part V)

    first_year = bool(company.get("first_year_filing_5472"))
    if not first_year and company.get("date_incorporated", "")[:4] == str(year):
        warnings.append("Kuruluş yılı = vergi yılı ama 'ilk kez 5472 veriliyor' işaretlenmedi")
    pv = case.get("part_vii", {})
    if has_loan and not (pv.get("q42a") and pv.get("q42b")):
        warnings.append("Ortakla borç var: Part VII 42a/42b sorularını cevaplayın")
    if interest_paid:
        warnings.append("Ortağa faiz ödendi: Part VII 40a (section 267A) için bir uzmana danışın")

    def yn(key):
        return {"yes": "Yes", "no": "No"}.get(pv.get(key, ""), "")

    numbers = {
        "total_assets": m(total_assets),
        "gross_payments": m(gross),
        "contributions": m(contributions),
        "owner_paid_expenses": m(owner_paid_exp),
        "distributions": m(draws),
        "part_v_total": m(part_v_total),
        "line17a": m(borrowed_beg), "line17b": m(borrowed_end),
        "line22": m(line22),
        "line31a": m(loaned_beg), "line31b": m(loaned_end),
        "line32": m(interest_paid),
        "line36": m(line36),
        "has_borrowed": has_borrowed, "has_loaned": has_loaned,
        "first_year": first_year,
        "q42a": yn("q42a") if has_loan else "No",
        "q42b": yn("q42b") if has_loan else "No",
    }

    revenue = total("revenue")
    expenses = {CATEGORIES[c][0]: total(c) for c in sorted(EXPENSE_CATEGORIES)}
    expenses[CATEGORIES["interest_paid_to_owner"][0]] = interest_paid
    books = {
        "Yıl başı nakit": m(opening),
        "Yıl sonu nakit (hesaplanan)": m(cash),
        "Gelir": m(revenue),
        **{f"Gider — {k}": m(v) for k, v in expenses.items()},
        "Net kâr (bilgi amaçlı)": m(revenue - sum(expenses.values(), ZERO)),
        "İşlem sayısı": len(txns),
    }

    return {
        "tax_year": year,
        "form_revision": FORM_REVISION,
        "numbers": numbers,
        "rows_1120": rows_1120(case, numbers),
        "rows_5472": rows_5472(case, numbers),
        "part_v_statement": part_v_statement(case, txns, numbers),
        "books": books,
        "warnings": warnings,
    }


# ------------------------------------------------------------ Gösterim satırları

def addr_line(a: dict) -> str:
    keys = ("street", "city", "state", "province", "zip", "country")
    return ", ".join(a[k].strip() for k in keys if a.get(k, "").strip())


def city_line(a: dict) -> str:
    keys = ("city", "state", "province", "zip", "country")
    return ", ".join(a[k].strip() for k in keys if a.get(k, "").strip())


def rows_1120(case: dict, n: dict) -> list[dict]:
    c, y = case["company"], case["tax_year"]
    rows = [
        ("Üst kenar", "Yazılacak ibare", "Foreign-owned U.S. DE"),
        ("Vergi yılı", "Calendar year", str(y)),
        ("İsim", "Corporation name", c["name"]),
        ("Adres", "Number, street, room/suite", c["address"]["street"]),
        ("Adres", "City, state, ZIP", city_line(c["address"])),
        ("B", "Employer identification number", c["ein"]),
        ("C", "Date incorporated", c["date_incorporated"]),
        ("D", "Total assets", f"{n['total_assets']:,}"),
        ("E(1)", "Initial return", "X" if n["first_year"] else ""),
        ("Diğer", "Gelir/gider satırları", "Boş bırakılır"),
    ]
    return [dict(zip(("line", "description", "value"), r)) for r in rows]


def rows_5472(case: dict, n: dict) -> list[dict]:
    c, o, y = case["company"], case["owner"], case["tax_year"]
    ftin = o.get("foreign_tin") or "None"
    owner_addr = f"{o['name']}, {addr_line(o['address'])}"
    money = lambda v: f"{v:,}"
    rows = [
        ("Başlık", "", "Tax year beginning / ending", f"01/01/{y} – 12/31/{y}"),
        ("I", "1a", "Name of reporting corporation", c["name"]),
        ("I", "1a", "Address", f"{c['address']['street']}, {city_line(c['address'])}"),
        ("I", "1b", "Employer identification number", c["ein"]),
        ("I", "1c", "Total assets", money(n["total_assets"])),
        ("I", "1d", "Principal business activity", c["principal_business_activity"]),
        ("I", "1e", "Principal business activity code", c["principal_business_activity_code"]),
        ("I", "1f", "Total value of gross payments (this form)", money(n["gross_payments"])),
        ("I", "1g", "Total number of Forms 5472 filed", "1"),
        ("I", "1h", "Total value of gross payments (all forms)", money(n["gross_payments"])),
        ("I", "1j", "Initial year filing Form 5472", "X" if n["first_year"] else ""),
        ("I", "1k", "Total number of Parts VIII attached", "0"),
        ("I", "1l", "Country of incorporation", "United States"),
        ("I", "1m", "Date of incorporation", c["date_incorporated"]),
        ("I", "1n", "Countries where files tax return as resident", "United States"),
        ("I", "1o", "Principal country(ies) where business is conducted", c["principal_countries_of_business"]),
        ("I", "2", "Foreign person owns at least 50%", "X"),
        ("I", "3", "Foreign-owned U.S. DE", "X"),
        ("II", "4a", "Direct 25% foreign shareholder", owner_addr),
        ("II", "4b(1)", "U.S. identifying number", o.get("us_tin", "")),
        ("II", "4b(2)", "Reference ID number", o.get("reference_id", "")),
        ("II", "4b(3)", "FTIN", ftin),
        ("II", "4c", "Principal country(ies) of business", o["principal_country_of_business"]),
        ("II", "4d", "Country of citizenship", o["country_of_citizenship"]),
        ("II", "4e", "Country(ies) of tax residence", o["country_of_tax_residence"]),
        ("III", "—", "Related party is a", "X foreign person"),
        ("III", "8a", "Related party", owner_addr),
        ("III", "8b(1)", "U.S. identifying number", o.get("us_tin", "")),
        ("III", "8b(2)", "Reference ID number", o.get("reference_id", "")),
        ("III", "8b(3)", "FTIN", ftin),
        ("III", "8c", "Principal business activity", o.get("principal_business_activity", "")),
        ("III", "8d", "Principal business activity code", o.get("principal_business_activity_code", "")),
        ("III", "8e", "Relationship", "X 25% foreign shareholder"),
        ("III", "8f", "Principal country(ies) of business", o["principal_country_of_business"]),
        ("III", "8g", "Country(ies) of tax residence", o["country_of_tax_residence"]),
    ]
    if n["has_borrowed"]:
        rows += [("IV", "17a", "Amounts borrowed — beginning balance", money(n["line17a"])),
                 ("IV", "17b", "Amounts borrowed — ending balance", money(n["line17b"]))]
    rows += [("IV", "22", "Total (lines 9–21)", money(n["line22"]))]
    if n["has_loaned"]:
        rows += [("IV", "31a", "Amounts loaned — beginning balance", money(n["line31a"])),
                 ("IV", "31b", "Amounts loaned — ending balance", money(n["line31b"]))]
    if n["line32"]:
        rows += [("IV", "32", "Interest paid", money(n["line32"]))]
    rows += [
        ("IV", "36", "Total (lines 23–35)", money(n["line36"])),
        ("V", "☐", "Contributions/distributions — attached statement", "X" if n["part_v_total"] else ""),
        ("VII", "37", "Imports goods from foreign related party?", "No"),
        ("VII", "39", "Foreign parent in a cost sharing arrangement?", "No"),
        ("VII", "40a", "Interest/royalty disallowed under sec. 267A?", "No"),
        ("VII", "41a", "Claiming FDII deduction?", "No"),
        ("VII", "42a", "Loan rate inside AFR safe-haven range?", n["q42a"] or "CEVAPLANMADI"),
        ("VII", "42b", "Loan rate outside AFR safe-haven range?", n["q42b"] or "CEVAPLANMADI"),
        ("VII", "43a", "Covered debt instrument (Reg. 1.385-3)?", "No"),
    ]
    return [dict(zip(("part", "line", "description", "value"), r)) for r in rows]


def part_v_statement(case: dict, txns: list[Txn], n: dict) -> list[str]:
    c, o, y = case["company"], case["owner"], case["tax_year"]
    lines = [
        "FORM 5472 - PART V STATEMENT",
        f"{c['name']}   EIN {c['ein']}   Tax year {y}",
        f"Related party: {o['name']} (100% foreign owner)",
        "Reportable transactions under Regulations section 1.482-1(i)(7) not reported in Part IV.",
        "",
        f"{'Capital contributions from owner (cash)':<54}${n['contributions']:>12,}",
        f"{'LLC expenses paid personally by owner (contribution)':<54}${n['owner_paid_expenses']:>12,}",
        f"{'Distributions to owner':<54}${n['distributions']:>12,}",
        "",
        "Detail:",
    ]
    kinds = {"capital_contribution": "Contribution", "owner_draw": "Distribution"}
    for t in sorted(txns, key=lambda t: t.date):
        is_owner_exp = t.category in EXPENSE_CATEGORIES and t.paid_by == "owner"
        if t.category in kinds or is_owner_exp:
            kind = kinds.get(t.category, "Owner-paid expense")
            lines.append(f"  {t.date}  {kind:<20}${t.amount:>11,.2f}  {t.description[:40]}")
    return lines
