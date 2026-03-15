"""CEPR Discussion Papers scraper via HTML page.

The CEPR RSS feed is defunct — we scrape the publications listing page directly.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Paper

logger = logging.getLogger(__name__)


class CEPRScraper(BaseScraper):
    SOURCE_NAME = "CEPR"
    LISTING_URL = "https://cepr.org/publications/discussion-papers"

    def scrape_papers(self, lookback_days: int = 8) -> list[Paper]:
        papers = []

        try:
            resp = self.fetch(self.LISTING_URL)
        except Exception as e:
            logger.warning(f"[CEPR] Failed to fetch listings: {e}")
            return papers

        soup = BeautifulSoup(resp.text, "html.parser")

        for article in soup.select("article"):
            try:
                title_el = article.select_one("h2 a, h3 a, h4 a, .title a")
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                # Remove DP number prefix like "DP21294 "
                title = re.sub(r"^DP\d+\s*", "", title)

                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = f"https://cepr.org{link}"

                # Get any description/abstract
                desc_el = article.select_one("p, .field-body, .abstract, .summary")
                abstract = desc_el.get_text(strip=True) if desc_el else ""

                # Get authors
                author_el = article.select_one(
                    ".authors, .field-authors, span[class*='author']"
                )
                authors_raw = author_el.get_text(strip=True) if author_el else ""
                authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

                # Get date
                date_el = article.select_one(
                    "time, .date, span[class*='date']"
                )
                pub_date = None
                if date_el:
                    date_text = date_el.get("datetime", "") or date_el.get_text(strip=True)
                    pub_date = self._parse_date(date_text)

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
                logger.debug(f"[CEPR] Skipping article: {e}")
                continue

        logger.info(f"[CEPR] Found {len(papers)} discussion papers")
        return papers

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None

        text = text.strip()
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
            "%d %b %Y",
            "%d %B %Y",
            "%B %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
