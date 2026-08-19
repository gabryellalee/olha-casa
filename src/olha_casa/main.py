from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config
from .dedupe import listing_fingerprint
from .geo import infer_location, location_allowed
from .message import format_alert
from .routing import estimate_peak_drive
from .scoring import attach_market_medians, score_listing
from .sources import PortalCollector
from .state import StateStore
from .telegram import TelegramSender


LOG = logging.getLogger("olha_casa")


def _route_if_relevant(listing, config: dict, state: StateStore) -> None:
    cached, kind = state.cached_route(listing.key)
    if cached is not None:
        listing.peak_drive_minutes = cached
        listing.drive_estimate_kind = kind
        return
    if listing.price is None or listing.price > config["search"]["exceptional_max_rent"]:
        return
    if listing.typology not in set(config["search"]["typologies"]):
        return
    allowed, _ = location_allowed(listing, config["geo"])
    if allowed:
        estimate_peak_drive(listing, config)


def run(config_path: str, dry_run: bool = False) -> dict:
    config = load_config(config_path)
    state = StateStore(config["project"].get("state_file", "data/state.json"))
    sender = TelegramSender(config, force_dry_run=dry_run)
    sender.validate()

    refresh_known = state.initialized and state.should_refresh_prices()
    collector = PortalCollector(
        config,
        known_keys=state.known_keys,
        refresh_known=refresh_known,
        refresh_urls=state.refresh_urls_by_source(),
    )
    fetched = collector.collect_all(config["sources"])

    for listing in fetched.listings:
        infer_location(listing, config["geo"])
        listing.fingerprint = listing_fingerprint(listing)
        _route_if_relevant(listing, config, state)

    attach_market_medians(fetched.listings, state.historical_records)
    was_initialized = state.initialized
    alert_candidates = []
    for listing in fetched.listings:
        state.classify(listing)
        score_listing(listing, config)
        if listing.recommended and listing.event in {"new", "republication", "price_drop"}:
            alert_candidates.append(listing)
        state.update(listing)

    if refresh_known and fetched.candidates_found:
        state.mark_price_refresh()
    if fetched.listings and not state.initialized:
        state.initialize()
    if state.heartbeat_due():
        state.heartbeat()

    should_notify_initial = bool(config["project"].get("notify_existing_on_first_run", False))
    if not was_initialized and not should_notify_initial:
        alert_candidates = []

    # Um só alerta por imóvel quando aparece simultaneamente em vários portais.
    best_by_fingerprint = {}
    for listing in alert_candidates:
        current = best_by_fingerprint.get(listing.fingerprint)
        if current is None or listing.score > current.score:
            best_by_fingerprint[listing.fingerprint] = listing
    alerts = sorted(best_by_fingerprint.values(), key=lambda item: item.score, reverse=True)
    for listing in alerts:
        sender.send(format_alert(listing))

    report = {
        "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "candidates_found": fetched.candidates_found,
        "details_fetched": len(fetched.listings),
        "recommended": sum(1 for item in fetched.listings if item.recommended),
        "alerts_sent": len(alerts),
        "first_run_silent": bool(not was_initialized and not should_notify_initial),
        "errors": fetched.errors[-30:],
    }
    report_path = Path(config["project"].get("report_file", "run-report.json"))
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not sender.dry_run:
        state.save()
    LOG.info("Resumo: %s", json.dumps(report, ensure_ascii=False))
    return report


def cli() -> None:
    parser = argparse.ArgumentParser(description="Procura e avalia casas para arrendar")
    parser.add_argument("--config", default="config.example.yml")
    parser.add_argument("--dry-run", action="store_true", help="não envia Telegram nem grava estado")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    cli()
