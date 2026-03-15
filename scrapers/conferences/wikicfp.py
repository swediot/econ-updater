"""WikiCFP (Call For Papers) scraper for economics conferences."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Conference

logger = logging.getLogger(__name__)


class WikiCFPScraper(BaseScraper):
    SOURCE_NAME = "WikiCFP"
    LISTING_URL = "http://www.wikicfp.com/cfp/call?conference=economics&skip=0"

    def scrape_conferences(self) -> list[Conference]:
        conferences = []

        try:
            resp = self.fetch(self.LISTING_URL)
            conferences = self._parse_listing(resp.text)
        except Exception as e:
            logger.warning(f"[WikiCFP] Failed: {e}")

        logger.info(f"[WikiCFP] Found {len(conferences)} conferences")
        return conferences

    def _parse_listing(self, html: str) -> list[Conference]:
        conferences = []
        soup = BeautifulSoup(html, "html.parser")
        now = datetime.now(timezone.utc)

        # WikiCFP uses a table-based layout
        rows = soup.select("table.tablelist tr")

        i = 0
        while i < len(rows):
            try:
                row = rows[i]
                cells = row.find_all("td")

                if len(cells) < 4:
                    i += 1
                    continue

                # First row of a pair: short name + link, full name
                link_el = cells[0].find("a")
                if not link_el:
                    i += 1
                    continue

                short_name = link_el.get_text(strip=True)
                link = link_el.get("href", "")
                if link and not link.startswith("http"):
                    link = f"http://www.wikicfp.com{link}"

                full_name = cells[1].get_text(strip=True) if len(cells) > 1 else short_name

                # Second row of pair: dates and location
                if i + 1 < len(rows):
                    detail_row = rows[i + 1]
                    detail_cells = detail_row.find_all("td")

                    deadline_text = ""
                    location = ""
                    date_text = ""

                    if len(detail_cells) >= 3:
                        date_text = detail_cells[0].get_text(strip=True)
                        location = detail_cells[1].get_text(strip=True)
                        deadline_text = detail_cells[2].get_text(strip=True)

                    deadline = self._parse_date(deadline_text)
                    start_date = self._parse_date(date_text)

                    # Skip past events
                    if deadline and deadline < now and start_date and start_date < now:
                        i += 2
                        continue

                    # Check if European location
                    is_european = self._is_european(location)

                    conferences.append(Conference(
                        name=f"{short_name}: {full_name}" if full_name != short_name else short_name,
                        url=link,
                        source=self.SOURCE_NAME,
                        deadline=deadline,
                        start_date=start_date,
                        location=location,
                        description="",
                        phd_friendly=True,
                    ))

                i += 2  # Skip the detail row
            except Exception as e:
                logger.debug(f"[WikiCFP] Skipping row: {e}")
                i += 1
                continue

        return conferences

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None

        text = text.strip()
        formats = [
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _is_european(self, location: str) -> bool:
        """Check if location is in Europe."""
        european_markers = [
            "uk", "united kingdom", "england", "germany", "france", "italy",
            "spain", "netherlands", "belgium", "austria", "switzerland",
            "sweden", "norway", "denmark", "finland", "portugal", "greece",
            "ireland", "poland", "czech", "hungary", "romania", "croatia",
            "slovenia", "slovakia", "estonia", "latvia", "lithuania",
            "luxembourg", "iceland", "europe",
        ]
        loc_lower = location.lower()
        return any(marker in loc_lower for marker in european_markers)
