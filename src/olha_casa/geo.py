from __future__ import annotations

import math

from .extract import normalize_text
from .models import Listing


def point_in_polygon(longitude: float, latitude: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        intersects = ((yi > latitude) != (yj > latitude)) and (
            longitude < (xj - xi) * (latitude - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def infer_location(listing: Listing, geo_config: dict) -> None:
    if listing.location:
        return
    text = normalize_text(listing.full_text)
    places = list(geo_config.get("fallback_allowed_places", [])) + list(
        geo_config.get("fallback_excluded_places", [])
    )
    matches = [place for place in places if normalize_text(place) in text]
    if matches:
        listing.location = max(matches, key=len).title()


def location_allowed(listing: Listing, geo_config: dict) -> tuple[bool, str]:
    location = normalize_text(listing.location or listing.full_text)
    for place in geo_config.get("additional_allowed_places", []):
        if normalize_text(place) in location:
            return True, f"concelho adicional: {place}"

    polygon = geo_config.get("allowed_polygon", [])
    if listing.latitude is not None and listing.longitude is not None and polygon:
        allowed = point_in_polygon(listing.longitude, listing.latitude, polygon)
        return allowed, "coordenadas do anúncio"

    for place in geo_config.get("fallback_excluded_places", []):
        if normalize_text(place) in location:
            return False, f"local identificado: {place}"
    for place in geo_config.get("fallback_allowed_places", []):
        if normalize_text(place) in location:
            return True, f"local aproximado: {place}"
    return False, "localização insuficiente para confirmar o círculo"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    value = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
