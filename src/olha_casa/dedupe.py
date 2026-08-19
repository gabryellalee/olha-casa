from __future__ import annotations

import hashlib
import re

from .extract import normalize_text
from .models import Listing


NOISE = {
    "apartamento", "arrendamento", "arrendar", "alugar", "casa", "imovel",
    "porto", "t0", "t1", "novo",
}


def listing_fingerprint(listing: Listing) -> str:
    title = normalize_text(listing.title)
    title = re.sub(r"\b\d{3,4}\s*(?:€|eur)\b", "", title)
    words = [word for word in re.findall(r"[a-z0-9]+", title) if word not in NOISE]
    title_core = " ".join(words[:10])
    location = normalize_text(listing.location or "")
    area_bucket = round(listing.area_m2 / 3) * 3 if listing.area_m2 else "?"
    basis = f"{listing.typology}|{area_bucket}|{location}|{title_core}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]

