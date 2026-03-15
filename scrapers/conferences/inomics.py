"""INOMICS conference scraper.

INOMICS is the largest economics conference aggregator. Their pages are
JS-heavy but the conference detail links follow a predictable pattern.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Conference

logger = logging.getLogger(__name__)


class INOMICSScraper(BaseScraper):
    SOURCE_NAME = "INOMICS"
    BASE_URL = "https://inomics.com"

    # Pages that list conferences
    LISTING_URLS = [
        "https://inomics.com/top/conferences",
        "https://inomics.com/search?conference=conference&discipline=economics",
    ]

    def scrape_conferences(self) -> list[Conference]:
        conferences = []

        for url in self.LISTING_URLS:
            try:
                resp = self.fetch(url)
                page_confs = self._parse_listing(resp.text)
                conferences.extend(page_confs)
            except Exception as e:
                logger.warning(f"[INOMICS] Failed to fetch {url}: {e}")
                continue

        # Deduplicate by URL
        seen = set()
        unique = []
        for c in conferences:
            if c.url not in seen:
                seen.add(c.url)
                unique.append(c)

        logger.info(f"[INOMICS] Found {len(unique)} conferences/events")
        return unique

    def _parse_listing(self, html: str) -> list[Conference]:
        conferences = []
        soup = BeautifulSoup(html, "html.parser")

        # INOMICS conference links follow the pattern /conference/slug-123456
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)

            # Only conference detail pages
            if "/conference/" not in href:
                continue
            if len(text) < 10:
                continue

            link = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            # Clean title — remove "ConferencePosted X days ago" prefix
            name = text
            for prefix in ["ConferencePosted", "Conference"]:
                if name.startswith(prefix):
                    # Find where the real title starts (after "X days ago")
                    import re

                    cleaned = re.sub(
                        r"^ConferencePosted\s+\d+\s+\w+\s+ago", "", name
                    ).strip()
                    if cleaned:
                        name = cleaned
                    else:
                        name = name.replace(prefix, "").strip()

            conferences.append(
                Conference(
                    name=name,
                    url=link,
                    source=self.SOURCE_NAME,
                    description="",
                    phd_friendly=True,
                )
            )

        return conferences
