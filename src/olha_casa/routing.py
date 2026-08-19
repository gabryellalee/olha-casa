from __future__ import annotations

import math

import requests

from .extract import normalize_text
from .geo import haversine_km
from .models import Listing


FALLBACK_PEAK_MINUTES = {
    "iscap": 3,
    "sao mamede de infesta": 8,
    "senhora da hora": 15,
    "maia": 18,
    "porto": 25,
    "matosinhos": 25,
    "rio tinto": 22,
    "ermesinde": 22,
    "alfena": 25,
    "trofa": 30,
    "leca da palmeira": 27,
    "perafita": 26,
    "lavra": 30,
    "vilar do pinheiro": 28,
    "modivas": 30,
    "vila cha": 30,
    "mindelo": 30,
    "baguim do monte": 28,
}


def _osrm_minutes(listing: Listing, config: dict) -> int | None:
    if listing.latitude is None or listing.longitude is None:
        return None
    destination = config["geo"]["iscap"]
    base = config.get("routing", {}).get("osrm_url")
    if not base:
        return None
    coordinates = (
        f"{listing.longitude},{listing.latitude};"
        f"{destination['longitude']},{destination['latitude']}"
    )
    url = f"{base.rstrip('/')}/route/v1/driving/{coordinates}"
    try:
        response = requests.get(
            url,
            params={"overview": "false", "alternatives": "false", "steps": "false"},
            timeout=12,
            headers={"User-Agent": config["search"].get("user_agent", "OlhaCasa/0.1")},
        )
        response.raise_for_status()
        routes = response.json().get("routes", [])
        if not routes:
            return None
        free_flow = float(routes[0]["duration"]) / 60
        peak = free_flow * float(config["routing"].get("peak_multiplier", 1.4))
        peak *= float(config["routing"].get("approximate_location_multiplier", 1.15))
        return max(1, math.ceil(peak))
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def estimate_peak_drive(listing: Listing, config: dict) -> None:
    routed = _osrm_minutes(listing, config)
    if routed is not None:
        listing.peak_drive_minutes = routed
        listing.drive_estimate_kind = "rota rodoviária com margem de hora de ponta"
        return

    if listing.latitude is not None and listing.longitude is not None:
        destination = config["geo"]["iscap"]
        distance = haversine_km(
            listing.latitude,
            listing.longitude,
            destination["latitude"],
            destination["longitude"],
        )
        listing.peak_drive_minutes = math.ceil(5 + (distance / 32 * 60) * 1.45)
        listing.drive_estimate_kind = "distância aproximada"
        return

    location = normalize_text(listing.location or listing.full_text)
    for place in sorted(FALLBACK_PEAK_MINUTES, key=len, reverse=True):
        if place in location:
            listing.peak_drive_minutes = FALLBACK_PEAK_MINUTES[place]
            listing.drive_estimate_kind = "estimativa por zona"
            return
    listing.drive_estimate_kind = "desconhecida"

