from pathlib import Path

from olha_casa.config import load_config
from olha_casa.sources import PortalCollector


CONFIG = load_config(Path(__file__).parents[1] / "config.example.yml")


def test_finds_supercasa_detail_url():
    collector = PortalCollector(CONFIG)
    search = "https://supercasa.pt/arrendar-casas/porto/com-t1"
    html = '<a href="/arrendamento-apartamento-t1-porto/i2230444">Casa</a>'
    assert collector._candidate_urls("supercasa", search, html) == [
        "https://supercasa.pt/arrendamento-apartamento-t1-porto/i2230444"
    ]


def test_decodes_casa_sapo_counter_link():
    collector = PortalCollector(CONFIG)
    search = "https://casa.sapo.pt/alugar-apartamentos/t1/porto/"
    html = """
    <a href="https://gespub.casa.sapo.pt/v3/counter.aspx?l=https%3A%2F%2Fcasa.sapo.pt%2Falugar-apartamento-t1-porto-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.html%3Fg3pid%3D1">Casa</a>
    """
    assert collector._candidate_urls("casa_sapo", search, html) == [
        "https://casa.sapo.pt/alugar-apartamento-t1-porto-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.html?g3pid=1"
    ]

