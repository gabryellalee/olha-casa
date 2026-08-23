from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from .extract import parse_listing, source_id_from_url
from .models import Listing


LOG = logging.getLogger(__name__)


DETAIL_PATTERNS = {
    "idealista": [r"/(?:imovel|inmueble)/\d+"],
    "imovirtual": [r"/pt/anuncio/", r"-ID[A-Za-z0-9]+\.html"],
    "supercasa": [r"/(?:arrendamento|arrendar|alugar)-[^?#]+/i\d+"],
    # Os resultados incluem links de navegação como /alugar-quartos/ e
    # /alugar-terrenos/. Os anúncios reais têm um UUID no URL.
    "casa_sapo": [r"-[a-f0-9-]{16,}(?:\.html)?"],
}


@dataclass
class FetchResult:
    listings: list[Listing]
    errors: list[str]
    candidates_found: int


class PortalCollector:
    def __init__(
        self,
        config: dict,
        known_keys: set[str] | None = None,
        refresh_known: bool = False,
        refresh_urls: dict[str, list[str]] | None = None,
    ):
        search = config["search"]
        self.timeout = float(search.get("request_timeout_seconds", 20))
        self.delay = float(search.get("request_delay_seconds", 1.2))
        self.max_candidates = int(search.get("max_candidates_per_source", 45))
        self.known_refresh_limit = int(search.get("known_refresh_limit_per_source", 12))
        self.user_agent = search.get("user_agent", "OlhaCasa/0.1")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.5",
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        self._robots: dict[str, RobotFileParser | None] = {}
        self.known_keys = known_keys or set()
        self.refresh_known = refresh_known
        self.refresh_urls = refresh_urls or {}

    def _robots_parser(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        robots_url = f"{origin}/robots.txt"
        try:
            response = self.session.get(robots_url, timeout=self.timeout)
            if response.status_code == 200:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
                self._robots[origin] = parser
                return parser
        except requests.RequestException as exc:
            LOG.warning("Não foi possível consultar %s: %s", robots_url, exc)
        self._robots[origin] = None
        return None

    def _allowed(self, url: str) -> bool:
        parser = self._robots_parser(url)
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    def _get(self, url: str) -> str:
        if not self._allowed(url):
            raise PermissionError(f"robots.txt não permite recolher {url}")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and not response.text.lstrip().startswith("<"):
            raise ValueError(f"resposta não HTML em {url}")
        return response.text

    @staticmethod
    def _same_domain(candidate: str, search_url: str) -> bool:
        left = urlparse(candidate).netloc.removeprefix("www.")
        right = urlparse(search_url).netloc.removeprefix("www.")
        return left == right

    def _candidate_urls(self, source: str, search_url: str, html: str) -> list[str]:
        patterns = DETAIL_PATTERNS.get(source, [])
        soup = BeautifulSoup(html, "html.parser")
        values: list[str] = []
        for anchor in soup.find_all("a", href=True):
            values.append(anchor["href"])
        # Alguns portais colocam URLs apenas em JSON embebido.
        values.extend(re.findall(r'"(?:url|canonicalUrl|href)"\s*:\s*"([^\"]+)"', html))

        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            raw = raw.replace("\\/", "/").replace("\\u002F", "/")
            candidate = urljoin(search_url, raw).split("#", 1)[0]
            if source == "casa_sapo" and urlparse(candidate).netloc.startswith("gespub."):
                redirect = parse_qs(urlparse(candidate).query).get("l", [None])[0]
                if redirect:
                    candidate = unquote(redirect)
            if not self._same_domain(candidate, search_url):
                continue
            if not any(re.search(pattern, candidate, flags=re.I) for pattern in patterns):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            result.append(candidate)
            if len(result) >= self.max_candidates:
                break
        return result

    def collect_source(self, source_cfg: dict) -> FetchResult:
        source = source_cfg["name"]
        errors: list[str] = []
        candidates: list[str] = []
        for search_url in source_cfg.get("search_urls", []):
            try:
                html = self._get(search_url)
                candidates.extend(self._candidate_urls(source, search_url, html))
            except Exception as exc:  # fonte externa: isolar falhas por portal
                errors.append(f"{source}: pesquisa falhou: {exc}")

        candidates = list(dict.fromkeys(candidates))[: self.max_candidates]
        new_candidates: list[str] = []
        known_candidates: list[str] = []
        for url in candidates:
            key = f"{source}:{source_id_from_url(source, url)}"
            if key in self.known_keys:
                known_candidates.append(url)
            else:
                new_candidates.append(url)
        candidates_to_fetch = new_candidates
        if self.refresh_known:
            refresh_pool = known_candidates + self.refresh_urls.get(source, [])
            candidates_to_fetch += list(dict.fromkeys(refresh_pool))[: self.known_refresh_limit]
        listings: list[Listing] = []
        for index, url in enumerate(candidates_to_fetch):
            try:
                if index:
                    time.sleep(self.delay)
                listing = parse_listing(source, url, self._get(url))
                listings.append(listing)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                errors.append(f"{source}: anúncio falhou ({url}): {exc}")
                if status == 429:
                    errors.append(
                        f"{source}: limite temporário atingido; os restantes anúncios "
                        "ficam para a próxima pesquisa"
                    )
                    break
            except Exception as exc:  # uma página inválida não interrompe as restantes
                errors.append(f"{source}: anúncio falhou ({url}): {exc}")
        return FetchResult(listings=listings, errors=errors, candidates_found=len(candidates))

    def collect_all(self, sources: list[dict]) -> FetchResult:
        listings: list[Listing] = []
        errors: list[str] = []
        candidates = 0
        for source_cfg in sources:
            if not source_cfg.get("enabled", True):
                continue
            result = self.collect_source(source_cfg)
            listings.extend(result.listings)
            errors.extend(result.errors)
            candidates += result.candidates_found
        return FetchResult(listings=listings, errors=errors, candidates_found=candidates)
