"""Mercury banka CSV dışa aktarımını işlem listesine çevirir.

Sütun adları esnek eşleştirilir; kategoriler tahmin edilir ve kullanıcı arayüzde onaylar.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_COLS = ["date (utc)", "date", "posted date", "transaction date", "posted at"]
AMOUNT_COLS = ["amount", "amount (usd)", "amount usd"]
CREDIT_COLS = ["credit", "credit amount", "deposit", "deposits", "money in", "inflow"]
DEBIT_COLS = ["debit", "debit amount", "withdrawal", "withdrawals", "money out", "outflow"]
DESC_COLS = ["description", "counterparty", "name", "counterparty name"]
BANK_DESC_COLS = ["bank description", "memo"]
STATUS_COLS = ["status"]
CATEGORY_COLS = ["mercury category", "category"]
SKIP_STATUS = {"failed", "cancelled", "canceled", "pending", "blocked", "reversed"}

REVENUE_RE = re.compile(r"apple|itunes|app store|google|play console", re.I)
SOFTWARE_RE = re.compile(r"apple|google|github|adobe|figma|notion|openai|anthropic|aws|amazon web|"
                         r"heroku|vercel|netlify|cloudflare|digitalocean|firebase|jetbrains|"
                         r"atlassian|slack|zoom|dropbox|software|subscription", re.I)
FEE_RE = re.compile(r"\bfee\b|wire fee|service charge", re.I)
TRANSFER_RE = re.compile(r"transfer between|internal transfer|mercury (checking|savings|treasury)", re.I)


def _pick(header: list[str], candidates: list[str]) -> str | None:
    low = {h.strip().lower(): h for h in header}
    for c in candidates:
        if c in low:
            return low[c]
    return None


def _parse_date(s: str) -> str | None:
    s = s.strip()[:19]
    for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%m-%d-%y", "%m/%d/%y"):
        try:
            return datetime.strptime(s if "%H" in fmt else s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _num(v) -> Decimal:
    s = str(v or "").replace(",", "").replace("$", "").replace("USD", "").strip()
    if s.startswith("(") and s.endswith(")"):  # muhasebe biçimi: (12.34) = -12.34
        s = "-" + s[1:-1]
    return Decimal(s) if s else Decimal("0")


def _owner_tokens(owner_name: str) -> list[str]:
    return [t for t in re.split(r"\W+", owner_name.lower()) if len(t) >= 3]


def _is_owner(text: str, tokens: list[str]) -> bool:
    low = text.lower()
    return bool(tokens) and sum(t in low for t in tokens) >= min(2, len(tokens))


def guess(desc: str, bank_desc: str, merc_cat: str, amount: Decimal, owner_tokens: list[str]) -> tuple[str, str]:
    """(category, paid_by) tahmini; emin olunamazsa category boş döner."""
    text = f"{desc} {bank_desc}"
    if TRANSFER_RE.search(text):
        return "internal_transfer", "llc"
    if amount > 0:
        if _is_owner(text, owner_tokens):
            return "capital_contribution", "owner"
        if REVENUE_RE.search(text):
            return "revenue", "llc"
        return "", "llc"
    if _is_owner(text, owner_tokens):
        return "owner_draw", "llc"
    if FEE_RE.search(text) or "fee" in merc_cat.lower():
        return "bank_fee", "llc"
    if SOFTWARE_RE.search(text) or "software" in merc_cat.lower():
        return "software_expense", "llc"
    return "other_expense", "llc"


def parse(csv_text: str, owner_name: str, tax_year: int) -> dict:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    header = reader.fieldnames or []
    dcol, acol = _pick(header, DATE_COLS), _pick(header, AMOUNT_COLS)
    ccol, dbcol = _pick(header, CREDIT_COLS), _pick(header, DEBIT_COLS)
    if not dcol or not (acol or (ccol and dbcol)):
        raise ValueError("CSV'de tarih ve tutar (veya giriş/çıkış) sütunları bulunamadı. "
                         f"Bulunan sütunlar: {', '.join(header)}")
    desc_col, bank_col = _pick(header, DESC_COLS), _pick(header, BANK_DESC_COLS)
    status_col, cat_col = _pick(header, STATUS_COLS), _pick(header, CATEGORY_COLS)
    tokens = _owner_tokens(owner_name)

    out, skipped = [], []
    for i, row in enumerate(reader, start=2):
        status = (row.get(status_col) or "").strip().lower() if status_col else ""
        if status in SKIP_STATUS:
            skipped.append(f"satır {i}: durum '{status}'")
            continue
        d = _parse_date(row.get(dcol) or "")
        if not d:
            skipped.append(f"satır {i}: tarih okunamadı '{row.get(dcol)}'")
            continue
        if int(d[:4]) != tax_year:
            skipped.append(f"satır {i}: {d} vergi yılı dışında")
            continue
        try:
            if acol:
                amt = _num(row.get(acol))
            else:  # ayrı giriş/çıkış sütunları
                amt = _num(row.get(ccol)) - abs(_num(row.get(dbcol)))
        except InvalidOperation:
            skipped.append(f"satır {i}: tutar okunamadı")
            continue
        if amt == 0:
            continue
        desc = (row.get(desc_col) or "").strip() if desc_col else ""
        bank_desc = (row.get(bank_col) or "").strip() if bank_col else ""
        merc_cat = (row.get(cat_col) or "").strip() if cat_col else ""
        cat, paid_by = guess(desc, bank_desc, merc_cat, amt, tokens)
        out.append({
            "date": d,
            "description": desc or bank_desc,
            "category": cat,
            "amount_usd": f"{abs(amt):.2f}",
            "counterparty": desc,
            "paid_by": paid_by,
            "notes": bank_desc if desc else "",
            "source": "mercury",
            "direction": "in" if amt > 0 else "out",
            "needs_review": cat in ("", "other_expense"),
        })
    return {"transactions": out, "skipped": skipped}


def dedupe_key(t: dict) -> tuple:
    return (t.get("date"), f"{Decimal(str(t.get('amount_usd') or 0)):.2f}",
            (t.get("description") or "").strip().lower())
