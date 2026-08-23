from olha_casa.extract import parse_listing, source_id_from_url


HTML = """
<html><head>
<script type="application/ld+json">
{
  "@type": "Apartment",
  "name": "Apartamento T1 na Maia",
  "description": "Zona muito tranquila e muito luminosa, com fibra. Cozinha totalmente equipada, lugar de garagem. Condições: 2 rendas + 1 caução. Contrato mínimo 1 ano. Exige-se fiador, IRS, contrato de trabalho e 3 recibos de vencimento. Animais permitidos.",
  "offers": {"price": "680"},
  "floorSize": {"value": "52"},
  "address": {"addressLocality": "Maia", "addressRegion": "Porto"},
  "geo": {"latitude": 41.232, "longitude": -8.621}
}
</script></head>
<body>3.º andar com elevador. Publicado há 2 horas.</body></html>
"""


def test_extracts_listing_and_terms():
    listing = parse_listing("idealista", "https://www.idealista.pt/imovel/12345678/", HTML)
    assert listing.price == 680
    assert listing.area_m2 == 52
    assert listing.typology == "T1"
    assert listing.location == "Maia, Porto"
    assert listing.floor == 3
    assert listing.elevator is True
    assert listing.parking is True
    assert listing.fiber is True
    assert listing.quiet is True
    assert listing.natural_light is True
    assert listing.terms.deposits == 1
    assert listing.terms.advance_rents == 2
    assert listing.terms.entry_total == 2040
    assert listing.terms.minimum_contract_months == 12
    assert listing.terms.guarantor is True
    assert listing.terms.payslips is True
    assert listing.terms.tax_return is True
    assert listing.terms.work_contract is True
    assert listing.terms.equipped_kitchen is True
    assert listing.terms.pets_allowed is True
    assert listing.price_per_m2 == 13.08


def test_preserves_negative_longitude():
    listing = parse_listing("idealista", "https://www.idealista.pt/imovel/12345678/", HTML)
    assert listing.latitude == 41.232
    assert listing.longitude == -8.621


def test_portuguese_thousands_separator_is_not_decimal():
    html = "<html><head><title>T1 Porto</title></head><body>1.800 € · 60 m²</body></html>"
    listing = parse_listing("supercasa", "https://supercasa.pt/arrendamento-apartamento-t1-porto/i2230444", html)
    assert listing.price == 1800
    assert listing.area_m2 == 60
    assert source_id_from_url("supercasa", listing.url) == "2230444"


def test_fixed_deposit_amount_contributes_to_entry_total():
    html = """
    <html><head><title>T1 Porto 700 €</title></head>
    <body>Área 50 m². Entrada: 2 rendas + caução 1.500 €. Cozinha equipada.</body></html>
    """
    listing = parse_listing("casa_sapo", "https://casa.sapo.pt/alugar-apartamento-t1-porto-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.html", html)
    assert listing.terms.deposits == 1
    assert listing.terms.deposit_amount == 1500
    assert listing.terms.advance_rents == 2
    assert listing.terms.entry_total == 2900


def test_studio_is_normalized_as_t0():
    html = "<html><head><title>Estúdio para arrendar no Porto</title></head><body>650 €</body></html>"
    listing = parse_listing("idealista", "https://www.idealista.pt/imovel/123456/", html)
    assert listing.typology == "T0"


def test_extracts_t2_or_higher():
    html = "<html><head><title>Moradia T3 para arrendar na Maia</title></head><body>750 €</body></html>"
    listing = parse_listing("idealista", "https://www.idealista.pt/imovel/654321/", html)
    assert listing.typology == "T3"


def test_extracts_olx_id_and_location_from_offer():
    html = """
    <html><head><script type="application/ld+json">
    {
      "@type": "Product",
      "name": "Apartamento T0 para arrendamento",
      "offers": {
        "price": "700",
        "areaServed": {"@type": "City", "name": "Paços de Ferreira"}
      }
    }
    </script></head></html>
    """
    url = "https://www.olx.pt/d/anuncio/apartamento-t0-IDJxLFQ.html"
    listing = parse_listing("olx", url, html)
    assert listing.source_id == "JxLFQ"
    assert listing.location == "Paços de Ferreira"


def test_extracts_custojusto_id_and_offer_location():
    html = """
    <html><head><script type="application/ld+json">
    {
      "@type": "Product",
      "name": "Estúdio para arrendar",
      "offers": {
        "price": "750",
        "availableAtOrFrom": {"@type": "Place", "name": "Porto"}
      }
    }
    </script></head></html>
    """
    url = "https://www.custojusto.pt/porto/imobiliario/apartamentos/estudio-45203601"
    listing = parse_listing("custojusto", url, html)
    assert listing.source_id == "45203601"
    assert listing.location == "Porto"

