# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Loads the 40-item mock dataset via `load_listings()` and returns the listings that match the user's request. It applies hard filters (price ceiling, size) and then ranks the survivors by keyword-overlap relevance against the description, dropping anything with zero keyword matches. It does not call the LLM — it is pure local filtering and scoring.

**Input parameters:**
- `description` (str): keywords describing the wanted item, e.g. `"vintage graphic tee"`. Used for relevance scoring against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): size to filter by, or `None` to skip. Case-insensitive **substring** match against the listing's `size` field, because sizes are free-form (`"S/M"`, `"XL (oversized)"`, `"W30 L30"`) — so `"M"` matches `"S/M"`. Size is a hard filter when provided.
- `max_price` (float | None): inclusive price ceiling, or `None` to skip. A listing is dropped if `listing["price"] > max_price`.

**What it returns:**
A `list[dict]` of matching listings, sorted by relevance score (highest first). Each dict is a full listing with: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or `None`), `platform`. Returns `[]` when nothing matches — it never raises.

**What happens if it fails or returns nothing:**
Returns an empty list (no exception). The planning loop detects `[]`, sets `session["error"]` to a specific suggestion (raise the price cap, drop the size filter, or try broader keywords), and returns early without calling `suggest_outfit`.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the selected listing and the user's wardrobe and asks the Groq LLM for 1–2 concrete outfit ideas that pair the new item with named pieces the user already owns. If the wardrobe is empty it falls back to general styling advice for the item alone (vibe, what kinds of pieces pair well) instead of failing.

**Input parameters:**
- `new_item` (dict): the listing chosen in Step 4 (`session["selected_item"]`). The LLM prompt uses its `title`, `category`, `colors`, and `style_tags` so the suggestion fits the actual piece.
- `wardrobe` (dict): a wardrobe dict shaped `{"items": [ {id, name, category, colors, style_tags, notes}, ... ]}`. The `items` list may be empty — that branch is handled explicitly.

**What it returns:**
A non-empty `str` of natural-language styling text. With a populated wardrobe it names specific owned pieces (e.g. "wide-leg khaki trousers + chunky white sneakers"). With an empty wardrobe it returns general advice. Never returns `""`.

**What happens if it fails or returns nothing:**
Empty wardrobe is not an error — it returns general styling advice. If the LLM call itself raises (network/auth), the loop catches it, sets `session["error"]` to "Couldn't generate an outfit right now — try again," and returns without calling `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion plus item details into a short, casual, shareable caption (Instagram/TikTok OOTD voice). Calls the LLM at a higher temperature so repeated runs read differently rather than templated.

**Input parameters:**
- `outfit` (str): the styling text from `suggest_outfit()` (`session["outfit_suggestion"]`).
- `new_item` (dict): the same selected listing — the caption naturally mentions its `title`, `price`, and `platform` once each.

**What it returns:**
A 2–4 sentence `str` caption in a casual first-person voice that names the item, price, and platform once and captures the outfit vibe (e.g. *"thrifted this faded band tee off depop for $22 🖤 styled it with my wide-legs and chunky sneakers — full look in stories"*).

**What happens if it fails or returns nothing:**
If `outfit` is empty/whitespace-only, it returns a descriptive error **string** (not an exception), e.g. `"Can't write a fit card without an outfit suggestion."` This guards against being called out of order.

---

### Additional Tools (if any)

None — the three required tools cover the full flow (find → style → caption).

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a fixed sequence with two early-exit branches keyed off state. It does not free-choose tools — the order is `parse → search → (select) → suggest → fit_card`, and each step reads the field the previous one wrote.

1. **Initialize:** `session = _new_session(query, wardrobe)`.
2. **Parse query → `session["parsed"]`:** extract `description`, `size`, `max_price` from the natural-language query (regex/string parsing: pull a number after `$`/`under`/`below` for `max_price`; look for a standalone size token like `M`, `S`, `XL` for `size`; treat the remaining words as `description`). Document approach inline.
3. **Search:** `results = search_listings(parsed.description, parsed.size, parsed.max_price)`; store in `session["search_results"]`.
   - **Branch A (empty):** `if not results:` set `session["error"] = "No listings matched '<query>'. Try raising your price cap, dropping the size filter, or using broader keywords."` and **return the session immediately** — do not call `suggest_outfit`.
   - **Branch B (non-empty):** continue.
4. **Select:** `session["selected_item"] = results[0]` (top-ranked match).
5. **Suggest outfit:** `session["outfit_suggestion"] = suggest_outfit(selected_item, session["wardrobe"])`. (Empty wardrobe is handled inside the tool, so no branch needed here; a raised exception is caught → set `session["error"]` and return.)
6. **Fit card:** `session["fit_card"] = create_fit_card(outfit_suggestion, selected_item)`.
7. **Done:** return `session`. The caller checks `session["error"]` first; if `None`, `outfit_suggestion` and `fit_card` are populated.

**Termination:** the loop ends when either an early-exit branch sets `error` and returns, or Step 6 completes and Step 7 returns the full session. There is no looping/retry — one pass per user query.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in the single `session` dict created by `_new_session()` (see [agent.py](agent.py)) — it is the one source of truth for a run; tools never read each other's return values directly, they read/write `session`.

Flow of data through the fields:
- `query` (input) → parsing writes `parsed = {description, size, max_price}`.
- `parsed` → `search_listings` args → its return is stored in `search_results`.
- `search_results[0]` → `selected_item`.
- `selected_item` + `wardrobe` (input) → `suggest_outfit` → `outfit_suggestion`.
- `outfit_suggestion` + `selected_item` → `create_fit_card` → `fit_card`.
- `error` is `None` unless an early-exit branch sets it; when set, downstream fields stay `None`.

Scope is one interaction (one `run_agent` call) — no cross-session memory. The session is returned to the caller (CLI / Gradio app) which renders `selected_item`, `outfit_suggestion`, and `fit_card`, or shows `error`.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Loop sets `session["error"]` and returns early (no `suggest_outfit` call). User sees: *"No listings matched 'designer ballgown size XXS under $5'. Try raising your price cap, dropping the size filter, or using broader keywords."* — names the unmet query and offers three concrete levers. |
| suggest_outfit | Wardrobe is empty | Not treated as an error. The tool returns general styling advice for the item alone (vibe + what kinds of pieces pair with it), so the flow continues to `create_fit_card`. (If the LLM call itself errors, loop sets `error = "Couldn't generate an outfit right now — try again."` and returns.) |
| create_fit_card | Outfit input is missing or incomplete | Tool returns a descriptive **string** (not an exception): *"Can't write a fit card without an outfit suggestion."* This only triggers if called out of order; in the normal flow `suggest_outfit` always returns non-empty text, so it acts as a defensive guard. |

---

## Architecture

```
User query + wardrobe
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Planning Loop  (run_agent)                              ┌──────────────┐ │
│                                                         │   SESSION    │ │
│  1. parse query ─────────────────────────────────────► │ parsed{desc, │ │
│        │ {description, size, max_price}                 │  size, price}│ │
│        ▼                                                │              │ │
│  2. search_listings(description, size, max_price) ────► │ search_      │ │
│        │                                                │  results[]   │ │
│        ├─ results == []                                 │              │ │
│        │     └─► [ERROR] session.error =                │ error="No    │ │
│        │         "No listings matched… try raising      │  listings…"  │ │
│        │          price / dropping size / broader kw"   │              │ │
│        │         ──────────────► return session  ◄──────┼─ error path  │ │
│        │                                                │   exits here │ │
│        │ results == [item, …]                           │              │ │
│        ▼                                                │              │ │
│  3. select results[0] ────────────────────────────────►│ selected_    │ │
│        │                                                │  item        │ │
│        ▼                                                │              │ │
│  4. suggest_outfit(selected_item, wardrobe) ──────────► │ outfit_      │ │
│        │   (empty wardrobe → general advice, no exit)   │  suggestion  │ │
│        ▼                                                │              │ │
│  5. create_fit_card(outfit_suggestion, selected_item)─► │ fit_card     │ │
│        │                                                └──────────────┘ │
│        ▼                                                                  │
│     return session  (error == None on success)                           │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  Caller (CLI / Gradio) renders selected_item + outfit_suggestion + fit_card,
  or shows session.error
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

I'll use **Claude (Claude Code)** for all three tools, one at a time, giving it the matching tool spec from this doc plus the docstring TODO already in [tools.py](tools.py).

- **search_listings:** Input = the *Tool 1* block (the three params, the substring/relevance rules, the empty-list contract) + the listing field list from `load_listings()`. Expected output = a pure-Python function: hard-filter by `max_price` and case-insensitive substring `size`, score remaining listings by keyword overlap of `description` against `title`/`description`/`style_tags`, drop score-0, sort desc. **Verify before trusting:** confirm it filters by all three params and returns `[]` (not an error) on no match; then run 3 queries — a hit ("vintage graphic tee" under $30), a price-excluded query, and a no-match query ("designer ballgown size XXS under $5") — and check counts/order by hand.
- **suggest_outfit:** Input = the *Tool 2* block + the wardrobe schema from `data/wardrobe_schema.json`. Expected output = a function that branches on empty `wardrobe["items"]`, builds a prompt naming real pieces, calls Groq via `_get_groq_client()`, returns a non-empty string. **Verify:** run once with `get_example_wardrobe()` (must name owned pieces) and once with `get_empty_wardrobe()` (must give general advice, never `""`).
- **create_fit_card:** Input = the *Tool 3* block. Expected output = guards empty `outfit`, prompts at higher temperature, returns a 2–4 sentence caption mentioning item/price/platform once. **Verify:** call twice with the same input and confirm the captions differ; call with `outfit=""` and confirm it returns the guard string, not an exception.

**Milestone 4 — Planning loop and state management:**

I'll give **Claude** the *Planning Loop*, *State Management*, and *Architecture* (ASCII diagram) sections plus the `_new_session()` / `run_agent()` TODO in [agent.py](agent.py), and ask it to implement `run_agent` exactly as the numbered steps describe — including the query parser (Step 2) and the Branch-A early return on empty results. Expected output = a single-pass loop that writes each result into `session` and returns it. **Verify before trusting:** run the two cases already in `agent.py`'s `__main__` — the happy path (graphic tee) must populate `selected_item`/`outfit_suggestion`/`fit_card` with `error is None`, and the no-results path must set `error` and leave the downstream fields `None`. Confirm `suggest_outfit` is never reached when `search_results == []`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr needs to do (overview):** FitFindr is a secondhand-fashion shopping agent that finds a thrifted item matching the user's request, then styles it against their existing wardrobe. A user message describing what they want triggers `search_listings`; if it returns at least one listing the agent picks the top match and calls `suggest_outfit` with that item and the user's wardrobe, then passes the resulting look to `create_fit_card` to produce a shareable caption. If `search_listings` comes back empty the agent stops there and tells the user how to loosen their query — it never calls `suggest_outfit` with no item, and it skips styling when the wardrobe is empty.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Search:** The request triggers `search_listings(description="vintage graphic tee", size="M", max_price=30.0)`, which filters the listings loaded by `load_listings()` and returns the matches sorted by relevance (each result carries `id`, `title`, `price`, `condition`, `platform`, `style_tags`, etc.). The agent picks the top result — e.g. a faded vintage band tee at ~$22 on Depop.

**Step 2 — Suggest outfit:** With a listing in hand, the agent calls `suggest_outfit(new_item=<band tee>, wardrobe=get_example_wardrobe())`, pairing the tee against the user's actual closet (baggy jeans, chunky sneakers) and returning a styling suggestion — e.g. "Pair with your wide-leg jeans and chunky sneakers for a 90s grunge look; roll the sleeves once and tuck the front corner."

**Step 3 — Fit card:** The agent passes the styled look to `create_fit_card(outfit=<suggestion>, new_item=<band tee>)`, which returns a short, casual shareable caption — e.g. "thrifted this faded band tee off depop for $22 and it was made for my wide-legs 🖤 full look in my stories".

**Final output to user:** The user sees the chosen listing (title, price, platform, condition), the outfit suggestion built from their own wardrobe, and the ready-to-post fit card caption. **Error path:** if Step 1 returns no listings, the agent stops and suggests what to change (raise the price cap, drop the size filter, try broader keywords) instead of proceeding to Steps 2–3.
