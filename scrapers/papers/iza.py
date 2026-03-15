"""IZA Discussion Papers scraper via HTML page.

The IZA RSS feed is defunct — we scrape the publications listing page directly.
IZA uses JavaScript rendering, so we parse the HTML for the initial server-rendered content.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Paper

logger = logging.getLogger(__name__)


class IZAScraper(BaseScraper):
    SOURCE_NAME = "IZA"
    LISTING_URL = "https://www.iza.org/publications/dp"

    def scrape_papers(self, lookback_days: int = 8) -> list[Paper]:
        papers = []

        try:
            resp = self.fetch(self.LISTING_URL)
        except Exception as e:
            logger.warning(f"[IZA] Failed to fetch listings: {e}")
            return papers

        soup = BeautifulSoup(resp.text, "html.parser")

        # IZA uses various possible selectors
        for item in soup.select(
            "article, .pub-item, .result-item, .views-row, "
            "tr, .list-group-item, div[class*='paper'], div[class*='pub']"
        ):
            try:
                title_el = item.select_one(
                    "h2 a, h3 a, h4 a, .title a, td a, a[class*='title']"
                )
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                if len(title) < 10:
                    continue

                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = f"https://www.iza.org{link}"

                # Skip non-paper links
                if "/dp" not in link and "/publications" not in link:
                    continue

                # Authors
                author_el = item.select_one(
                    ".authors, .author, span[class*='author'], td:nth-child(2)"
                )
                authors_raw = author_el.get_text(strip=True) if author_el else ""
                authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

                # Date
                date_el = item.select_one(
                    "time, .date, span[class*='date'], td:last-child"
                )
                pub_date = None
                if date_el:
                    pub_date = self._parse_date(date_el.get_text(strip=True))

                papers.append(Paper(
                    title=title,
                    authors=authors,
                    abstract="",
                    url=link,
                    source=self.SOURCE_NAME,
                    date=pub_date,
                ))
            except Exception as e:
                logger.debug(f"[IZA] Skipping item: {e}")
                continue

        # If HTML scraping yields nothing (JS-rendered), try a known API endpoint
        if not papers:
            papers = self._try_api(lookback_days)

        logger.info(f"[IZA] Found {len(papers)} discussion papers")
        return papers

    def _try_api(self, lookback_days: int) -> list[Paper]:
        """Try IZA's internal API as fallback."""
        papers = []
        try:
            # IZA sometimes serves JSON at this endpoint
            resp = self.fetch(
                "https://www.iza.org/api/publications",
                params={"type": "dp", "limit": "50", "sort": "date"},
            )
            if resp.headers.get("content-type", "").startswith("application/json"):
                data = resp.json()
                for item in data if isinstance(data, list) else data.get("items", []):
                    title = item.get("title", "")
                    link = f"https://www.iza.org/publications/dp/{item.get('id', '')}"
                    authors = item.get("authors", [])
                    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
                        authors = [a.get("name", "") for a in authors]
                    abstract = item.get("abstract", "")

                    papers.append(Paper(
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        url=link,
                        source=self.SOURCE_NAME,
                    ))
        except Exception as e:
            logger.debug(f"[IZA] API fallback failed: {e}")

        return papers

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None

        text = text.strip()
        formats = [
            "%B %Y",
            "%b %Y",
            "%Y-%m-%d",
            "%d %b %Y",
            "%d %B %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
