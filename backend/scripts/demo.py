"""End-to-end demo: serve a fixture listing on localhost, call /analyze.

Usage:
    uv run python scripts/demo.py

Requires the FastAPI server to be running at http://127.0.0.1:8000.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

FIXTURE_HTML = b"""<!doctype html><html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "RealEstateListing",
  "name": "Bel appartement 3p 65m\u00b2 - Paris 11e",
  "description": "Appartement traversant, 4e \u00e9tage avec ascenseur. Cuisine ouverte, parquet, double exposition. DPE D.",
  "image": "https://picsum.photos/600/400",
  "offers": {"@type": "Offer", "price": "850000", "priceCurrency": "EUR"},
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "5 rue du Faubourg du Temple",
    "postalCode": "75011",
    "addressLocality": "Paris"
  },
  "floorSize": {"value": 65},
  "numberOfRooms": 3,
  "numberOfBedrooms": 2
}
</script></head><body><h1>Annonce de d\xc3\xa9mo</h1></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(FIXTURE_HTML)))
        self.end_headers()
        self.wfile.write(FIXTURE_HTML)

    def log_message(self, *_):
        pass


def main() -> int:
    server = HTTPServer(("127.0.0.1", 9999), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        url = "http://127.0.0.1:9999/listing"
        r = httpx.post(
            "http://127.0.0.1:8000/analyze",
            json={"url": url},
            timeout=60.0,
        )
        print(f"HTTP {r.status_code}")
        body = r.json()
        # Trim photos & description for readable output
        if "listing" in body:
            body["listing"]["description"] = (
                (body["listing"].get("description") or "")[:120] + "…"
            )
            body["listing"]["photos"] = body["listing"].get("photos", [])[:1]
        print(json.dumps(body, indent=2, ensure_ascii=False, default=str)[:6000])
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
