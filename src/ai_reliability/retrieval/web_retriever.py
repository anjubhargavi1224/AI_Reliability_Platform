"""Evidence retrieval engine for the AI Reliability Checker.

Retrieves external sources and evidence from authoritative, encyclopedic,
and web sources using live search APIs and HTTP fallback.
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, unquote, urlparse

import httpx

logger = logging.getLogger("ai_reliability.retrieval")

SourceType = Literal[
    "official_doc",
    "government",
    "academic",
    "encyclopedia",
    "news",
    "general_web",
]


@dataclass
class RetrievedSource:
    id: str
    title: str
    url: str
    domain: str
    snippet: str
    source_type: SourceType = "general_web"
    published_date: str | None = None
    relevance_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "source_type": self.source_type,
            "published_date": self.published_date,
            "relevance_score": self.relevance_score,
        }


def extract_domain(url: str) -> str:
    """Extract clean domain name from a URL."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or "external-source"
    except Exception:
        return "external-source"


def classify_source_type(domain: str, url: str) -> SourceType:
    """Classify the authority and type of a source based on domain patterns."""
    domain_lower = domain.lower()
    url_lower = url.lower()

    if (
        domain_lower.endswith(".gov")
        or ".gov." in domain_lower
        or "nasa.gov" in domain_lower
        or "cdc.gov" in domain_lower
        or "nih.gov" in domain_lower
        or "fda.gov" in domain_lower
        or "noaa.gov" in domain_lower
        or "epa.gov" in domain_lower
        or "who.int" in domain_lower
        or "esa.int" in domain_lower
    ):
        return "government"
    if (
        domain_lower.endswith(".edu")
        or ".edu." in domain_lower
        or "arxiv.org" in domain_lower
        or "ncbi.nlm.nih.gov" in domain_lower
        or "nature.com" in domain_lower
        or "sciencedirect.com" in domain_lower
        or "cell.com" in domain_lower
        or "springer.com" in domain_lower
        or "ieee.org" in domain_lower
        or "acm.org" in domain_lower
    ):
        return "academic"
    if "wikipedia.org" in domain_lower or "britannica.com" in domain_lower:
        return "encyclopedia"
    if (
        "docs." in domain_lower
        or "/docs" in url_lower
        or "developer." in domain_lower
        or "support." in domain_lower
        or "help." in domain_lower
        or "legal." in domain_lower
        or "apple.com" in domain_lower
        or "microsoft.com" in domain_lower
        or "github.com" in domain_lower
        or "python.org" in domain_lower
        or "mozilla.org" in domain_lower
    ):
        return "official_doc"
    if any(
        n in domain_lower
        for n in (
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "bbc.co.uk",
            "bloomberg.com",
            "nytimes.com",
            "wsj.com",
            "theguardian.com",
            "scientificamerican.com",
            "newscientist.com",
        )
    ):
        return "news"

    return "general_web"


def get_source_tier(source_type_or_domain: str, url: str = "") -> int:
    """Return the authority tier (1 to 4) of a source.
    
    Tier 1: Government, NASA/scientific agencies, official docs/policies, universities, peer-reviewed research.
    Tier 2: Established international and professional scientific bodies.
    Tier 3: Reputable encyclopedias (Wikipedia, Britannica) and major news agencies.
    Tier 4: Generic websites, blogs, aggregators.
    """
    domain = source_type_or_domain.lower()
    s_type = classify_source_type(domain, url) if ("." in domain or "/" in url) else source_type_or_domain

    if s_type in ("government", "academic", "official_doc"):
        return 1
    if any(d in domain for d in ("who.int", "esa.int", "cern.ch", "ieee.org", "acm.org", "wmo.int")):
        return 2
    if s_type in ("encyclopedia", "news"):
        return 3
    return 4


def get_source_authority_label(source_type_or_domain: str, url: str = "") -> str:
    """Return an accurate authority classification label for a source.
    
    Labels:
    - Primary / Official (Tier 1: official government, NASA, regulatory, vendor documentation)
    - Academic (Tier 1: universities, peer-reviewed scientific journals, research institutions)
    - Reputable Secondary (Tier 3: encyclopedias like Wikipedia/Britannica, major news agencies)
    - General Web (Tier 4: blogs, forums, generic websites)
    """
    domain = source_type_or_domain.lower()
    s_type = classify_source_type(domain, url) if ("." in domain or "/" in url) else source_type_or_domain

    if s_type in ("government", "official_doc"):
        return "Primary / Official"
    if s_type == "academic":
        return "Academic"
    if s_type in ("encyclopedia", "news"):
        return "Reputable Secondary"
    return "General Web"


def clean_ddg_url(raw_url: str) -> str:
    """Extract destination URL from DuckDuckGo redirect links if present."""
    if not raw_url:
        return raw_url
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    if "duckduckgo.com/l/?" in raw_url:
        parsed = urlparse(raw_url)
        params = parse_qs(parsed.query)
        if "uddg" in params and params["uddg"]:
            return unquote(params["uddg"][0])
    return raw_url


class WebRetriever:
    """Autonomous multi-strategy web and evidence retriever."""

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/json,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def search(self, query: str, max_results: int = 5) -> list[RetrievedSource]:
        """Search for external evidence across available strategies."""
        query = query.strip()
        if not query:
            return []

        results: list[RetrievedSource] = []
        seen_urls: set[str] = set()

        # Strategy 1: Optional Tavily Search API if configured
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            tavily_results = self._search_tavily(query, tavily_key, max_results)
            for r in tavily_results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    results.append(r)
            if len(results) >= max_results:
                return results[:max_results]

        # Strategy 2: Wikipedia API (high factual reliability)
        wiki_results = self._search_wikipedia(query, limit=2)
        for r in wiki_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                results.append(r)

        # Strategy 3: DuckDuckGo HTML / Instant Answers Search
        ddg_results = self._search_duckduckgo(query, max_results=max_results)
        for r in ddg_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                results.append(r)

        # Sort by source authority and relevance
        authority_priority = {
            "government": 1.5,
            "official_doc": 1.4,
            "academic": 1.3,
            "encyclopedia": 1.2,
            "news": 1.0,
            "general_web": 0.6,
        }

        for idx, src in enumerate(results):
            base_score = authority_priority.get(src.source_type, 0.6)
            rank_discount = max(0.1, 1.0 - (idx * 0.04))
            src.relevance_score = round(base_score * rank_discount, 3)

        results.sort(key=lambda s: s.relevance_score, reverse=True)
        return results[:max_results]

    def _search_wikipedia(self, query: str, limit: int = 2) -> list[RetrievedSource]:
        """Query Wikipedia API for encyclopedic evidence."""
        results: list[RetrievedSource] = []
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "utf8": 1,
            "srlimit": limit,
        }
        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    search_items = data.get("query", {}).get("search", [])
                    for i, item in enumerate(search_items):
                        title = item.get("title", "")
                        page_id = item.get("pageid", "")
                        raw_snippet = item.get("snippet", "")
                        # Strip HTML tags from wiki snippet
                        clean_snippet = re.sub(r"<[^>]+>", "", raw_snippet).strip()
                        page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        results.append(
                            RetrievedSource(
                                id=f"wiki-{page_id or i+1}",
                                title=f"{title} — Wikipedia",
                                url=page_url,
                                domain="en.wikipedia.org",
                                snippet=clean_snippet,
                                source_type="encyclopedia",
                            )
                        )
        except Exception as exc:
            logger.warning("Wikipedia search failed for '%s': %s", query, exc)
        return results

    def _search_duckduckgo(self, query: str, max_results: int = 5) -> list[RetrievedSource]:
        """Query DuckDuckGo for organic web results and instant answers."""
        results: list[RetrievedSource] = []
        seen_urls: set[str] = set()

        # Strategy 3A: DuckDuckGo Instant Answer API
        try:
            ia_url = "https://api.duckduckgo.com/"
            ia_params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "0"}
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                ia_resp = client.get(ia_url, params=ia_params)
                if ia_resp.status_code == 200:
                    ia_data = ia_resp.json()
                    abstract_url = ia_data.get("AbstractURL")
                    abstract_text = ia_data.get("AbstractText")
                    heading = ia_data.get("Heading")
                    if abstract_url and abstract_text:
                        domain = extract_domain(abstract_url)
                        results.append(
                            RetrievedSource(
                                id="ddg-ia",
                                title=heading or domain,
                                url=abstract_url,
                                domain=domain,
                                snippet=abstract_text,
                                source_type=classify_source_type(domain, abstract_url),
                            )
                        )
                        seen_urls.add(abstract_url)

                    # Check RelatedTopics
                    for r_topic in ia_data.get("RelatedTopics", []):
                        if isinstance(r_topic, dict) and "FirstURL" in r_topic and "Text" in r_topic:
                            f_url = r_topic["FirstURL"]
                            f_text = r_topic["Text"]
                            if f_url not in seen_urls and f_url.startswith("http"):
                                domain = extract_domain(f_url)
                                results.append(
                                    RetrievedSource(
                                        id=f"ddg-topic-{len(results)+1}",
                                        title=domain,
                                        url=f_url,
                                        domain=domain,
                                        snippet=f_text,
                                        source_type=classify_source_type(domain, f_url),
                                    )
                                )
                                seen_urls.add(f_url)
                                if len(results) >= max_results:
                                    return results[:max_results]
        except Exception as exc:
            logger.debug("DuckDuckGo Instant Answer failed for '%s': %s", query, exc)

        # Strategy 3B: DuckDuckGo HTML / Lite Search
        search_urls = [
            ("https://html.duckduckgo.com/html/", {"q": query}),
            ("https://lite.duckduckgo.com/lite/", {"q": query}),
        ]

        for s_url, s_data in search_urls:
            if len(results) >= max_results:
                break
            try:
                with httpx.Client(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
                    resp = client.post(s_url, data=s_data)
                    if resp.status_code == 200:
                        html = resp.text
                        pattern = re.compile(
                            r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
                            r'<a class="result__snippet"[^>]*href="[^"]*"[^>]*>(.*?)</a>',
                            re.DOTALL | re.IGNORECASE,
                        )
                        alt_pattern = re.compile(
                            r'<h2 class="result__title">\s*<a class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>.*?'
                            r'<a class="result__snippet"[^>]*>(.*?)</a>',
                            re.DOTALL | re.IGNORECASE,
                        )
                        lite_pattern = re.compile(
                            r'<a class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
                            r'<td class="result-snippet"[^>]*>(.*?)</td>',
                            re.DOTALL | re.IGNORECASE,
                        )

                        matches = list(alt_pattern.finditer(html)) or list(pattern.finditer(html)) or list(lite_pattern.finditer(html))
                        for i, match in enumerate(matches[:max_results]):
                            raw_url = clean_ddg_url(match.group(1).strip())
                            raw_title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                            raw_snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()

                            if not raw_url.startswith("http") or raw_url in seen_urls:
                                continue

                            domain = extract_domain(raw_url)
                            source_type = classify_source_type(domain, raw_url)

                            results.append(
                                RetrievedSource(
                                    id=f"web-{len(results)+1}",
                                    title=raw_title or domain,
                                    url=raw_url,
                                    domain=domain,
                                    snippet=raw_snippet,
                                    source_type=source_type,
                                )
                            )
                            seen_urls.add(raw_url)
            except Exception as exc:
                logger.warning("DuckDuckGo HTML search failed for '%s': %s", query, exc)

        return results

    def _search_tavily(self, query: str, api_key: str, max_results: int = 5) -> list[RetrievedSource]:
        """Query Tavily Search API if configured."""
        results: list[RetrievedSource] = []
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_domains": [],
        }
        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    for i, item in enumerate(data.get("results", [])):
                        item_url = item.get("url", "")
                        domain = extract_domain(item_url)
                        results.append(
                            RetrievedSource(
                                id=f"tavily-{i+1}",
                                title=item.get("title", domain),
                                url=item_url,
                                domain=domain,
                                snippet=item.get("content", ""),
                                source_type=classify_source_type(domain, item_url),
                                published_date=item.get("published_date"),
                            )
                        )
        except Exception as exc:
            logger.warning("Tavily search failed for '%s': %s", query, exc)
        return results
