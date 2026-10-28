"""Resmi IRS PDF'lerini doldurur (yerel, pypdf ile).

Alan adları forms/ altındaki PDF'lerden çıkarılıp görsel olarak doğrulanmıştır.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

FORMS_DIR = Path(__file__).resolve().parent.parent / "forms"
F5472 = FORMS_DIR / "f5472.pdf"
F1120 = FORMS_DIR / "f1120.pdf"

# Form 5472 (Rev. 12-2023) Part VII Evet/Hayır kutuları: (alan, "Yes" değeri, "No" değeri)
F5472_YES_NO = {
    "37": ("c3_1", "/1", "/2"),
    "39": ("c3_4", "/1", "/2"),
    "40a": ("c3_5", "/1", "/2"),
    "41a": ("c3_6", "/1", "/2"),
    "42a": ("c3_7", "/1", "/2"),
    "42b": ("c3_8", "/1", "/2"),
    "43a": ("c3_9", "/1", "/2"),
}


def ascii_text(s: str) -> str:
    """IRS formları İngilizce/ASCII ister; Türkçe karakterleri sadeleştirir."""
    s = str(s).replace("ı", "i").replace("İ", "I")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def money(v: int, blank_zero: bool = False) -> str:
    return "" if (blank_zero and not v) else f"{v:,}"


def values_5472(case: dict, n: dict) -> tuple[dict, dict]:
    """(metin alanları, buton alanları) — buton değeri işaretli durum adıdır."""
    c, o, y = case["company"], case["owner"], case["tax_year"]
    ca, oa = c["address"], o["address"]
    city = ", ".join(x for x in (ca.get("city"), ca.get("state")) if x) + f" {ca.get('zip', '')}"
    owner_addr = ", ".join(x for x in (o["name"], oa.get("street"), oa.get("city"), oa.get("province"),
                                       oa.get("zip"), oa.get("country")) if x)
    ftin = o.get("foreign_tin") or "None"
    inc = c["date_incorporated"]
    inc_us = f"{inc[5:7]}/{inc[8:10]}/{inc[:4]}"

    text = {
        "f1_1": "01/01", "f1_2": str(y), "f1_3": "12/31", "f1_4": str(y),
        # Part I
        "f1_5": c["name"], "f1_6": ca["street"], "f1_7": city.strip(),
        "f1_8": c["ein"], "f1_9": money(n["total_assets"]),
        "f1_10": c["principal_business_activity"], "f1_11": c["principal_business_activity_code"],
        "f1_12": money(n["gross_payments"]), "f1_13": "1", "f1_14": money(n["gross_payments"]),
        "f1_15": "0", "f1_16": "United States", "f1_17": inc_us,
        "f1_18": "United States", "f1_19": c["principal_countries_of_business"],
        # Part II (4a–4e)
        "f1_20": owner_addr, "f1_21": o.get("us_tin", ""), "f1_22": o.get("reference_id", ""),
        "f1_23": ftin, "f1_24": o["principal_country_of_business"],
        "f1_25": o["country_of_citizenship"], "f1_26": o["country_of_tax_residence"],
        # Part III (8a–8g)
        "f2_1": owner_addr, "f2_2": o.get("us_tin", ""), "f2_3": o.get("reference_id", ""),
        "f2_4": ftin, "f2_5": o.get("principal_business_activity", ""),
        "f2_6": o.get("principal_business_activity_code", ""),
        "f2_7": o["principal_country_of_business"], "f2_8": o["country_of_tax_residence"],
        # Part IV
        "f2_24": money(n["line22"]),   # 22
        "f2_40": money(n["line36"]),   # 36
    }
    if n["has_borrowed"]:
        text["f2_18"] = money(n["line17a"])  # 17a
        text["f2_19"] = money(n["line17b"])  # 17b
    if n["has_loaned"]:
        text["f2_34"] = money(n["line31a"])  # 31a
        text["f2_35"] = money(n["line31b"])  # 31b
    if n["line32"]:
        text["f2_36"] = money(n["line32"])   # 32

    buttons = {
        "c1_3": "/1",      # 2: yabancı kişi >= %50
        "c1_4": "/1",      # 3: foreign-owned U.S. DE
        "c2_1[0]": "/1",   # Part III: foreign person
        "c2_4": "/1",      # 8e: 25% foreign shareholder
    }
    if n["first_year"]:
        buttons["c1_2"] = "/1"  # 1j
    if n["part_v_total"]:
        buttons["c2_6"] = "/1"  # Part V
    answers = {"37": "No", "39": "No", "40a": "No", "41a": "No", "43a": "No",
               "42a": n["q42a"] or "", "42b": n["q42b"] or ""}
    for line, ans in answers.items():
        field, yes, no = F5472_YES_NO[line]
        if ans in ("Yes", "No"):
            buttons[f"{field}[{0 if ans == 'Yes' else 1}]"] = yes if ans == "Yes" else no
    return {k: ascii_text(v) for k, v in text.items()}, buttons


def _fill(template: Path, text: dict, buttons: dict, out: Path) -> None:
    writer = PdfWriter()
    writer.append(PdfReader(template))
    for page in writer.pages:
        names = set()
        for annot in page.get("/Annots", []) or []:
            a = annot.get_object()
            t = str(a.get("/T", ""))
            names.add(t)
            short = t.split("[")[0]
            key = t if t in buttons else short if short in buttons else None
            if key is not None and a.get("/FT") == "/Btn":
                on = NameObject(buttons[key])
                a[NameObject("/V")] = on
                a[NameObject("/AS")] = on
        page_text = {}
        for k, v in text.items():
            for t in names:
                if t.split("[")[0] == k:
                    page_text[t] = v
        if page_text:
            writer.update_page_form_field_values(page, page_text, auto_regenerate=False)
    writer.set_need_appearances_writer(True)
    with out.open("wb") as f:
        writer.write(f)


def text_pdf(lines: list[str], out: Path, title: str = "") -> None:
    """Bağımlılıksız, tek sayfalık düz metin PDF (Courier 10pt)."""
    def esc(s: str) -> str:
        return ascii_text(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    pages, per_page = [], 60
    for i in range(0, max(len(lines), 1), per_page):
        chunk = lines[i:i + per_page]
        ops = ["BT", "/F1 10 Tf", "12 TL", "50 750 Td"]
        for ln in chunk:
            ops.append(f"({esc(ln)}) '")
        ops.append("ET")
        pages.append("\n".join(ops).encode())

    objs = []
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    for i, content in enumerate(pages):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")

    buf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(buf)
    buf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    out.write_bytes(bytes(buf))


def generate(case: dict, result: dict, out_dir: Path) -> dict:
    """Formları üretir; {"files": [...], "missing": [...]} döner."""
    out_dir.mkdir(parents=True, exist_ok=True)
    y, n = case["tax_year"], result["numbers"]
    files, missing = [], []

    p1120 = out_dir / f"{y}_1_pro_forma_1120.pdf"
    if F1120.exists():
        from .f1120_map import values_1120
        text, buttons = values_1120(case, n)
        _fill(F1120, text, buttons, p1120)
        files.append(p1120)
    else:
        missing.append("forms/f1120.pdf (vergi yılına ait Form 1120)")

    p5472 = out_dir / f"{y}_2_form_5472.pdf"
    text, buttons = values_5472(case, n)
    _fill(F5472, text, buttons, p5472)
    files.append(p5472)

    if n["part_v_total"]:
        pv = out_dir / f"{y}_3_part_v_statement.pdf"
        text_pdf(result["part_v_statement"], pv)
        files.append(pv)

    if not missing:
        packet = out_dir / f"{y}_FAX_PAKETI.pdf"
        w = PdfWriter()
        for f in files:
            w.append(PdfReader(f))
        with packet.open("wb") as fh:
            w.write(fh)
        files.insert(0, packet)
    return {"files": [f.name for f in files], "missing": missing}
