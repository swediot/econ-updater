"""NBER conferences and workshops scraper.

NBER runs frequent workshops on labour, public economics, and other topics
that are often open to PhD student paper submissions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Conference

logger = logging.getLogger(__name__)


class NBERConfScraper(BaseScraper):
    SOURCE_NAME = "NBER"
    LISTING_URL = "https://www.nber.org/conferences"

    def scrape_conferences(self) -> list[Conference]:
        conferences = []

        try:
            resp = self.fetch(self.LISTING_URL)
        except Exception as e:
            logger.warning(f"[NBER Conf] Failed to fetch: {e}")
            return conferences

        soup = BeautifulSoup(resp.text, "html.parser")
        now = datetime.now(timezone.utc)

        for el in soup.select(
            "article, .event, .conference-item, .views-row, "
            "div[class*='conference'], div[class*='event'], "
            ".card, .listing-item, .result-item"
        ):
            try:
                title_el = el.select_one(
                    "h2 a, h3 a, h4 a, a[class*='title'], .title a"
                )
                if not title_el:
                    continue

                name = title_el.get_text(strip=True)
                if len(name) < 5:
                    continue

                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = urljoin(self.LISTING_URL, link)

                # Date
                date_el = el.select_one(
                    "time, .date, span[class*='date'], div[class*='date']"
                )
                date_text = date_el.get_text(strip=True) if date_el else ""
                start_date = self._parse_date(date_text)

                # Location
                loc_el = el.select_one(
                    ".location, span[class*='location'], div[class*='location']"
                )
                location = loc_el.get_text(strip=True) if loc_el else ""

                # Skip past events
                if start_date and start_date < now:
                    continue

                conferences.append(
                    Conference(
                        name=name,
                        url=link,
                        source=self.SOURCE_NAME,
                        start_date=start_date,
                        location=location,
                        phd_friendly=True,
                    )
                )
            except Exception as e:
                logger.debug(f"[NBER Conf] Skipping: {e}")
                continue

        logger.info(f"[NBER Conf] Found {len(conferences)} conferences")
        return conferences

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None

        text = text.strip().split("-")[0].split("–")[0].strip()
        formats = [
            "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
