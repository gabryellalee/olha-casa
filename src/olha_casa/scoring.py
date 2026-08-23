from __future__ import annotations

import re
from statistics import median

from .extract import normalize_text
from .fraud import detect_fraud_signals
from .geo import location_allowed
from .models import Listing


def attach_market_medians(listings: list[Listing], historical: list[dict]) -> None:
    samples: dict[str, list[float]] = {"T0": [], "T1": []}
    for item in historical:
        typology = item.get("typology")
        value = item.get("price_per_m2")
        if typology in samples and isinstance(value, (int, float)) and 3 <= value <= 80:
            samples[typology].append(float(value))
    for listing in listings:
        if listing.typology in samples and listing.price_per_m2:
            samples[listing.typology].append(listing.price_per_m2)
    for listing in listings:
        values = samples.get(listing.typology or "", [])
        if len(values) >= 3:
            listing.local_median_price_per_m2 = round(median(values), 2)


def _hard_filters(listing: Listing, config: dict) -> list[str]:
    search = config["search"]
    reasons: list[str] = []
    title = normalize_text(listing.title)
    room_only = bool(
        re.search(r"^(?:quartos?|suite)\b", title)
        or re.search(r"^(?:arrend[oa](?:-se)?|alug[oa](?:-se)?).{0,24}\bquartos?\b", title)
        or re.search(r"\bquartos?\s+(?:individuais?|para\s+(?:arrendar|alugar))\b", title)
    )
    if room_only:
        reasons.append("anúncio de quarto, não de habitação completa")
    if listing.typology is None:
        reasons.append("tipologia do imóvel não identificada")
    if listing.price is None:
        reasons.append("renda não identificada")
    elif listing.price > float(search["exceptional_max_rent"]):
        reasons.append(f"renda acima de {search['exceptional_max_rent']} €")
    allowed, geo_reason = location_allowed(listing, config["geo"])
    if not allowed:
        reasons.append(f"fora da área ou por confirmar ({geo_reason})")
    return reasons


def _mark_missing(listing: Listing) -> None:
    checks = [
        (listing.area_m2 is None, "área útil"),
        (listing.parking is None, "garagem ou facilidade real de estacionamento"),
        (listing.floor is None, "andar"),
        (listing.floor is not None and listing.floor > 2 and listing.elevator is None, "elevador"),
        (listing.fiber is None, "fibra/internet disponível"),
        (listing.quiet is None, "nível de ruído"),
        (listing.natural_light is None, "luz natural/orientação solar"),
        (listing.terms.deposits is None, "número de cauções"),
        (listing.terms.advance_rents is None, "rendas adiantadas"),
        (listing.terms.guarantor is None, "necessidade de fiador"),
        (listing.terms.minimum_contract_months is None, "duração mínima do contrato"),
        (listing.terms.equipped_kitchen is None, "cozinha equipada"),
        (listing.terms.pets_allowed is None, "animais permitidos"),
    ]
    listing.missing = [label for condition, label in checks if condition]


def score_listing(listing: Listing, config: dict) -> None:
    _mark_missing(listing)
    listing.rejection_reasons = _hard_filters(listing, config)
    if listing.rejection_reasons:
        listing.score = 0.0
        listing.recommended = False
        listing.fraud_flags = detect_fraud_signals(listing)
        return

    score = 0.0
    reasons: list[str] = []
    price = listing.price or 9999
    if price <= 650:
        score += 2.0
        reasons.append("renda até 650 €")
    elif price <= 700:
        score += 1.7
        reasons.append("renda dentro do limite preferido")
    else:
        score += 0.8
        reasons.append("renda excecional entre 701 € e 750 €")
    if listing.price_per_m2 and listing.local_median_price_per_m2:
        if listing.price_per_m2 <= listing.local_median_price_per_m2 * 0.9:
            score += 0.2
            reasons.append("bom preço por m² face à amostra")

    minutes = listing.peak_drive_minutes or 999
    if minutes <= 15:
        score += 2.0
        reasons.append("ligação muito rápida ao ISCAP")
    elif minutes <= 20:
        score += 1.7
        reasons.append("boa ligação de carro ao ISCAP")
    elif minutes <= 25:
        score += 1.2
        reasons.append("ligação aceitável ao ISCAP")
    else:
        score += 0.7

    if listing.parking is True:
        score += 1.4
        reasons.append("garagem ou estacionamento indicado")
    else:
        score += 0.35

    comfortable = float(
        config["home_office"].get(
            f"comfortable_{listing.typology.lower()}_m2",
            config["home_office"]["comfortable_t1_m2"],
        )
    )
    if listing.area_m2 is None:
        score += 0.3
    elif listing.area_m2 >= comfortable:
        score += 1.1
        reasons.append("área compatível com dois postos de trabalho")
    else:
        score += 0.6
    if listing.typology == "T1":
        score += 0.3

    if listing.floor is None:
        score += 0.25
    elif listing.floor <= 2 or listing.elevator is True:
        score += 0.7

    for value, points, label in [
        (listing.fiber, 0.5, "fibra/internet indicada"),
        (listing.quiet, 0.4, "zona ou casa descrita como tranquila"),
        (listing.natural_light, 0.4, "boa luz natural indicada"),
    ]:
        if value is True:
            score += points
            reasons.append(label)

    terms = listing.terms
    if terms.entry_total is not None and listing.price and terms.entry_total <= listing.price * 3:
        score += 0.35
        reasons.append("entrada inicial até três rendas")
    if terms.equipped_kitchen is True:
        score += 0.2
        reasons.append("cozinha equipada")
    if terms.included_expenses:
        score += 0.15
        reasons.append("algumas despesas incluídas")
    if listing.public_transport_bonus:
        score += 0.3
        reasons.append("transportes públicos mencionados")

    listing.fraud_flags = detect_fraud_signals(listing)
    score -= min(2.0, len(listing.fraud_flags) * 0.55)
    listing.score = round(max(0.0, min(10.0, score)), 1)
    listing.recommendation_reasons = reasons

    # A pontuação é apenas informativa. Qualquer casa, apartamento ou estúdio
    # com tipologia identificada, até ao preço máximo e numa zona aceite gera alerta.
    listing.recommended = True

