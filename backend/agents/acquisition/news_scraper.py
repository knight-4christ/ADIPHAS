from scrapling.fetchers import Fetcher, StealthyFetcher
from datetime import datetime
import logging
import time
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source registry — ordered by priority (1 = highest, 3 = lowest)
# method: "rss" uses /feed XML; "html" uses Scrapling StealthyFetcher
# keywords: if set, only articles containing ANY keyword (case-insensitive) are kept
# ---------------------------------------------------------------------------
SOURCES = [
    # ── I. Federal Agencies (priority 1) ───────────────────────────────────
    {
        "name": "NCDC",
        "category": "Federal Agency",
        "url": "https://ncdc.gov.ng/news/press",
        "method": "html",
        "priority": 1,
        "keywords": [], # Bypasses all filters
    },
    {
        "name": "FMoH",
        "category": "Federal Agency",
        "url": "https://health.gov.ng",
        "method": "html",
        "priority": 1,
        "keywords": [],
    },
    {
        "name": "NAFDAC",
        "category": "Federal Agency",
        "url": "https://www.nafdac.gov.ng",
        "method": "html",
        "priority": 1,
        "keywords": [],
    },
    {
        "name": "NPHCDA",
        "category": "Federal Agency",
        "url": "https://nphcda.gov.ng",
        "method": "html",
        "priority": 1,
        "keywords": [],
    },
    # ── II. Lagos State (priority 1) ───────────────────────────────────────
    {
        "name": "Lagos MoH",
        "category": "Lagos State",
        "url": "https://lagosministryofhealth.org",
        "method": "html",
        "priority": 1,
        "keywords": [], # Capture all official Lagos state health news
    },
    {
        "name": "HEFAMAA",
        "category": "Lagos State",
        "url": "https://hefamaa.lagosstate.gov.ng",
        "method": "html",
        "priority": 1,
        "keywords": [],
    },
    # ── III. Lagos Hospitals (priority 2) ──────────────────────────────────
    {
        "name": "LASUTH",
        "category": "Hospital",
        "url": "https://lasuth.org.ng",
        "method": "html",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "GH Ikorodu",
        "category": "Hospital",
        "url": "https://generalhospitalikorodu.org",
        "method": "html",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "GH Alimosho",
        "category": "Hospital",
        "url": "http://alimoshogh.com",
        "method": "html",
        "priority": 2,
        "keywords": [],
    },
    # ── IV. Health Journalism — RSS preferred (priority 2) ─────────────────
    {
        "name": "Nigeria Health Watch",
        "category": "Health Journalism",
        "url": "https://articles.nigeriahealthwatch.com/feed",
        "method": "rss",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "Medical World Nigeria",
        "category": "Health Journalism",
        "url": "https://medicalworldnigeria.com/feed",
        "method": "rss",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "HealthNews.ng",
        "category": "Health Journalism",
        "url": "http://healthnews.ng/feed",
        "method": "rss",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "Public Health Nigeria",
        "category": "Health Journalism",
        "url": "https://www.publichealth.com.ng/feed",
        "method": "rss",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "NiMedHealth",
        "category": "Health Journalism",
        "url": "https://nimedhealth.com.ng/feed",
        "method": "rss",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "WHO Nigeria",
        "category": "Health Journalism",
        "url": "https://www.afro.who.int/countries/nigeria/news",
        "method": "html",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "Punch Health",
        "category": "Health Journalism",
        "url": "https://punchng.com/health",
        "method": "html",
        "priority": 2,
        "keywords": ["outbreak", "cholera", "lassa", "mpox", "cases", "virus", "infection", "deaths", "epidemic"],
    },
    {
        "name": "Vanguard News",
        "category": "Health Journalism",
        "url": "https://www.vanguardngr.com/category/health/",
        "method": "html",
        "priority": 2,
        "keywords": ["outbreak", "cholera", "lassa", "mpox", "cases", "virus", "infection", "deaths", "epidemic"],
    },
    # ── V. Aggregators (priority 3) ────────────────────────────────────────
    {
        "name": "Pulse Nigeria",
        "category": "Aggregator",
        "url": "https://www.pulse.ng",
        "method": "html",
        "priority": 3,
        "keywords": ["health", "disease", "outbreak", "hospital", "epidemic",
                     "cholera", "malaria", "lassa", "mpox"],
    },
    {
        "name": "Daily Trust Health",
        "category": "Health Journalism",
        "url": "https://dailytrust.com/category/health/",
        "method": "html",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "ThisDay Health",
        "category": "Health Journalism",
        "url": "https://www.thisdaylive.com/index.php/category/health-wellness/",
        "method": "html",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "The Guardian Health",
        "category": "Health Journalism",
        "url": "https://guardian.ng/category/life/health/",
        "method": "html",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "Premium Times Health",
        "category": "Health Journalism",
        "url": "https://www.premiumtimesng.com/category/news/health-news",
        "method": "html",
        "priority": 2,
        "keywords": [],
    },
]

class NewsScraperAgent:
    def __init__(self):
        self.sources = sorted(SOURCES, key=lambda s: s["priority"])
        self.politeness_delay = 3  # seconds between requests
        
        # Scrapling handles impersonation automatically, but we can set defaults if desired
        StealthyFetcher.adaptive = True # Enable adaptive parsing by default for all instances

        self.intelligence_keywords = [
            "cholera", "lassa", "mpox", "monkeypox", "yellow fever", 
            "diphtheria", "meningitis", "malaria", "covid", "ebola",
            "outbreak", "epidemic", "strange illness", "unusual", "fatality",
            "hospitalized", "emergency", "advisory", "infection",
            "Mastomys", "rat-borne", "hemorrhagic", "inexplicable bleeding",
            "LASHMA", "Ilera Eko", "LASAMBUS", "LSMOH", "HEFAMAA",
        ]

    def _passes_keyword_filter(self, text: str, keywords: list) -> bool:
        if not keywords: return True
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    def _scrape_rss(self, source: dict) -> list:
        """Parse an RSS/Atom feed using scrapling Fetcher (faster/stealthier requests)."""
        try:
            # Use Fetcher for raw XML requests (stealthier than requests.get)
            page = Fetcher.get(source["url"], timeout=30)
            content_str = page.text.strip()
            
            if "</rss>" in content_str:
                content_str = content_str[:content_str.find("</rss>") + 6]
            elif "</feed>" in content_str:
                content_str = content_str[:content_str.find("</feed>") + 7]
            
            root = ET.fromstring(content_str)
        except Exception as e:
            logger.error(f"Error scraping RSS for {source['name']}: {e}")
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        results = []
        for item in items[:15]:
            title_el = item.find("title") or item.find("atom:title", ns)
            link_el  = item.find("link")  or item.find("atom:link", ns)

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if link_el is not None:
                url = link_el.text.strip() if link_el.text else link_el.get("href", "")
            else:
                url = ""

            if title and url and self._passes_keyword_filter(title, source.get("keywords", [])):
                results.append({"title": title, "url": url})
        return results

    def _scrape_html(self, source: dict) -> list:
        """Scrape HTML using a tiered strategy:
        1. Fast: scrapling.Fetcher (HTTP with browser TLS fingerprint) — instant.
        2. Fallback: scrapling.StealthyFetcher (full headless browser) — for blocked sites.
        """
        page = None
        try:
            # Tier 1: Fast HTTP fetcher with browser impersonation (no browser overhead)
            page = Fetcher.get(source["url"], impersonate="chrome", timeout=30)
            if not page or page.status == 0:
                raise ConnectionError("Empty response from fast fetcher")
        except Exception as fast_err:
            logger.warning(f"[Scrapling] Fast fetcher failed for {source['name']} ({fast_err}). Escalating to StealthyFetcher...")
            try:
                # Tier 2: Full headless browser — only launched when site is truly blocking
                page = StealthyFetcher.fetch(source["url"], headless=True, timeout=60000)
            except Exception as stealth_err:
                logger.error(f"[Scrapling] StealthyFetcher also failed for {source['name']}: {stealth_err}")
                raise stealth_err

        extracted = []
        name = source["name"]

        if name == "Punch Health":
            for item in page.css('h2 a, h3 a')[:15]:
                text = item.css('::text').get()
                url = item.attrib.get('href')
                if text and url:
                    extracted.append({"title": text.strip(), "url": url})

        elif name == "Vanguard News":
            for item in page.css('article h2 a, article h3 a')[:10]:
                text = item.css('::text').get()
                url = item.attrib.get('href')
                if text and url:
                    extracted.append({"title": text.strip(), "url": url})

        elif name == "NCDC":
            for item in page.css('li a')[:20]:
                text = item.css('::text').get()
                url = item.attrib.get('href')
                if text and len(text.split()) > 3 and url:
                    if not url.startswith("http"):
                        url = "https://ncdc.gov.ng" + url
                    extracted.append({"title": text.strip(), "url": url})

        elif name == "WHO Nigeria":
            for item in page.css('.views-row a')[:10]:
                text = item.css('::text').get()
                url = item.attrib.get('href')
                if text and url:
                    if not url.startswith("http"):
                        url = "https://www.afro.who.int" + url
                    extracted.append({"title": text.strip(), "url": url})

        # Generic fallback: works for all other sites
        if not extracted:
            for item in page.css('h1 a, h2 a, h3 a')[:20]:
                text = item.css('::text').get()
                url = item.attrib.get('href')
                if text and url:
                    if not url.startswith("http"):
                        base = source["url"].rstrip("/")
                        url = base + "/" + url.lstrip("/")
                    extracted.append({"title": text.strip(), "url": url})

        # Apply keyword filter
        if source.get("keywords"):
            extracted = [e for e in extracted if self._passes_keyword_filter(e["title"], source["keywords"])]

        return extracted

    # ── Public API ─────────────────────────────────────────────────────────

    def scrape(self) -> tuple:
        """
        Scrapes all configured sources.
        Returns: (results: list[dict], trace: list[dict])
        """
        results = []
        trace = []

        trace.append({
            "step": f"Initializing News Scraper Agent — {len(self.sources)} sources configured.",
            "timestamp": datetime.now().replace(microsecond=0)
        })

        for source in self.sources:
            try:
                trace.append({
                    "step": f"[{source['category']}] Scraping {source['name']} via {source['method'].upper()}...",
                    "timestamp": datetime.now().replace(microsecond=0)
                })

                if source["method"] == "rss":
                    extracted = self._scrape_rss(source)
                else:
                    extracted = self._scrape_html(source)

                for item in extracted:
                    results.append({
                        "source": source["name"],
                        "category": source["category"],
                        "title": item["title"],
                        "url": item["url"],
                        "timestamp": datetime.now().replace(microsecond=0),
                    })

                count = len(extracted)
                trace.append({
                    "source_name": source['name'],
                    "items_found": count,
                    "step": f"✓ {source['name']}: {count} article(s) found.",
                    "timestamp": datetime.now().replace(microsecond=0)
                })
                logger.info(f"[NewsScraperAgent] {source['name']} ({source['category']}): {count} items")

                time.sleep(self.politeness_delay)

            except Exception as e:
                logger.warning(f"[NewsScraperAgent] Failed to scrape {source['name']}: {e}")
                trace.append({
                    "step": f"✗ {source['name']}: Error — {str(e)}",
                    "timestamp": datetime.now().replace(microsecond=0)
                })

        trace.append({
            "step": f"Scraping complete. Total: {len(results)} article(s) from {len(self.sources)} sources.",
            "timestamp": datetime.now().replace(microsecond=0)
        })
        return results, trace

    def get_sources_summary(self) -> dict:
        """Returns a summary of configured sources grouped by category."""
        summary = {}
        for s in self.sources:
            cat = s["category"]
            summary.setdefault(cat, []).append({
                "name": s["name"],
                "url": s["url"],
                "method": s["method"],
                "priority": s["priority"],
            })
        return summary
