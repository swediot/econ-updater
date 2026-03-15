"""arXiv economics papers scraper using the arXiv API."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests
import xml.etree.ElementTree as ET

from scrapers.base import BaseScraper, Paper

logger = logging.getLogger(__name__)

# arXiv API namespace
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"

# Economics categories on arXiv
ECON_CATEGORIES = [
    "econ.EM",   # Econometrics
    "econ.GN",   # General Economics
    "econ.TH",   # Theoretical Economics
]


class ArxivEconScraper(BaseScraper):
    SOURCE_NAME = "arXiv"
    BASE_URL = "http://export.arxiv.org/api/query"

    def scrape_papers(self, lookback_days: int = 8) -> list[Paper]:
        papers = []

        for cat in ECON_CATEGORIES:
            try:
                cat_papers = self._fetch_category(cat, lookback_days)
                papers.extend(cat_papers)
                time.sleep(3)  # arXiv asks for 3s between requests
            except Exception as e:
                logger.warning(f"[arXiv] Failed for {cat}: {e}")
                continue

        # Deduplicate by URL (a paper can be in multiple categories)
        seen = set()
        unique = []
        for p in papers:
            if p.url not in seen:
                seen.add(p.url)
                unique.append(p)

        logger.info(f"[arXiv] Found {len(unique)} papers")
        return unique

    def _fetch_category(self, category: str, lookback_days: int) -> list[Paper]:
        papers = []

        params = {
            "search_query": f"cat:{category}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 100,
        }

        resp = self.fetch(self.BASE_URL, params=params)
        root = ET.fromstring(resp.text)

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        for entry in root.findall(f"{{{ATOM_NS}}}entry"):
            try:
                published_el = entry.find(f"{{{ATOM_NS}}}published")
                if published_el is not None and published_el.text:
                    pub_date = datetime.fromisoformat(
                        published_el.text.replace("Z", "+00:00")
                    )
                    if pub_date < cutoff:
                        continue
                else:
                    pub_date = None

                title_el = entry.find(f"{{{ATOM_NS}}}title")
                title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""

                summary_el = entry.find(f"{{{ATOM_NS}}}summary")
                abstract = summary_el.text.strip().replace("\n", " ") if summary_el is not None and summary_el.text else ""

                # Get the abstract page link (not PDF)
                link = ""
                for link_el in entry.findall(f"{{{ATOM_NS}}}link"):
                    if link_el.get("type") == "text/html":
                        link = link_el.get("href", "")
                        break
                if not link:
                    id_el = entry.find(f"{{{ATOM_NS}}}id")
                    link = id_el.text.strip() if id_el is not None and id_el.text else ""

                authors = []
                for author_el in entry.findall(f"{{{ATOM_NS}}}author"):
                    name_el = author_el.find(f"{{{ATOM_NS}}}name")
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                if not title or not link:
                    continue

                papers.append(Paper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=link,
                    source=self.SOURCE_NAME,
                    date=pub_date,
                ))
            except Exception as e:
                logger.debug(f"[arXiv] Skipping entry: {e}")
                continue

        return papers
