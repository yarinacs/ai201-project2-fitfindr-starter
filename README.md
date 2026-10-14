# FitFindr 🛍️

FitFindr is a secondhand-fashion shopping agent. You describe what you're looking
for in plain language; it finds a matching thrifted listing, styles it against your
existing wardrobe, and writes a shareable "fit card" caption for the find.

It's a three-tool agent driven by a planning loop that **branches on what the search
returns** — a real find leads to styling and a caption, while an empty search stops
early with actionable advice instead of fabricating an outfit.

---

## Setup

```bash
# from the project root
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)). The file is already in `.gitignore` —
never commit it.

```
GROQ_API_KEY=your_key_here
```

## Running

```bash
python app.py          # launches the Gradio UI (default http://localhost:7860)
python agent.py        # runs the two CLI test cases (happy path + no-results)
pytest tests/          # runs the tool test suite
bash demo_failures.sh  # triggers all three failure modes (for the demo)
```

Open the URL printed in your terminal. A happy-path query (e.g. *"vintage graphic
tee under $30"*) populates all three panels: the top listing, an outfit idea, and a
fit card.

---

## Tool Inventory

### 1. `search_listings(description, size, max_price) -> list[dict]`
**Purpose:** Find listings in the mock dataset that match the user's request. Pure
local filtering and ranking — no LLM call.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `description` | `str` | Keywords describing the wanted item (e.g. `"vintage graphic tee"`). Used for relevance scoring. |
| `size` | `str \| None` | Size to filter by, or `None` to skip. Case-insensitive **substring** match (so `"M"` matches the free-form size `"S/M"`). |
| `max_price` | `float \| None` | Inclusive price ceiling, or `None` to skip. |

**Output:** a `list[dict]` of full listing dicts (`id`, `title`, `description`,
`category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`,
`platform`), sorted by relevance (most keyword overlap first). Returns `[]` when
nothing matches — never raises.

### 2. `suggest_outfit(new_item, wardrobe) -> str`
**Purpose:** Style the found item against the user's wardrobe. Calls the Groq LLM.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `new_item` | `dict` | The selected listing dict from `search_listings`. |
| `wardrobe` | `dict` | `{"items": [ {id, name, category, colors, style_tags, notes}, ... ]}`. May be empty. |

**Output:** a non-empty `str` of styling text. With a populated wardrobe it names
specific owned pieces; with an empty wardrobe it returns general styling advice.

### 3. `create_fit_card(outfit, new_item) -> str`
**Purpose:** Turn the outfit into a short, casual social-media caption. Calls the
Groq LLM at high temperature so captions vary across runs.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `outfit` | `str` | The styling text from `suggest_outfit`. |
| `new_item` | `dict` | The selected listing dict (its title, price, platform appear in the caption). |

**Output:** a 2–4 sentence caption `str` mentioning the item, price, and platform
once each. If `outfit` is empty, returns a descriptive error string instead.

Both LLM tools use Groq's `llama-3.3-70b-versatile`.

---

## Planning Loop — what the agent decides

The loop (`run_agent` in `agent.py`) is a fixed pipeline with **one decision point**.
It does not free-choose tools; the order is `parse → search → select → suggest →
caption`, and the search result decides whether the pipeline continues.

1. **Initialize** a `session` dict (the single source of truth for the interaction).
2. **Parse** the natural-language query into `{description, size, max_price}` using
   deterministic regex (`_parse_query`): a number after `$`/`under`/`below` becomes
   `max_price`; a size token (`M`, `XL`, or `size 8`) becomes `size`; those phrases
   are stripped from the remaining `description`. *(I chose regex over an LLM parse
   so the search inputs are deterministic and testable.)*
3. **Search** with the parsed parameters.
   - **Decision:** `if not search_results:` → set `session["error"]` with a helpful
     message and **return immediately**. The agent does **not** call `suggest_outfit`
     with empty input.
   - Otherwise continue.
4. **Select** `search_results[0]` (top-ranked) as `selected_item`.
5. **Suggest outfit** for the selected item + wardrobe. (An empty wardrobe is handled
   *inside* the tool, so no branch is needed here.)
6. **Create fit card** from the outfit suggestion + selected item.
7. **Return** the session (`error` stays `None` on success).

This is why the agent behaves differently for different inputs: an impossible query
exits at step 3 with two `None` outputs and an error, while a real query runs all
three tools.

---

## State Management

All state lives in one `session` dict created by `_new_session()`. Tools never read
each other's return values directly — each step **writes its result into `session`**,
and the next step reads from there:

```
query ──► parsed{description,size,max_price} ──► search_results[]
search_results[0] ──► selected_item
selected_item + wardrobe ──► outfit_suggestion
outfit_suggestion + selected_item ──► fit_card
error: None  (set only if an early-exit branch fires)
```

Scope is one `run_agent` call — no cross-session memory. The caller (the Gradio
`handle_query` or the CLI) reads the finished session and renders `selected_item`,
`outfit_suggestion`, and `fit_card`, or shows `error`.

State passing is verifiable: instrumenting the tools shows the *exact same object*
flows through — `selected_item is` the dict passed into both `suggest_outfit` and
`create_fit_card`, and `outfit_suggestion is` the string passed into `create_fit_card`
(all identity `is` checks return `True`). Nothing is re-prompted or hardcoded between
steps.

---

## Error Handling

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | No listing matches | Returns `[]`. The loop sets `error` and stops before styling. |
| `suggest_outfit` | Empty wardrobe | Returns general styling advice (not a crash, not `""`); flow continues. |
| `create_fit_card` | Empty/missing outfit | Returns a descriptive error string; no LLM call, no exception. |

**Concrete example from testing** (full transcript in
[`docs/error_handling_demo.md`](docs/error_handling_demo.md), reproducible with
`bash demo_failures.sh`):

Query: `"designer ballgown size XXS under $5"`

```
error    : No listings matched "designer ballgown size XXS under $5". Try raising
           your price cap, dropping the size filter, or using broader keywords.
fit_card : None
```

A spy confirmed `suggest_outfit` was **never called** on this path. The message
names the exact failed query and offers three concrete levers — not just
"no results found."

---

## AI Usage

I used **Claude (via Claude Code)** to help implement and verify the project. Two
specific instances:

**1. Implementing `search_listings`.**
- *Input:* the Tool 1 spec block from `planning.md` (the three parameters with types,
  the case-insensitive substring rule for size, the keyword-relevance ranking, and the
  "return `[]`, never raise" contract) plus the field list from `load_listings()`.
- *Produced:* a function that hard-filters on price and size, then scores listings by
  keyword overlap and sorts descending.
- *What I changed:* the first version did exact size matching (`listing["size"] == size`),
  which missed free-form sizes like `"S/M"` and `"XL (oversized)"`. I overrode it to a
  case-insensitive substring match, matching the rule I'd written in my spec, and added
  a test (`test_search_size_filter_substring`) to lock that behavior in.

**2. Implementing the planning loop (`run_agent`).**
- *Input:* the Planning Loop + State Management sections and the ASCII architecture
  diagram from `planning.md`, plus the `_new_session`/`run_agent` TODO stub in `agent.py`.
- *Produced:* the numbered pipeline with the empty-results early-return branch.
- *What I verified/changed:* I checked it branched on the search result rather than
  calling all three tools unconditionally, then confirmed with instrumented spies that
  the *same objects* pass through the session (identity checks) and that `suggest_outfit`
  is skipped on the no-results path before trusting it.

---

## Spec Reflection


> - The free-form `size` field (`"S/M"`, `"W30 L30"`, `"XL (oversized)"`) was the
>   biggest spec gap — my original plan said "filter by size" without defining *how*,
>   and exact matching silently dropped valid results. Defining substring matching in
>   the spec first would have caught it earlier.
> - Writing the Planning Loop section as explicit numbered branches (not "it decides
>   what to call next") made the implementation almost mechanical and made the
>   "different behavior for different inputs" requirement easy to satisfy.
> - `brand` can be `None`, which the spec noted; handling it up front avoided a display
>   bug in the Gradio listing panel.

---

## Project Layout

```
ai201-project2-fitfindr-starter/
├── agent.py                  # run_agent planning loop + query parser
├── tools.py                  # the three tools
├── app.py                    # Gradio UI + handle_query
├── planning.md               # design doc (tools, loop, state, diagram, AI plan)
├── demo_failures.sh          # triggers all three failure modes
├── docs/error_handling_demo.md
├── tests/test_tools.py       # pytest suite
├── data/                     # listings.json, wardrobe_schema.json
└── utils/data_loader.py      # load_listings, get_example/empty_wardrobe
```
