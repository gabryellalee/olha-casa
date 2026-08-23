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


def test_third_floor_without_elevator_is_still_recommended():
    listing = good_listing(floor=3, elevator=False)
    score_listing(listing, CONFIG)
    assert listing.recommended is True


def test_up_to_750_does_not_need_a_minimum_score():
    listing = good_listing(price=740, area_m2=46, price_per_m2=16.09, local_median_price_per_m2=None)
    listing.fiber = None
    listing.quiet = None
    listing.natural_light = None
    score_listing(listing, CONFIG)
    assert listing.recommended is True


def test_over_30_minutes_is_still_recommended():
    listing = good_listing(peak_drive_minutes=31)
    score_listing(listing, CONFIG)
    assert listing.recommended is True


def test_small_area_no_parking_and_unknown_route_are_still_recommended():
    listing = good_listing(area_m2=20, parking=False, peak_drive_minutes=None)
    score_listing(listing, CONFIG)
    assert listing.recommended is True


def test_over_750_is_rejected():
    listing = good_listing(price=751)
    score_listing(listing, CONFIG)
    assert listing.recommended is False


def test_t2_or_higher_within_budget_is_recommended():
    listing = good_listing(typology="T3", price=750)
    score_listing(listing, CONFIG)
    assert listing.recommended is True


def test_unknown_typology_is_rejected():
    listing = good_listing(typology=None)
    score_listing(listing, CONFIG)
    assert listing.recommended is False


def test_room_ad_leaking_from_house_category_is_rejected():
    listing = good_listing(
        title="Quartos Individuais | Moradia a 5 min do Hospital de São João",
        typology="T1",
        price=349,
    )
    score_listing(listing, CONFIG)
    assert listing.recommended is False
    assert "anúncio de quarto" in listing.rejection_reasons[0]


def test_apartment_title_that_mentions_a_bedroom_is_not_rejected():
    listing = good_listing(title="Apartamento T1 com quarto luminoso")
    score_listing(listing, CONFIG)
    assert listing.recommended is True

