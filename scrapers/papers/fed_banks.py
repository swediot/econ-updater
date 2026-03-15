"""Federal Reserve Banks working papers scraper.

Only the Fed Board RSS feed reliably works. For other banks, we attempt
RSS first and fall back gracefully.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import feedparser

from scrapers.base import BaseScraper, Paper

logger = logging.getLogger(__name__)

# RSS feeds for Fed bank research series (tested March 2026)
FED_FEEDS = {
    "Fed Board (FEDS)": "https://www.federalreserve.gov/feeds/feds.xml",
    "Fed Board (Notes)": "https://www.federalreserve.gov/feeds/feds-notes.xml",
    "NY Fed": "https://www.newyorkfed.org/rss/feeds/staff_reports.xml",
    "St Louis Fed": "https://research.stlouisfed.org/wp/rss.php",
    "Chicago Fed": "https://www.chicagofed.org/~/rss/publications/working-papers",
    "SF Fed": "https://www.frbsf.org/feed/?post_type=wp",
}


class FedBanksScraper(BaseScraper):
    SOURCE_NAME = "Fed"

    def scrape_papers(self, lookback_days: int = 8) -> list[Paper]:
        papers = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        working_feeds = 0

        for bank_name, feed_url in FED_FEEDS.items():
            try:
                feed = feedparser.parse(feed_url)
                if not feed.entries:
                    continue

                working_feeds += 1
                for entry in feed.entries:
                    try:
                        pub_date = None
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            pub_date = datetime(
                                *entry.published_parsed[:6], tzinfo=timezone.utc
                            )
                        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                            pub_date = datetime(
                                *entry.updated_parsed[:6], tzinfo=timezone.utc
                            )

                        if pub_date and pub_date < cutoff:
                            continue

                        title = entry.get("title", "").strip()
                        link = entry.get("link", "").strip()
                        summary = entry.get("summary", "").strip()
                        authors_raw = (
                            entry.get("author", "") or entry.get("dc_creator", "")
                        )
                        authors = [
                            a.strip() for a in authors_raw.split(",") if a.strip()
                        ]

                        if not title or not link:
                            continue

                        papers.append(
                            Paper(
                                title=title,
                                authors=authors,
                                abstract=summary,
                                url=link,
                                source=f"{self.SOURCE_NAME} ({bank_name})",
                                date=pub_date,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"[Fed:{bank_name}] Skipping entry: {e}")
                        continue
            except Exception as e:
                logger.debug(f"[Fed] Feed failed for {bank_name}: {e}")
                continue

        logger.info(
            f"[Fed] Found {len(papers)} papers from {working_feeds}/{len(FED_FEEDS)} working feeds"
        )
        return papers
