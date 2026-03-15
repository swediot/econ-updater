"""LLM-based relevance scorer for papers.

Uses Claude Haiku (cheap + fast) to score each paper's relevance
to the user's research profile on a 0-1 scale.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from scrapers.base import Paper

logger = logging.getLogger(__name__)


def keyword_prescore(paper: Paper, config: dict) -> float:
    """Fast keyword-based pre-filter. Returns 0-1 score."""
    text = f"{paper.title} {paper.abstract}".lower()

    strong_keywords = config.get("keywords", {}).get("strong", [])
    moderate_keywords = config.get("keywords", {}).get("moderate", [])

    strong_hits = sum(1 for kw in strong_keywords if kw.lower() in text)
    moderate_hits = sum(1 for kw in moderate_keywords if kw.lower() in text)

    # Scoring: strong keywords are worth more
    score = min(1.0, (strong_hits * 0.3) + (moderate_hits * 0.1))
    return score


def score_papers_with_llm(
    papers: list[Paper],
    config: dict,
    batch_size: int = 10,
) -> list[Paper]:
    """Score papers using Claude Haiku for relevance.

    Papers are first pre-filtered by keywords, then the top candidates
    are scored by the LLM.
    """
    if not papers:
        return papers

    # Step 1: keyword pre-score
    for paper in papers:
        paper.relevance_score = keyword_prescore(paper, config)

    # Papers with any keyword match get LLM scoring
    candidates = [p for p in papers if p.relevance_score > 0]
    # Also include papers without keyword matches but from key sources
    key_sources = {"NBER", "IZA", "CEPR"}
    for p in papers:
        if any(ks in p.source for ks in key_sources) and p not in candidates:
            candidates.append(p)

    # When no LLM is available, give key-source papers a baseline score
    # so they still appear in the digest
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        for p in candidates:
            if p.relevance_score == 0 and any(ks in p.source for ks in key_sources):
                p.relevance_score = 0.65  # baseline for key sources (above default threshold)

    if not candidates:
        logger.info("No candidate papers for LLM scoring")
        return papers

    # Step 2: LLM scoring
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY set — using keyword scores only")
        return papers

    research_profile = config.get("research_profile", "")
    min_score = config.get("llm", {}).get("min_relevance_score", 0.4)
    model = config.get("llm", {}).get("model", "claude-haiku-4-5-20251001")

    # Score in batches to reduce API calls
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        try:
            _score_batch(batch, research_profile, model, api_key)
        except Exception as e:
            logger.warning(f"LLM scoring failed for batch {i}: {e}")
            # Keep keyword scores as fallback

    return papers


def _score_batch(
    papers: list[Paper],
    research_profile: str,
    model: str,
    api_key: str,
) -> None:
    """Score a batch of papers via the Anthropic API."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    papers_text = ""
    for idx, paper in enumerate(papers):
        abstract_preview = paper.abstract[:500] if paper.abstract else "(no abstract)"
        papers_text += (
            f"\n[{idx}] {paper.title}\n"
            f"    Authors: {', '.join(paper.authors[:5])}\n"
            f"    Abstract: {abstract_preview}\n"
        )

    prompt = f"""You are an academic paper relevance scorer. Given a researcher's profile
and a batch of papers, score each paper's relevance from 0.0 to 1.0.

RESEARCHER PROFILE:
{research_profile}

PAPERS:
{papers_text}

Return ONLY a JSON array of objects with "index" (int) and "score" (float 0.0-1.0).
Score meaning:
- 0.9-1.0: Directly in my research area, must read
- 0.7-0.8: Closely related, should read
- 0.5-0.6: Somewhat related, might be useful
- 0.3-0.4: Tangentially related
- 0.0-0.2: Not relevant

Be generous with labour economics papers. JSON only, no other text."""

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()
        # Extract JSON from response
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            scores = json.loads(json_match.group())
            for item in scores:
                idx = item.get("index", -1)
                score = item.get("score", 0.0)
                if 0 <= idx < len(papers):
                    papers[idx].relevance_score = float(score)
    except Exception as e:
        logger.warning(f"Failed to parse LLM scores: {e}")
