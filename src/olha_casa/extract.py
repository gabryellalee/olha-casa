from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .models import Listing, RentalTerms


SPACE_RE = re.compile(r"\s+")
NUMBER_WORDS = {
    "uma": 1,
    "um": 1,
    "duas": 2,
    "dois": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
}


def normalize_text(value: str | None) -> str:
    value = SPACE_RE.sub(" ", value or "").strip().lower()
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = SPACE_RE.sub(" ", soup.get_text(" ", strip=True)).strip()
    for marker in [
        "Mais imóveis que lhe podem interessar",
        "Sugestões de pesquisa",
        "Imóveis semelhantes",
    ]:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text


def _first_meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return SPACE_RE.sub(" ", tag["content"]).strip()
    return None


def _walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _json_ld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(tag.string or tag.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        objects.extend(_walk_json(payload))
    return objects


def _listing_json(soup: BeautifulSoup) -> dict[str, Any]:
    candidates = _json_ld_objects(soup)
    preferred = {
        "apartment",
        "accommodation",
        "house",
        "residence",
        "product",
        "realestatelisting",
        "offer",
    }
    for item in candidates:
        kind = item.get("@type", "")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(normalize_text(str(entry)) in preferred for entry in kinds):
            return item
    return candidates[0] if candidates else {}


def _as_float(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("value") or value.get("price")
    if value is None:
        return None
    match = re.search(r"[-+]?\d[\d,.]*", str(value).replace("−", "-"))
    if not match:
        return None
    cleaned = match.group(0)
    sign = -1 if cleaned.startswith("-") else 1
    cleaned = cleaned.lstrip("+-")
    # Em preços portugueses, "1.800" é normalmente um separador de milhares.
    # Valores com dois algarismos antes do ponto (por exemplo 41.232 numa
    # latitude) são decimais e não podem perder o separador.
    if sign > 0 and re.fullmatch(r"\d[.,]\d{3}", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", "")
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return sign * float(cleaned)
    except ValueError:
        return None


def _regex_float(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return _as_float(match.group(1))
    return None


def _number_near(label: str, text: str) -> int | None:
    normalized = normalize_text(text)
    patterns = [
        rf"(\d+)\s+(?:mes(?:es)?\s+(?:de\s+)?)?{label}",
        rf"{label}\D{{0,22}}(\d+)",
        rf"({'|'.join(NUMBER_WORDS)})\s+(?:mes(?:es)?\s+(?:de\s+)?)?{label}",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        raw = match.group(1)
        value = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw)
        return value if value is not None and value <= 6 else None
    return None


def _bool_signal(text: str, positives: list[str], negatives: list[str]) -> bool | None:
    normalized = normalize_text(text)
    if any(re.search(pattern, normalized) for pattern in negatives):
        return False
    if any(re.search(pattern, normalized) for pattern in positives):
        return True
    return None


def _extract_terms(text: str, price: float | None) -> RentalTerms:
    normalized = normalize_text(text)
    deposits = _number_near(r"cauc(?:ao|oes)", text)
    advance = _number_near(r"rendas?\s+adiantad[ao]s?", text)
    deposit_amount = _regex_float(
        [r"cauc(?:ao|oes)\D{0,12}(\d{1,5}(?:[.,]\d{1,3})?)\s*€"], normalized
    )
    if deposits is None and re.search(r"\bcauc(?:ao|oes)\b", normalized):
        deposits = 1

    # Formula comum: "2 rendas + 1 caução".
    if advance is None:
        match = re.search(r"(\d+)\s+rendas?\s*(?:\+|e)\s*\d+\s+cauc", normalized)
        if match:
            advance = int(match.group(1))
        else:
            match = re.search(r"(\d+)\s+rendas?\s*(?:\+|e)\s*cauc", normalized)
            if match:
                advance = int(match.group(1))
    if advance is None:
        match = re.search(r"(?:pagamento|entrada)\D{0,20}(\d+)\s+(?:mes(?:es)?\s+de\s+)?renda", normalized)
        if match and int(match.group(1)) <= 6:
            advance = int(match.group(1))
    if deposits is None:
        match = re.search(r"\d+\s+rendas?\s*(?:\+|e)\s*(\d+)\s+cauc", normalized)
        if match:
            deposits = int(match.group(1))

    entry_total = None
    if price is not None and (deposits is not None or advance is not None):
        deposit_total = deposit_amount if deposit_amount is not None else price * (deposits or 0)
        entry_total = deposit_total + price * (advance or 0)

    included: list[str] = []
    for label, patterns in {
        "água": [r"agua\s+incluid", r"inclui\s+agua"],
        "eletricidade": [r"(?:luz|eletricidade)\s+incluid", r"inclui\s+(?:luz|eletricidade)"],
        "internet": [r"internet\s+incluid", r"inclui\s+internet"],
        "gás": [r"gas\s+incluid", r"inclui\s+gas"],
        "condomínio": [r"condominio\s+incluid", r"inclui\s+condominio"],
    }.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            included.append(label)

    minimum_months = None
    match = re.search(
        r"(?:contrato|arrendamento|periodo)\D{0,25}(?:minim[oa]\D{0,8})?(\d+)\s*(mes(?:es)?|ano(?:s)?)",
        normalized,
    ) or re.search(r"minim[oa]\D{0,8}(\d+)\s*(mes(?:es)?|ano(?:s)?)", normalized)
    if match:
        minimum_months = int(match.group(1)) * (12 if "ano" in match.group(2) else 1)

    docs: list[str] = []
    if "nota de liquidacao" in normalized:
        docs.append("nota de liquidação")
    if "mapa de responsabilidades" in normalized:
        docs.append("mapa de responsabilidades do Banco de Portugal")

    return RentalTerms(
        deposits=deposits,
        deposit_amount=deposit_amount,
        advance_rents=advance,
        entry_total=entry_total,
        guarantor=_bool_signal(
            text,
            [r"\bfiador\b", r"exige-se fiador"],
            [r"sem fiador", r"nao (?:e )?necessario fiador"],
        ),
        payslips=_bool_signal(
            text,
            [r"recibos? de vencimento", r"comprovativ[oa]s? de rendimento"],
            [],
        ),
        tax_return=_bool_signal(text, [r"\birs\b", r"declaracao de rendimentos"], []),
        work_contract=_bool_signal(text, [r"contrato de trabalho"], []),
        other_documents=docs,
        included_expenses=included,
        minimum_contract_months=minimum_months,
        equipped_kitchen=_bool_signal(
            text,
            [r"cozinha (?:totalmente )?equipada", r"eletrodomesticos incluidos"],
            [r"cozinha nao equipada", r"sem eletrodomesticos"],
        ),
        pets_allowed=_bool_signal(
            text,
            [r"aceita (?:animais|pets)", r"animais permitidos", r"pet friendly"],
            [r"nao (?:sao )?permitidos animais", r"nao aceita animais", r"sem animais"],
        ),
    )


def _extract_coordinates(item: dict[str, Any], html: str) -> tuple[float | None, float | None]:
    geo = item.get("geo") if isinstance(item.get("geo"), dict) else {}
    lat = _as_float(geo.get("latitude"))
    lon = _as_float(geo.get("longitude"))
    if lat is not None and lon is not None:
        return lat, lon

    lat = _regex_float(
        [
            r'"latitude"\s*:\s*"?(-?\d{1,3}(?:\.\d+)?)',
            r'"lat"\s*:\s*"?(-?\d{1,3}(?:\.\d+)?)',
        ],
        html,
    )
    lon = _regex_float(
        [
            r'"longitude"\s*:\s*"?(-?\d{1,3}(?:\.\d+)?)',
            r'"lng"\s*:\s*"?(-?\d{1,3}(?:\.\d+)?)',
            r'"lon"\s*:\s*"?(-?\d{1,3}(?:\.\d+)?)',
        ],
        html,
    )
    if lat is not None and lon is not None and 40.5 <= lat <= 42.5 and -9.5 <= lon <= -7.5:
        return lat, lon
    return None, None


def _extract_floor(text: str) -> int | None:
    normalized = normalize_text(text)
    if re.search(r"\b(?:res do chao|r/c|rc)\b", normalized):
        return 0
    if re.search(r"\b(?:cave|subsolo)\b", normalized):
        return -1
    match = re.search(r"(?:andar|piso)\s*(-?\d+)|(-?\d+)\s*[.ºoª]{1,2}\s*(?:andar|piso)?", normalized)
    if match:
        return int(match.group(1) or match.group(2))
    return None


def _extract_published(text: str, html: str) -> str | None:
    now = datetime.now(UTC)
    normalized = normalize_text(text)
    match = re.search(r"ha\s+(\d+)\s+(minuto|hora|dia)s?", normalized)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {
            "minuto": timedelta(minutes=amount),
            "hora": timedelta(hours=amount),
            "dia": timedelta(days=amount),
        }[unit]
        return (now - delta).isoformat(timespec="seconds")
    match = re.search(
        r'"(?:datePublished|publicationDate|publishedAt|createdAt)"\s*:\s*"([^\"]+)"',
        html,
        flags=re.I,
    )
    return match.group(1)[:40] if match else None


def source_id_from_url(source: str, url: str) -> str:
    patterns = {
        "idealista": [r"/imovel/(\d+)", r"/inmueble/(\d+)"],
        "imovirtual": [r"-ID([A-Za-z0-9]+)\.html", r"/anuncio/([^/?#]+)"],
        "supercasa": [r"/i(\d+)(?:/|$|\?)", r"/(?:[^/?#]*?)-(\d{5,})(?:/|$|\?)"],
        "casa_sapo": [r"-([a-f0-9-]{16,})(?:\.html)?", r"/([^/?#]+)/?$"],
        "olx": [r"-ID([A-Za-z0-9]+)\.html"],
        "custojusto": [r"-(\d{7,})(?:/|$|\?|#)"],
    }
    for pattern in patterns.get(source, []):
        match = re.search(pattern, url, flags=re.I)
        if match:
            return match.group(1)
    digest = hashlib.sha256(url.split("#", 1)[0].encode()).hexdigest()
    return digest[:20]


def parse_listing(source: str, url: str, html: str) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    item = _listing_json(soup)
    title = (
        item.get("name")
        or item.get("headline")
        or _first_meta(soup, "og:title", "twitter:title")
        or (soup.title.get_text(" ", strip=True) if soup.title else urlparse(url).path)
    )
    description_parts = [
        item.get("description"),
        _first_meta(soup, "og:description", "description", "twitter:description"),
        visible_text(BeautifulSoup(html, "html.parser")),
    ]
    description = " ".join(
        str(part).strip() for part in description_parts if part and str(part).strip()
    )
    title = SPACE_RE.sub(" ", str(title)).strip()
    description = SPACE_RE.sub(" ", str(description)).strip()[:16000]
    combined = f"{title} {description}"
    normalized = normalize_text(combined)

    offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
    price = _as_float(offers.get("price") or item.get("price"))
    if price is None:
        price_pattern = r"\b(\d{1,3}[.,]\d{3}|\d{3,4}(?:[.,]\d{1,2})?)\s*€(?:\s*/\s*(?:mes|mês))?"
        price = _regex_float([price_pattern], title)
    if price is None:
        price = _regex_float(
            [
                r"(?:renda|preco|arrendamento)\D{0,20}(\d{1,3}[.,]\d{3}|\d{3,4}(?:[.,]\d{1,2})?)\s*€",
                price_pattern,
            ],
            combined,
        )

    area = _as_float(item.get("floorSize"))
    if area is None:
        area = _regex_float([r"\b(\d{1,3}(?:[.,]\d+)?)\s*m\s*[²2]\b"], combined)

    typology_match = re.search(r"\bT\s*(\d{1,2})(?:\b|\+)", combined, flags=re.I)
    if typology_match:
        typology = f"T{int(typology_match.group(1))}"
    elif re.search(r"\b(?:estudio|studio|kitnet|kitchenette)\b", normalized):
        # Os portais nem sempre escrevem T0 nos anúncios de estúdios.
        typology = "T0"
    else:
        typology = None

    address = item.get("address")
    if isinstance(address, dict):
        location_parts = [
            address.get("streetAddress"),
            address.get("addressLocality"),
            address.get("addressRegion"),
        ]
        location = ", ".join(str(part) for part in location_parts if part)
    else:
        location = str(address).strip() if address else None
    location = location or _first_meta(soup, "og:locality", "geo.placename")
    if not location:
        # OLX e CustoJusto expõem a localidade no Offer em vez do Address.
        for value in (
            offers.get("areaServed"),
            offers.get("availableAtOrFrom"),
            item.get("areaServed"),
            item.get("availableAtOrFrom"),
        ):
            if isinstance(value, dict) and value.get("name"):
                location = str(value["name"]).strip()
                break
            if isinstance(value, str) and value.strip():
                location = value.strip()
                break

    latitude, longitude = _extract_coordinates(item, html)
    image = item.get("image") or _first_meta(soup, "og:image", "twitter:image")
    if isinstance(image, list):
        image = image[0] if image else None
    elif isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")

    parking = _bool_signal(
        combined,
        [r"lugar de garagem", r"garagem", r"estacionamento (?:facil|privativo|incluido)", r"parqueamento"],
        [r"sem garagem", r"nao (?:tem|possui) (?:garagem|estacionamento)"],
    )
    elevator = _bool_signal(
        combined,
        [r"com elevador", r"predio (?:servido )?por elevador"],
        [r"sem elevador", r"nao (?:tem|possui) elevador"],
    )

    listing = Listing(
        source=source,
        source_id=source_id_from_url(source, url),
        url=url,
        title=title,
        description=description,
        price=price,
        area_m2=area,
        typology=typology,
        location=location,
        latitude=latitude,
        longitude=longitude,
        floor=_extract_floor(combined),
        elevator=elevator,
        parking=parking,
        fiber=_bool_signal(combined, [r"\bfibra\b", r"internet de alta velocidade"], [r"sem fibra"]),
        quiet=_bool_signal(combined, [r"zona (?:muito )?tranquila", r"pouco ruido", r"silencios[oa]"], [r"zona ruidosa"]),
        natural_light=_bool_signal(combined, [r"luz natural", r"muita luminosidade", r"muito luminos[oa]", r"boa exposicao solar"], [r"pouca luz natural"]),
        published_at=_extract_published(combined, html),
        image_url=str(image) if image else None,
        terms=_extract_terms(combined, price),
        public_transport_bonus=bool(re.search(r"\b(?:metro|autocarro|transportes publicos)\b", normalized)),
    )
    if price and area:
        listing.price_per_m2 = round(price / area, 2)
    return listing

