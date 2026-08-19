from olha_casa.dedupe import listing_fingerprint
from olha_casa.models import Listing
from olha_casa.state import StateStore


def make_listing(source="one", source_id="1", price=700):
    listing = Listing(
        source=source,
        source_id=source_id,
        url=f"https://example.test/{source_id}",
        title="T1 com garagem na Maia",
        price=price,
        area_m2=50,
        typology="T1",
        location="Maia",
    )
    listing.fingerprint = listing_fingerprint(listing)
    return listing


def test_new_price_drop_and_republication(tmp_path):
    store = StateStore(tmp_path / "state.json")
    first = make_listing()
    store.classify(first)
    assert first.event == "new"
    store.update(first)

    cheaper = make_listing(price=650)
    store.classify(cheaper)
    assert cheaper.event == "price_drop"
    assert cheaper.previous_price == 700
    store.update(cheaper)

    repost = make_listing(source="two", source_id="99", price=650)
    store.classify(repost)
    assert repost.event == "republication"

