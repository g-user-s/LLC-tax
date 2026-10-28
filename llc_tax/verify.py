"""Kurulum ve form güncelliği kontrolü.

    python3 -m llc_tax.verify --year 2025            # yerel kontroller
    python3 -m llc_tax.verify --year 2025 --online   # + irs.gov'daki güncel PDF'lerle karşılaştır

--online yalnızca irs.gov'dan herkese açık PDF'leri indirir; kullanıcı verisi gönderilmez.
Çıkış kodu: 0 = her şey tamam, 1 = en az bir kontrol başarısız.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import re
import sys
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"

# Alan eşleştirmesinin görsel olarak doğrulandığı PDF'lerin alan düzeni parmak izleri.
# Bir PDF değişip parmak izi tutmazsa pdf_fill.py'deki eşleştirme yeniden doğrulanmalıdır.
EXPECTED = {
    "f5472.pdf": {
        "revision": "Rev. December 2023",
        "layout_sha256": "89455e8e129fdaef0464dc357dc1e13e71dd692781941ce857b5b9bfa4b939c9",
        "widgets": 143,
        "pages": None,
        "url": "https://www.irs.gov/pub/irs-pdf/f5472.pdf",
    },
    "f1120.pdf": {
        "revision": "calendar year 2025",
        "layout_sha256": "f772b8a6779dae829b63a625865933951a9a6e042ae67ae3329f7125f231a3c5",
        "widgets": 79,
        "pages": {0},
        "url": "https://www.irs.gov/pub/irs-pdf/f1120.pdf",
    },
}
INSTRUCTIONS_URL = "https://www.irs.gov/pub/irs-pdf/i5472.pdf"
INSTRUCTIONS_REVISION = "Rev. December 2024"


def layout_fingerprint(data: bytes, pages: set[int] | None = None) -> tuple[str, int]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    items = []
    for pi, page in enumerate(reader.pages):
        if pages and pi not in pages:
            continue
        for a in page.get("/Annots", []) or []:
            a = a.get_object()
            if a.get("/Subtype") != "/Widget":
                continue
            rect = ",".join(str(round(float(x))) for x in a["/Rect"])
            items.append(f"{pi}|{a.get('/T')}|{rect}")
    return hashlib.sha256("\n".join(sorted(items)).encode()).hexdigest(), len(items)


def first_page_text(data: bytes) -> str:
    from pypdf import PdfReader
    return PdfReader(io.BytesIO(data)).pages[0].extract_text() or ""


def check_pdf(name: str, data: bytes, label: str) -> list[str]:
    exp = EXPECTED[name]
    problems = []
    text = first_page_text(data)
    if exp["revision"] not in text:
        found = re.search(r"Rev\. \w+ \d{4}|calendar year \d{4}", text)
        problems.append(f"{label} {name}: beklenen '{exp['revision']}', bulunan "
                        f"'{found.group(0) if found else '?'}'")
    sha, n = layout_fingerprint(data, exp["pages"])
    if sha != exp["layout_sha256"]:
        problems.append(f"{label} {name}: alan düzeni değişmiş ({n} alan) — "
                        "pdf_fill.py eşleştirmesi yeniden doğrulanmalı")
    return problems


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "llc-tax-verify"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> int:
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True, help="Beyan edilecek vergi yılı")
    ap.add_argument("--online", action="store_true", help="irs.gov'daki güncel PDF'lerle karşılaştır")
    args = ap.parse_args()

    results: list[tuple[str, bool, str]] = []

    def record(name, ok, detail=""):
        results.append((name, ok, detail))

    record("Python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0])
    try:
        import pypdf
        record("pypdf kurulu", True, pypdf.__version__)
    except ImportError:
        record("pypdf kurulu", False, "pip install -r requirements.txt")
        return report(results)

    for name in EXPECTED:
        p = FORMS / name
        if not p.exists():
            record(f"forms/{name} mevcut", False, "dosya yok")
            continue
        probs = check_pdf(name, p.read_bytes(), "yerel")
        record(f"forms/{name} bilinen sürüm ve alan düzeni", not probs, "; ".join(probs))

    from .pdf_fill import F1120, form_year
    if F1120.exists():
        fy = form_year(F1120)
        record(f"forms/f1120.pdf yılı = {args.year}", fy == args.year, f"PDF yılı: {fy}")

    # Birim testleri
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    buf = io.StringIO()
    res = unittest.TextTestRunner(stream=buf, verbosity=1).run(suite)
    record(f"Birim testleri ({res.testsRun})", res.wasSuccessful(),
           "" if res.wasSuccessful() else buf.getvalue()[-3000:])

    if args.online:
        for name, exp in EXPECTED.items():
            try:
                data = fetch(exp["url"])
            except OSError as e:
                record(f"irs.gov {name} indirildi", False, str(e))
                continue
            probs = check_pdf(name, data, "irs.gov")
            local = (FORMS / name).read_bytes() if (FORMS / name).exists() else b""
            same = hashlib.sha256(data).hexdigest() == hashlib.sha256(local).hexdigest()
            record(f"irs.gov {name} = yerel sürüm", not probs,
                   "; ".join(probs) or ("bayt bayt aynı" if same else "içerik farklı ama sürüm ve alan düzeni aynı"))
        try:
            text = first_page_text(fetch(INSTRUCTIONS_URL))
            record(f"irs.gov i5472 talimatı {INSTRUCTIONS_REVISION}", INSTRUCTIONS_REVISION in text,
                   "" if INSTRUCTIONS_REVISION in text else "talimat güncellenmiş: README'deki kural kontrolünü yapın")
        except OSError as e:
            record("irs.gov i5472 indirildi", False, str(e))

    return report(results)


def report(results) -> int:
    width = max(len(r[0]) for r in results)
    for name, ok, detail in results:
        print(f"[{'OK ' if ok else 'HATA'}] {name:<{width}}  {detail.splitlines()[0] if detail else ''}")
        if not ok and detail and "\n" in detail:
            print(detail)
    failed = [r for r in results if not r[1]]
    print(f"\nSONUÇ: {'TAMAM' if not failed else f'{len(failed)} kontrol başarısız'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
