# FitFindr — Error Handling Demo

Each of FitFindr's three tools has a defined failure mode. This document shows
each one **deliberately triggered**, with the actual output, proving the agent
recovers gracefully — every failure returns a specific, informative response
and **never raises a Python exception**.

Reproduce all three at once from the project root:

```bash
bash demo_failures.sh
```

---

## Failure 1 — `search_listings` returns zero results

**Trigger:** an impossible query (no listing matches the keywords, size, and price).

```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```

**Tool output** — an empty list, not an exception:

```
[]
```

**Full agent** on the same query — the planning loop detects the empty result,
sets a helpful error, and **stops before** `suggest_outfit` (so `fit_card` stays `None`):

```
error   : No listings matched "designer ballgown size XXS under $5". Try raising
          your price cap, dropping the size filter, or using broader keywords.
fit_card : None
```

The message names *what* failed (the exact query) and *what to try next* (three
concrete levers) — not just "no results found."

---

## Failure 2 — `suggest_outfit` with an empty wardrobe

**Trigger:** a valid item, but the user has no wardrobe entered yet.

```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

**Output** — a useful non-empty string (general styling advice), not a crash and not `""`:

```
This adorable Y2K baby tee is perfect for creating a playful, nostalgic look.
To style it, try pairing it with high-waisted jeans or a flowy skirt for a cute,
cottagecore vibe, and add some comfy sneakers or sandals to keep the overall feel
relaxed and casual. You can also layer it under a cardigan or denim jacket for a
more polished look, and don't forget to accessorize with some fun, vintage-inspired
jewelry to really make the butterfly print pop.
```

The empty wardrobe is handled *inside* the tool: it falls back to general advice
for the item alone instead of trying to name pieces that don't exist.

---

## Failure 3 — `create_fit_card` with an empty outfit string

**Trigger:** the tool is called with no outfit to describe.

```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```

**Output** — a descriptive error **string** (guards before any LLM call), not an exception:

```
Can't write a fit card without an outfit suggestion.
```

---

## Summary

| Tool | Failure mode | Response | Exception? |
|------|-------------|----------|------------|
| `search_listings` | No match | `[]`; agent sets `error` + next steps, skips downstream tools | No |
| `suggest_outfit` | Empty wardrobe | General styling advice (non-empty string) | No |
| `create_fit_card` | Empty outfit | `"Can't write a fit card without an outfit suggestion."` | No |
