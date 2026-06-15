"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract search parameters from a natural-language query.

    Deterministic regex/string parsing (no LLM), as documented in the
    Planning Loop section of planning.md:
      - max_price: a number following "$", "under", "below", or "less than"
      - size:      a standalone size token (XS/S/M/L/XL/XXL or "size 8")
      - description: the query with the price/size phrases stripped out

    Returns a dict: {"description": str, "size": str | None, "max_price": float | None}
    """
    text = query.strip()
    lowered = text.lower()

    # --- max_price -----------------------------------------------------------
    max_price = None
    price_match = re.search(
        r"(?:under|below|less than|<|\$)\s*\$?\s*(\d+(?:\.\d+)?)", lowered
    )
    if price_match:
        max_price = float(price_match.group(1))

    # --- size ----------------------------------------------------------------
    size = None
    # Numeric shoe/clothing size, e.g. "size 8".
    size_num = re.search(r"\bsize\s+(\d{1,2})\b", lowered)
    if size_num:
        size = size_num.group(1)
    else:
        # Letter sizes as whole words (avoid matching the "m" inside other words).
        size_letter = re.search(r"\b(xxl|xl|xs|s|m|l)\b", lowered)
        if size_letter:
            size = size_letter.group(1).upper()

    # --- description ---------------------------------------------------------
    # Strip the phrases we already consumed so they don't pollute keywords.
    description = re.sub(
        r"(?:under|below|less than|<)\s*\$?\s*\d+(?:\.\d+)?", " ", text, flags=re.I
    )
    description = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", description)
    description = re.sub(r"\bsize\s+\w+\b", " ", description, flags=re.I)
    description = re.sub(r"\s+", " ", description).strip()

    return {"description": description or text, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: fresh session — single source of truth for this interaction.
    session = _new_session(query, wardrobe)

    # Step 2: parse the natural-language query into search parameters.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: search. The result of this call decides what happens next.
    session["search_results"] = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )

    # Branch A — no matches: set a specific error and STOP. We do not call
    # suggest_outfit with empty input.
    if not session["search_results"]:
        session["error"] = (
            f"No listings matched \"{query}\". "
            "Try raising your price cap, dropping the size filter, "
            "or using broader keywords."
        )
        return session

    # Branch B — we have matches: continue the pipeline.
    # Step 4: select the top-ranked listing and pass it forward via state.
    session["selected_item"] = session["search_results"][0]

    # Step 5: style the selected item against the user's wardrobe.
    # (Empty wardrobe is handled inside suggest_outfit, so no branch here.)
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: turn the outfit suggestion into a shareable caption.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: done — error stays None on success.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
