"""Yerel grafik arayüz sunucusu (yalnızca 127.0.0.1, dış ağ erişimi yok)."""

from __future__ import annotations

import json
import mimetypes
import re
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import engine, mercury

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
YEAR_RE = re.compile(r"^\d{4}$")


def case_path(year: int) -> Path:
    return DATA / f"case_{year}.json"


def load_case(year: int) -> dict:
    p = case_path(year)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # Önceki yılın şirket/ortak bilgilerini devral
    prev = case_path(year - 1)
    case = engine.empty_case(year)
    if prev.exists():
        old = json.loads(prev.read_text(encoding="utf-8"))
        case["eligibility"] = old.get("eligibility", case["eligibility"])
        case["company"].update(old.get("company", {}))
        case["owner"].update(old.get("owner", {}))
        case["company"]["first_year_filing_5472"] = False
        case["company"]["opening_cash_balance_usd"] = old["company"].get("ending_cash_balance_usd_actual", "")
        case["company"]["ending_cash_balance_usd_actual"] = ""
    return case


def save_case(case: dict) -> None:
    DATA.mkdir(exist_ok=True)
    case_path(int(case["tax_year"])).write_text(json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "LLCTax/1.0"

    def log_message(self, fmt, *args):  # konsolu sessiz tut
        pass

    # --- yardımcılar
    def _host_ok(self) -> bool:
        # DNS rebinding'e karşı yalnızca yerel host adlarını kabul et
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    # --- yönlendirme
    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        if path == "/api/meta":
            return self._json({
                "eligibility": engine.ELIGIBILITY,
                "categories": {k: v[0] for k, v in engine.CATEGORIES.items()},
                "default_year": date.today().year - 1,
                "has_f1120": (ROOT / "forms" / "f1120.pdf").exists(),
            })
        if path.startswith("/api/case/"):
            year = path.rsplit("/", 1)[1]
            if not YEAR_RE.match(year):
                return self._json({"error": "geçersiz yıl"}, 400)
            return self._json(load_case(int(year)))
        if path.startswith("/output/"):
            parts = path.split("/")
            if len(parts) == 4 and YEAR_RE.match(parts[2]) and re.match(r"^[\w.-]+\.pdf$", parts[3]):
                f = OUTPUT / parts[2] / parts[3]
                if f.exists():
                    return self._send(200, f.read_bytes(), "application/pdf")
            return self._send(404, b"not found", "text/plain")
        f = (STATIC / path.lstrip("/")).resolve()
        if f.is_file() and STATIC in f.parents:
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            return self._send(200, f.read_bytes(), ctype)
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        try:
            body = self._body()
        except json.JSONDecodeError:
            return self._json({"error": "geçersiz JSON"}, 400)
        path = self.path.split("?")[0]

        if path == "/api/case":
            save_case(body)
            return self._json({"ok": True})

        if path == "/api/compute":
            errors, txns = engine.validate(body)
            if errors:
                return self._json({"errors": errors})
            return self._json({"errors": [], "result": engine.compute(body, txns)})

        if path == "/api/import/mercury":
            try:
                res = mercury.parse(body.get("csv", ""), body.get("owner_name", ""), int(body["tax_year"]))
            except (ValueError, KeyError) as e:
                return self._json({"error": str(e)}, 400)
            existing = {mercury.dedupe_key(t) for t in body.get("existing", [])}
            new = [t for t in res["transactions"] if mercury.dedupe_key(t) not in existing]
            dup = len(res["transactions"]) - len(new)
            return self._json({"transactions": new, "skipped": res["skipped"], "duplicates": dup})

        if path == "/api/generate":
            errors, txns = engine.validate(body)
            if errors:
                return self._json({"errors": errors})
            result = engine.compute(body, txns)
            save_case(body)
            try:
                from . import pdf_fill
            except ImportError:
                return self._json({"errors": ["pypdf kurulu değil: pip install -r requirements.txt"]})
            out = pdf_fill.generate(body, result, OUTPUT / str(body["tax_year"]))
            return self._json({"errors": [], "year": body["tax_year"], **out})

        self._json({"error": "bulunamadı"}, HTTPStatus.NOT_FOUND)


def serve(port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
