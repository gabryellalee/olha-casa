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


def _listing_completeness(listing) -> tuple[int, int]:
    """Escolhe o anúncio mais informativo sem atribuir uma pontuação de qualidade."""
    values = [
        listing.price,
        listing.area_m2,
        listing.typology,
        listing.location,
        listing.latitude,
        listing.longitude,
        listing.published_at,
        listing.image_url,
    ]
    return sum(value is not None for value in values), len(listing.description or "")


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


def run(config_path: str, dry_run: bool = False, send_current: bool = False) -> dict:
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
        include_known=send_current,
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
        if listing.recommended and (
            send_current or listing.event in {"new", "republication", "price_drop"}
        ):
            alert_candidates.append(listing)
        state.update(listing)

    if refresh_known and fetched.candidates_found:
        state.mark_price_refresh()
    if fetched.listings and not state.initialized:
        state.initialize()
    heartbeat_due = state.heartbeat_due()
    if heartbeat_due:
        state.heartbeat()

    should_notify_initial = bool(config["project"].get("notify_existing_on_first_run", False))
    if not was_initialized and not should_notify_initial:
        alert_candidates = []

    # Um só alerta por imóvel quando aparece simultaneamente em vários portais.
    best_by_fingerprint = {}
    for listing in alert_candidates:
        current = best_by_fingerprint.get(listing.fingerprint)
        if current is None or _listing_completeness(listing) > _listing_completeness(current):
            best_by_fingerprint[listing.fingerprint] = listing
    alerts = list(best_by_fingerprint.values())
    for listing in alerts:
        sender.send(format_alert(listing))

    report = {
        "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "candidates_found": fetched.candidates_found,
        "details_fetched": len(fetched.listings),
        "recommended": sum(1 for item in fetched.listings if item.recommended),
        "alerts_sent": len(alerts),
        "send_current": send_current,
        "first_run_silent": bool(not was_initialized and not should_notify_initial),
        "errors": fetched.errors[-30:],
    }
    status_sent = False
    if not was_initialized:
        status = (
            "<b>✅ Olha Casa está ligado</b>\n"
            f"Primeira pesquisa concluída: {fetched.candidates_found} anúncios encontrados "
            f"e {len(fetched.listings)} analisados.\n"
            "A partir de agora, envio aqui os novos anúncios que cumprirem os critérios."
        )
        if fetched.errors:
            failed_sources = sorted({error.split(":", 1)[0] for error in fetched.errors})
            status += (
                "\n⚠️ Algumas páginas recusaram pedidos nesta execução: "
                + ", ".join(failed_sources)
                + ". Vou voltar a tentar automaticamente."
            )
        sender.send(status)
        status_sent = True
    elif heartbeat_due and not alerts:
        sender.send(
            "<b>💚 Olha Casa continua ligado</b>\n"
            f"Esta pesquisa encontrou {fetched.candidates_found} anúncios e não há "
            "novidades compatíveis para enviar."
        )
        status_sent = True
    report["status_sent"] = status_sent
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
    parser.add_argument(
        "--send-current",
        action="store_true",
        help="analisa e envia os anúncios atuais, incluindo os já conhecidos",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run(args.config, dry_run=args.dry_run, send_current=args.send_current)


if __name__ == "__main__":
    cli()

