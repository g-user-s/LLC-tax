#!/usr/bin/env python3
"""Grafik arayüzü başlatır: yerel bir sunucu açar ve tarayıcıda gösterir.

Kullanım:
    python3 app.py            # rastgele boş port
    python3 app.py --port 8765
"""

from __future__ import annotations

import argparse
import threading
import webbrowser

from llc_tax.server import serve


def main() -> None:
    ap = argparse.ArgumentParser(description="NM LLC — Form 5472 / Pro Forma 1120 hazırlayıcı")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    httpd = serve(args.port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"Uygulama çalışıyor: {url}\nKapatmak için Ctrl+C. Veriler yalnızca bu bilgisayarda (data/, output/).")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatıldı.")


if __name__ == "__main__":
    main()
