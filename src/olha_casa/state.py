from __future__ import annotations

import json
from difflib import SequenceMatcher
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import Listing
from .extract import normalize_text


def _now() -> datetime:
    return datetime.now(UTC)


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            data.setdefault("listings", {})
            data.setdefault("fingerprints", {})
            data.setdefault("initialized", False)
            return data
        return {
            "schema_version": 1,
            "initialized": False,
            "listings": {},
            "fingerprints": {},
            "last_heartbeat": None,
            "last_price_refresh": None,
        }

    @property
    def initialized(self) -> bool:
        return bool(self.data.get("initialized"))

    @property
    def known_keys(self) -> set[str]:
        return set(self.data["listings"])

    @property
    def historical_records(self) -> list[dict[str, Any]]:
        return list(self.data["listings"].values())

    def refresh_urls_by_source(self) -> dict[str, list[str]]:
        records = sorted(
            self.data["listings"].values(),
            key=lambda item: str(item.get("last_seen", "")),
        )
        result: dict[str, list[str]] = {}
        for record in records:
            source = record.get("source")
            url = record.get("url")
            if source and url:
                result.setdefault(str(source), []).append(str(url))
        return result

    def cached_route(self, key: str) -> tuple[int | None, str | None]:
        record = self.data["listings"].get(key, {})
        value = record.get("peak_drive_minutes")
        return (int(value), record.get("drive_estimate_kind")) if value is not None else (None, None)

    def should_refresh_prices(self, every_hours: int = 6) -> bool:
        raw = self.data.get("last_price_refresh")
        if not raw:
            return True
        try:
            previous = datetime.fromisoformat(raw)
        except ValueError:
            return True
        return _now() - previous >= timedelta(hours=every_hours)

    def mark_price_refresh(self) -> None:
        self.data["last_price_refresh"] = _now().isoformat(timespec="seconds")

    def classify(self, listing: Listing) -> None:
        existing = self.data["listings"].get(listing.key)
        if existing:
            listing.first_seen_at = existing.get("first_seen")
            old_price = existing.get("price")
            if old_price is not None and listing.price is not None and listing.price < old_price:
                listing.event = "price_drop"
                listing.previous_price = float(old_price)
            else:
                listing.event = "unchanged"
            return

        previous_key = self.data["fingerprints"].get(listing.fingerprint or "")
        if not previous_key:
            previous_key = self._find_similar(listing)
        if previous_key and previous_key in self.data["listings"]:
            previous = self.data["listings"][previous_key]
            listing.event = "republication"
            if previous.get("price") is not None:
                listing.previous_price = float(previous["price"])
        else:
            listing.event = "new"

    def _find_similar(self, listing: Listing) -> str | None:
        best_key = None
        best_score = 0.0
        title = normalize_text(listing.title)
        location = normalize_text(listing.location or "")
        for key, record in self.data["listings"].items():
            if record.get("typology") != listing.typology:
                continue
            old_area = record.get("area_m2")
            if old_area is not None and listing.area_m2 is not None:
                if abs(float(old_area) - listing.area_m2) > 4:
                    continue
            old_location = normalize_text(str(record.get("location") or ""))
            if location and old_location:
                left = set(location.split())
                right = set(old_location.split())
                overlap = len(left & right) / max(1, min(len(left), len(right)))
                if overlap < 0.5 and location not in old_location and old_location not in location:
                    continue
            title_similarity = SequenceMatcher(
                None, title, normalize_text(str(record.get("title") or ""))
            ).ratio()
            if title_similarity > best_score and title_similarity >= 0.52:
                best_key = key
                best_score = title_similarity
        return best_key

    def update(self, listing: Listing) -> None:
        now = _now().isoformat(timespec="seconds")
        today = now[:10]
        existing = self.data["listings"].get(listing.key, {})
        record = listing.public_record()
        record["first_seen"] = existing.get("first_seen", now)
        listing.first_seen_at = record["first_seen"]
        previous_seen = str(existing.get("last_seen", ""))
        record["last_seen"] = previous_seen if previous_seen.startswith(today) else now
        history = list(existing.get("price_history", []))
        if listing.price is not None and (not history or history[-1].get("price") != listing.price):
            history.append({"at": now, "price": listing.price})
        record["price_history"] = history[-20:]
        if listing.event in {"new", "republication", "price_drop"}:
            record["last_change"] = now
        else:
            record["last_change"] = existing.get("last_change", now)
        self.data["listings"][listing.key] = record
        if listing.fingerprint:
            self.data["fingerprints"][listing.fingerprint] = listing.key

    def initialize(self) -> None:
        self.data["initialized"] = True

    def heartbeat_due(self, days: int = 7) -> bool:
        raw = self.data.get("last_heartbeat")
        if not raw:
            return True
        try:
            return _now() - datetime.fromisoformat(raw) >= timedelta(days=days)
        except ValueError:
            return True

    def heartbeat(self) -> None:
        self.data["last_heartbeat"] = _now().isoformat(timespec="seconds")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
