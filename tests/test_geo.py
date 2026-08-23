from pathlib import Path

from olha_casa.config import load_config
from olha_casa.geo import location_allowed
from olha_casa.models import Listing


CONFIG = load_config(Path(__file__).parents[1] / "config.example.yml")


def test_famalicao_is_allowed_even_outside_original_polygon():
    listing = Listing(
        source="test",
        source_id="1",
        url="https://example.test/1",
        title="T1 em Vila Nova de Famalicão",
        location="Vila Nova de Famalicão",
        latitude=41.4078,
        longitude=-8.5196,
    )
    allowed, reason = location_allowed(listing, CONFIG["geo"])
    assert allowed is True
    assert "adicional" in reason


def test_pacos_de_ferreira_is_allowed_even_outside_original_polygon():
    listing = Listing(
        source="test",
        source_id="2",
        url="https://example.test/2",
        title="T0 em Paços de Ferreira",
        location="Paços de Ferreira",
        latitude=41.2766,
        longitude=-8.3762,
    )
    allowed, _ = location_allowed(listing, CONFIG["geo"])
    assert allowed is True

