"""Listing parser tests using synthetic JSON-LD fixtures.

Real listings can't be hit in CI (anti-bot, ToS); we test the parser
logic with representative HTML that mirrors what each portal emits.
"""
from __future__ import annotations

from app.services.listing_parser import detect_portal, parse_html

BIENICI_HTML = """
<!doctype html>
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "RealEstateListing",
  "name": "Appartement 3 pièces 65m² rue de Rivoli, Paris 1er",
  "description": "Bel appartement traversant, étage élevé, ascenseur. DPE: D",
  "image": ["https://img.example/1.jpg", "https://img.example/2.jpg"],
  "offers": {
    "@type": "Offer",
    "price": "895000",
    "priceCurrency": "EUR"
  },
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "12 rue de Rivoli",
    "postalCode": "75001",
    "addressLocality": "Paris"
  },
  "floorSize": {"@type": "QuantitativeValue", "value": 65, "unitCode": "MTK"},
  "numberOfRooms": 3,
  "numberOfBedrooms": 2
}
</script>
</head><body></body></html>
"""

SELOGER_HTML = """
<!doctype html><html><head>
<script type="application/ld+json">
[
  {"@type": "BreadcrumbList", "itemListElement": []},
  {
    "@type": "Product",
    "name": "Studio 22m² Paris 11e",
    "description": "Charmant studio, 4ème étage avec ascenseur. DPE F.",
    "offers": {"price": 295000, "priceCurrency": "EUR"},
    "image": "https://img.example/x.jpg"
  }
]
</script>
</head><body></body></html>
"""


def test_detect_portal():
    assert detect_portal("https://www.bienici.com/annonce/123") == "Bien'ici"
    assert detect_portal("https://www.seloger.com/annonces/456.htm") == "SeLoger"
    assert detect_portal("https://www.leboncoin.fr/ad/12345") == "LeBonCoin"
    assert detect_portal("https://www.pap.fr/x") == "PAP"


def test_parse_bienici():
    listing = parse_html(BIENICI_HTML, "https://www.bienici.com/annonce/x")
    assert listing.portal == "Bien'ici"
    assert listing.price_eur == 895000.0
    assert listing.surface_m2 == 65.0
    assert listing.rooms == 3
    assert listing.bedrooms == 2
    assert listing.postal_code == "75001"
    assert listing.city == "Paris"
    assert "rue de Rivoli" in (listing.address_raw or "")
    assert listing.dpe_class == "D"
    assert len(listing.photos) == 2


def test_parse_seloger():
    listing = parse_html(SELOGER_HTML, "https://www.seloger.com/annonces/1.htm")
    assert listing.portal == "SeLoger"
    assert listing.price_eur == 295000.0
    assert listing.dpe_class == "F"
