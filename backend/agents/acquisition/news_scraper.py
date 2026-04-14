from bs4 import BeautifulSoup  # type: ignore[import-untyped,import-not-found]
from datetime import datetime
import httpx  # type: ignore[import-untyped,import-not-found]
from typing import Any, Dict, List
import logging
import time
import xml.etree.ElementTree as ET
import re
from scrapling import Fetcher  # type: ignore[import-untyped]

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
        "url": "https://articles.nigeriahealthwatch.com/feed/",
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
    # {
    #     "name": "HealthNews.ng",
    #     "category": "Health Journalism",
    #     "url": "http://healthnews.ng/feed",
    #     "method": "rss",
    #     "priority": 2,
    #     "keywords": [],
    # },
    {
        "name": "Public Health Nigeria",
        "category": "Health Journalism",
        "url": "https://www.publichealth.com.ng/feed/",
        "method": "rss",
        "priority": 2,
        "keywords": [],
    },
    {
        "name": "NiMedHealth",
        "category": "Health Journalism",
        "url": "https://nimedhealth.com.ng/feed/",
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
        """Parse an RSS/Atom feed using httpx."""
        try:
            # RSS Feeds typically don't block basic HTTP clients
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            with httpx.Client(timeout=30, verify=False, follow_redirects=True) as client:
                res = client.get(source["url"], headers=headers)
                res.raise_for_status()
                content_str = res.text.strip()
            
            if "</rss>" in content_str:
                content_str = content_str[:content_str.find("</rss>") + 6]
            elif "</feed>" in content_str:
                content_str = content_str[:content_str.find("</feed>") + 7]
            
            root = ET.fromstring(content_str)
        except Exception as e:
            logger.error(f"Error scraping RSS for {source['name']}: {e}")
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items: list[Any] = root.findall(".//item") or root.findall(".//atom:entry", ns)

        results: List[Dict[str, str]] = []
        for item in list(items)[:15]:  # type: ignore[index]
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
        """Scrape HTML using Scrapling Fetcher v0.4 for stealth.
        Uses curl_cffi TLS fingerprinting to bypass anti-bot firewalls
        on government health portals.
        """
        page = None
        try:
            # Scrapling v0.4: Fetcher.get() is a class method.
            # stealthy_headers enable TLS fingerprinting & real browser headers.
            res = Fetcher.get(
                source["url"],
                stealthy_headers=True,
                timeout=20,
            )
            
            if res.status != 200:
                if res.status in (403, 401, 406):
                    # Cloudflare / Imperva Fallback Bypass
                    logger.info(f"Target {source['name']} blocked connection ({res.status}). Engaging TLS Impersonation Bypass...")
                    try:
                        from curl_cffi import requests as c_req
                        # Impersonating a modern MacOS Safari/Chrome handshake perfectly bypasses Cloudflare
                        fallback = c_req.get(source["url"], impersonate="chrome110", timeout=20)
                        if fallback.status_code == 200:
                            page = BeautifulSoup(fallback.text, "lxml")
                            logger.info(f"[Scraper] Successfully bypassed firewall for {source['name']}!")
                        else:
                            return []
                    except Exception as bypass_err:
                        logger.warning(f"[Scraper] Bypass failed for {source['name']}: {bypass_err}")
                        return []
                else:
                    logger.warning(f"[Scraper] {source['name']} returned status {res.status}")
                    return []
            else:
                page = BeautifulSoup(res.html_content, "lxml")
            
        except Exception as err:
            logger.warning(f"[Scraper] Failed to fetch {source['name']} via Scrapling: {err}")
            return []

        extracted = []
        name = source["name"]

        if name == "Punch Health":
            for item in page.select('h2 a, h3 a')[:15]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    extracted.append({"title": text, "url": url})

        elif name == "Vanguard News":
            for item in page.select('article h2 a, article h3 a')[:10]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    extracted.append({"title": text, "url": url})

        elif name == "NCDC":
            for item in page.select('li a')[:20]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url and "news" in url.lower():
                    if url.startswith('/'):
                        url = "https://ncdc.gov.ng" + url
                    extracted.append({"title": text, "url": url})

        elif name == "FMoH":
            for item in page.select('article h2 a, .entry-title a')[:10]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    extracted.append({"title": text, "url": url})
                    
        elif name == "NAFDAC":
            for item in page.select('.elementor-post__title a, article h3 a')[:20]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    extracted.append({"title": text, "url": url})
                    
        elif name == "Lagos MoH":
            for item in page.select('.entry-title a, h2.title a')[:20]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    extracted.append({"title": text, "url": url})
                    
        elif name == "HEFAMAA":
            for item in page.select('.entry-title a, article a')[:15]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url and len(text) > 10:
                    extracted.append({"title": text, "url": url})
                    
        elif name == "LASUTH":
            for item in page.select('.post-title a, h3 a')[:15]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    extracted.append({"title": text, "url": url})
                    
        elif name == "GH Ikorodu":
            for item in page.select('.elementor-post__title a, h3 a')[:15]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    extracted.append({"title": text, "url": url})

        elif name == "WHO Nigeria":
            for item in page.select('.views-row a')[:10]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    if not url.startswith("http"):
                        url = "https://www.afro.who.int" + url
                    extracted.append({"title": text, "url": url})

        # Generic fallback: works for all other sites
        if not extracted:
            for item in page.select('h1 a, h2 a, h3 a')[:20]:
                text = item.get_text(strip=True)
                url = item.get('href')
                if text and url:
                    if not url.startswith("http"):
                        base = source["url"].rstrip("/")
                        url = base + "/" + url.lstrip("/")
                    extracted.append({"title": text, "url": url})

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
        results: List[Dict[str, Any]] = []
        trace: List[Dict[str, Any]] = []

        trace.append({
            "step": f"Initializing News Scraper Agent — {len(self.sources)} sources configured.",
            "timestamp": datetime.now().replace(microsecond=0)
        })

        for source in self.sources:
            try:
                method_str: str = str(source['method'])
                trace.append({
                    "step": f"[{source['category']}] Scraping {source['name']} via {method_str.upper()}...",
                    "timestamp": datetime.now().replace(microsecond=0)
                })

                if source["method"] == "rss":
                    extracted = self._scrape_rss(source)
                else:
                    extracted = self._scrape_html(source)

                for item in extracted:
                    import html
                    raw_title = item.get("title", "")
                    
                    # Security: Sanitize against basic prompt injections and bloated HTML
                    clean_title = html.unescape(raw_title)
                    clean_title = re.sub(r'<[^>]+>', '', clean_title) # Strip HTML tags
                    clean_title = str(clean_title.strip())[:500] # Truncate absurdly long text  # type: ignore[index]
                    
                    if not clean_title: continue
                    
                    results.append({
                        "source": source["name"],
                        "category": source["category"],
                        "title": clean_title,
                        "url": item.get("url", ""),
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

    def get_sources_summary(self) -> Dict[str, Any]:
        """Returns a summary of configured sources grouped by category."""
        summary: Dict[str, list[Any]] = {}
        for s in self.sources:
            cat = s["category"]
            summary.setdefault(cat, []).append({  # type: ignore[call-overload]
                "name": s["name"],
                "url": s["url"],
                "method": s["method"],
                "priority": s["priority"],
            })
        return summary
