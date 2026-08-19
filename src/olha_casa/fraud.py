from __future__ import annotations

import re

from .extract import normalize_text
from .models import Listing


def detect_fraud_signals(listing: Listing) -> list[str]:
    text = normalize_text(listing.full_text)
    flags: list[str] = []
    if listing.local_median_price_per_m2 and listing.price_per_m2:
        if listing.price_per_m2 < listing.local_median_price_per_m2 * 0.58:
            flags.append("preço por m² muito abaixo da amostra disponível")
    if re.search(r"(?:pagar|transferir|sinal|reserva).{0,35}(?:antes da visita|sem visita)", text):
        flags.append("pedido de pagamento antes da visita")
    if re.search(r"(?:senhorio|proprietario).{0,30}(?:estrangeiro|fora do pais)", text) and re.search(
        r"(?:transferencia|western union|moneygram|reserva)", text
    ):
        flags.append("proprietário ausente associado a transferência")
    if re.search(r"apenas\s+(?:whatsapp|telegram)", text):
        flags.append("contacto limitado a aplicação de mensagens")
    if listing.terms.deposits is not None and listing.terms.deposits >= 3:
        flags.append("número elevado de cauções")
    if listing.terms.advance_rents is not None and listing.terms.advance_rents >= 4:
        flags.append("muitas rendas adiantadas")
    return flags

