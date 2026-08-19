from pathlib import Path

from olha_casa.config import load_config
from olha_casa.models import Listing, RentalTerms
from olha_casa.scoring import score_listing


CONFIG = load_config(Path(__file__).parents[1] / "config.example.yml")


def good_listing(**changes):
    values = {
        "source": "test",
        "source_id": "1",
        "url": "https://example.test/1",
        "title": "T1 com garagem na Maia",
        "description": "",
        "price": 680,
        "area_m2": 52,
        "typology": "T1",
        "location": "Maia",
        "floor": 1,
        "elevator": True,
        "parking": True,
        "fiber": True,
        "quiet": True,
        "natural_light": True,
        "peak_drive_minutes": 18,
        "public_transport_bonus": True,
        "price_per_m2": 13.08,
        "local_median_price_per_m2": 15,
        "terms": RentalTerms(
            deposits=1,
            advance_rents=2,
            entry_total=2040,
            equipped_kitchen=True,
            included_expenses=["condomínio"],
        ),
    }
    values.update(changes)
    return Listing(**values)


def test_good_listing_is_recommended():
    listing = good_listing()
    score_listing(listing, CONFIG)
    assert listing.recommended is True
    assert listing.score >= 8.5


def test_third_floor_without_elevator_is_rejected():
    listing = good_listing(floor=3, elevator=False)
    score_listing(listing, CONFIG)
    assert listing.recommended is False
    assert any("2.º andar" in reason for reason in listing.rejection_reasons)


def test_over_700_needs_exceptional_score():
    listing = good_listing(price=740, area_m2=46, price_per_m2=16.09, local_median_price_per_m2=None)
    listing.fiber = None
    listing.quiet = None
    listing.natural_light = None
    score_listing(listing, CONFIG)
    assert listing.recommended is False
    assert any("8.5" in reason for reason in listing.rejection_reasons)


def test_over_30_minutes_is_rejected():
    listing = good_listing(peak_drive_minutes=31)
    score_listing(listing, CONFIG)
    assert listing.recommended is False
    assert any("30 min" in reason for reason in listing.rejection_reasons)

