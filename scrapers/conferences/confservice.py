"""conference-service.com economics conference scraper.

Reliable source with structured HTML table of upcoming economics conferences.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Conference

logger = logging.getLogger(__name__)


class ConfServiceScraper(BaseScraper):
    SOURCE_NAME = "ConfService"
    LISTING_URL = "https://www.conference-service.com/conferences/economics.html"

    def scrape_conferences(self) -> list[Conference]:
        conferences = []

        try:
            resp = self.fetch(self.LISTING_URL)
        except Exception as e:
            logger.warning(f"[ConfService] Failed to fetch: {e}")
            return conferences

        soup = BeautifulSoup(resp.text, "html.parser")
        now = datetime.now(timezone.utc)

        for row in soup.select("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            try:
                a = cells[0].find("a")
                if not a:
                    continue

                name = a.get_text(strip=True)
                if len(name) < 5:
                    continue

                link = a.get("href", "")
                if link and not link.startswith("http"):
                    link = f"https://www.conference-service.com{link}"

                # Parse remaining cells for date, location, deadline
                location = ""
                date_text = ""
                deadline_text = ""

                for cell in cells[1:]:
                    text = cell.get_text(strip=True)
                    if not text:
                        continue
                    # Heuristic: dates contain months or dashes
                    if any(
                        m in text.lower()
                        for m in [
                            "jan", "feb", "mar", "apr", "may", "jun",
                            "jul", "aug", "sep", "oct", "nov", "dec",
                        ]
                    ):
                        if not date_text:
                            date_text = text
                        else:
                            deadline_text = text
                    else:
                        if not location:
                            location = text

                start_date = self._parse_date(date_text)
                deadline = self._parse_date(deadline_text)

                # Only future events
                if start_date and start_date < now:
                    continue

                conferences.append(
                    Conference(
                        name=name,
                        url=link,
                        source=self.SOURCE_NAME,
                        deadline=deadline,
                        start_date=start_date,
                        location=location,
                        phd_friendly=True,
                    )
                )
            except Exception as e:
                logger.debug(f"[ConfService] Skipping row: {e}")
                continue

        logger.info(f"[ConfService] Found {len(conferences)} conferences")
        return conferences

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None

        text = text.strip()
        # Often ranges like "Jun 15-17, 2026" — take first date
        text = text.split("-")[0].split("–")[0].strip()

        formats = [
            "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y",
            "%Y-%m-%d", "%d/%m/%Y", "%b %d %Y", "%B %d %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
