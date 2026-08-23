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


def test_ignores_casa_sapo_navigation_links():
    collector = PortalCollector(CONFIG)
    search = "https://casa.sapo.pt/alugar-apartamentos/t0,t1/distrito.porto/"
    html = """
    <a href="/alugar-quartos/t0,t1/distrito.porto/">Quartos</a>
    <a href="/alugar-terrenos/t0,t1/distrito.porto/">Terrenos</a>
    <a href="/alugar-apartamentos/t1/distrito.porto/">T1</a>
    """
    assert collector._candidate_urls("casa_sapo", search, html) == []


def test_stops_source_after_rate_limit(monkeypatch):
    collector = PortalCollector(CONFIG)
    search_url = "https://casa.sapo.pt/alugar-apartamentos/t0,t1/distrito.porto/"
    detail_urls = [
        f"https://casa.sapo.pt/alugar-apartamento-t1-porto-aaaaaaaa-bbbb-cccc-dddd-{index:012d}.html"
        for index in range(3)
    ]
    search_html = "".join(f'<a href="{url}">Casa</a>' for url in detail_urls)
    calls = []

    def fake_get(url):
        calls.append(url)
        if url == search_url:
            return search_html
        import requests

        response = requests.Response()
        response.status_code = 429
        response.url = url
        raise requests.HTTPError("429 Too Many Requests", response=response)

    monkeypatch.setattr(collector, "_get", fake_get)
    result = collector.collect_source(
        {"name": "casa_sapo", "enabled": True, "search_urls": [search_url]}
    )

    assert len(calls) == 2
    assert any("limite temporário" in error for error in result.errors)


def test_manual_scan_fetches_known_candidates(monkeypatch):
    search_url = "https://www.imovirtual.com/pt/resultados/arrendar/apartamento/porto"
    detail_url = "https://www.imovirtual.com/pt/anuncio/apartamento-t1-ID123.html"
    collector = PortalCollector(
        CONFIG,
        known_keys={"imovirtual:ID123"},
        include_known=True,
    )
    calls = []

    def fake_get(url):
        calls.append(url)
        if url == search_url:
            return f'<a href="{detail_url}">Casa</a>'
        return "<html><head><title>T1 Porto</title></head><body></body></html>"

    monkeypatch.setattr(collector, "_get", fake_get)
    result = collector.collect_source(
        {"name": "imovirtual", "enabled": True, "search_urls": [search_url]}
    )

    assert detail_url in calls
    assert len(result.listings) == 1


def test_candidate_limit_is_shared_between_searches():
    groups = [
        ["porto-apartamento-1", "porto-apartamento-2"],
        ["porto-estudio-1", "porto-estudio-2"],
        ["famalicao-moradia-1", "famalicao-moradia-2"],
    ]
    assert PortalCollector._round_robin(groups, 4) == [
        "porto-apartamento-1",
        "porto-estudio-1",
        "famalicao-moradia-1",
        "porto-apartamento-2",
    ]

