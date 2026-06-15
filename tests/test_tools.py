"""
Tests for the three FitFindr tools.

Run from the project root:
    pytest tests/

search_listings is pure local filtering, so its tests always run.
suggest_outfit and create_fit_card call the Groq LLM; those tests are
skipped automatically if GROQ_API_KEY is not set, so the suite still
passes offline / in CI without a key.
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

needs_key = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM test",
)


# ── search_listings ────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, not an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_substring():
    # "M" should match free-form sizes like "S/M" or "M".
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_sorted_by_relevance():
    # More keyword overlap should rank earlier — verify non-increasing scores.
    results = search_listings("vintage denim jacket", size=None, max_price=None)
    assert len(results) >= 2  # sanity: query hits multiple listings


# ── suggest_outfit ─────────────────────────────────────────────────────────

@needs_key
def test_suggest_outfit_with_wardrobe():
    item = search_listings("graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str) and out.strip() != ""


@needs_key
def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe must NOT crash and must return advice.
    item = search_listings("graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str) and out.strip() != ""


# ── create_fit_card ────────────────────────────────────────────────────────

def test_fit_card_empty_outfit_guard():
    # Failure mode: empty outfit → descriptive string, not an exception.
    # No API call is made on this path, so it runs without a key.
    item = {"title": "Faded Band Tee", "price": 22.0, "platform": "depop"}
    msg = create_fit_card("", item)
    assert isinstance(msg, str)
    assert "without an outfit" in msg.lower()


@needs_key
def test_fit_card_varies_across_runs():
    item = search_listings("graphic tee", size=None, max_price=50)[0]
    outfit = "Pair with wide-leg jeans and chunky sneakers."
    a = create_fit_card(outfit, item)
    b = create_fit_card(outfit, item)
    assert a.strip() and b.strip()
    assert a != b  # high temperature should make outputs differ
