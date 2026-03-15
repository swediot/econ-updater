"""INOMICS conference scraper.

INOMICS is the largest economics conference aggregator. Their pages are
JS-heavy but the conference detail links follow a predictable pattern.
We fetch individual detail pages for structured metadata.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import unquote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Conference

logger = logging.getLogger(__name__)

# Only keep conferences in these regions
ALLOWED_COUNTRIES = {
    # Europe
    "albania", "andorra", "austria", "belgium", "bosnia", "bulgaria", "croatia",
    "cyprus", "czech republic", "czechia", "denmark", "estonia", "finland",
    "france", "germany", "greece", "hungary", "iceland", "ireland", "italy",
    "kosovo", "latvia", "liechtenstein", "lithuania", "luxembourg", "malta",
    "moldova", "monaco", "montenegro", "netherlands", "north macedonia",
    "norway", "poland", "portugal", "romania", "san marino", "serbia",
    "slovakia", "slovenia", "spain", "sweden", "switzerland", "turkey",
    "ukraine", "united kingdom", "uk", "england", "scotland", "wales",
    # North America
    "united states", "usa", "us", "canada", "mexico",
}


class INOMICSScraper(BaseScraper):
    SOURCE_NAME = "INOMICS"
    BASE_URL = "https://inomics.com"

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

        # Deduplicate by normalized name
        seen_names: set[str] = set()
        seen_urls: set[str] = set()
        unique = []
        for c in conferences:
            norm = c.name.lower().strip()
            if norm not in seen_names and c.url not in seen_urls:
                seen_names.add(norm)
                seen_urls.add(c.url)
                unique.append(c)

        logger.info(f"[INOMICS] Found {len(unique)} conferences/events")
        return unique

    def _parse_listing(self, html: str) -> list[Conference]:
        conferences = []
        soup = BeautifulSoup(html, "html.parser")

        seen_hrefs: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/conference/" not in href:
                continue
            link = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            if link in seen_hrefs:
                continue
            seen_hrefs.add(link)

            raw_text = a.get_text(strip=True)
            if len(raw_text) < 10:
                continue

            name, listing_location, listing_start, listing_deadline = self._parse_listing_text(raw_text)

            conf = self._fetch_detail(name, link, listing_location, listing_start, listing_deadline)
            if conf:
                # Filter: only Europe and North America
                if conf.location and not self._is_allowed_location(conf.location):
                    logger.debug(f"[INOMICS] Skipping non-Europe/NA conf: {conf.name} ({conf.location})")
                    continue
                conferences.append(conf)

        return conferences

    def _is_allowed_location(self, location: str) -> bool:
        loc_lower = location.lower()
        return any(country in loc_lower for country in ALLOWED_COUNTRIES)

    def _parse_listing_text(self, raw: str) -> tuple[str, str, datetime | None, datetime | None]:
        """Parse INOMICS concatenated listing text into name, location, dates."""
        text = re.sub(r"^ConferencePosted\s+\d+\s+\w+\s+ago\s*", "", raw).strip()

        # Extract location from "in City, Country" pattern
        location = ""
        loc_match = re.search(r"\bin\s*([A-Z][a-zA-Z\s,.-]+,\s*[A-Z][a-zA-Za-z\s]+?)(?:\d|$)", text)
        if loc_match:
            location = loc_match.group(1).strip().rstrip(",")

        # Extract dates from "Between DD Month and DD Month" pattern
        start_date = None
        date_match = re.search(r"Between\s*(\d{1,2}\s+\w+)\s*and\s*(\d{1,2}\s+\w+).*?(\d{4})", text)
        if date_match:
            start_str = f"{date_match.group(1)} {date_match.group(3)}"
            start_date = self._parse_date(start_str)

        deadline = None
        deadline_match = re.search(r"(\w+\s+\d{1,2},?\s+\d{4})", text)
        if deadline_match:
            deadline = self._parse_date(deadline_match.group(1))

        # Extract clean name
        name = re.split(r"Between\s*\d", text, maxsplit=1)[0].strip()
        if name == text:
            name = re.split(r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text, maxsplit=1)[0].strip()
        if name == text:
            name = re.split(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}", text, maxsplit=1)[0].strip()

        if len(name) < 10:
            name = raw

        return name, location, start_date, deadline

    def _extract_country(self, raw_location: str) -> str:
        """Extract just the country name from a raw location string."""
        if not raw_location:
            return ""

        loc = unquote(raw_location).lower().strip()

        # Find the longest matching country name
        best = ""
        for country in ALLOWED_COUNTRIES:
            if country in loc and len(country) > len(best):
                best = country

        if best:
            # Return properly capitalized
            return best.title() if best not in ("uk", "usa", "us") else best.upper()

        return ""

    def _fetch_detail(
        self, name: str, url: str,
        listing_location: str = "",
        listing_start: datetime | None = None,
        listing_deadline: datetime | None = None,
    ) -> Conference | None:
        """Fetch an INOMICS conference detail page for structured data."""
        try:
            resp = self.fetch(url)
        except Exception as e:
            logger.debug(f"[INOMICS] Detail fetch failed for {url}: {e}")
            return Conference(
                name=name,
                url=url,
                source=self.SOURCE_NAME,
                start_date=listing_start,
                deadline=listing_deadline,
                location=self._extract_country(listing_location),
                phd_friendly=True,
            )

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to get a better title from <h1>
        title_el = soup.select_one("h1")
        if title_el:
            detail_name = title_el.get_text(strip=True)
            # Remove "Email Address" or other form labels that get concatenated
            detail_name = re.sub(r"Email\s*Address.*$", "", detail_name).strip()
            if 10 <= len(detail_name) <= 200:
                name = detail_name

        # Clean name of trailing junk
        name = re.sub(r"Email\s*Address.*$", "", name).strip()

        # Extract country from detail page text
        page_text = soup.get_text(" ", strip=True)
        location = self._extract_country(page_text)

        # Fall back to listing location
        if not location and listing_location:
            location = self._extract_country(listing_location)

        # Extract dates
        start_date = None
        deadline = None
        body_text = soup.get_text(" ", strip=True)

        for pattern in [
            r"Between\s*(\d{1,2}\s+\w+)\s*and\s*\d{1,2}\s+\w+.*?(\d{4})",
            r"(?:Date|Event|Conference date|When)[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
            r"(?:Date|Event|Conference date|When)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        ]:
            m = re.search(pattern, body_text, re.IGNORECASE)
            if m:
                date_str = m.group(1)
                if m.lastindex and m.lastindex >= 2:
                    date_str += f" {m.group(2)}"
                start_date = self._parse_date(date_str)
                if start_date:
                    break

        for pattern in [
            r"(?:Deadline|Submission deadline|Application deadline)[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
            r"(?:Deadline|Submission deadline|Application deadline)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        ]:
            m = re.search(pattern, body_text, re.IGNORECASE)
            if m:
                deadline = self._parse_date(m.group(1))
                if deadline:
                    break

        if not start_date and listing_start:
            start_date = listing_start
        if not deadline and listing_deadline:
            deadline = listing_deadline

        # Description — skip form labels like "Email Address"
        description = ""
        for sel in [".description", ".field-body", ".abstract", ".summary",
                    "div[class*='description']"]:
            el = soup.select_one(sel)
            if el:
                desc_text = el.get_text(strip=True)[:300]
                # Skip if it's just a form label
                if desc_text.lower().strip() not in ("email address", "email", ""):
                    description = desc_text
                break

        # Clean description of form artifacts
        if description:
            description = re.sub(r"Email\s*Address.*$", "", description).strip()

        return Conference(
            name=name,
            url=url,
            source=self.SOURCE_NAME,
            start_date=start_date,
            deadline=deadline,
            location=location,
            description=description,
            phd_friendly=True,
        )

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None
        text = text.strip().rstrip(".")
        formats = [
            "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%B %d %Y",
            "%b %d, %Y", "%b %d %Y", "%Y-%m-%d", "%d/%m/%Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
