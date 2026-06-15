#!/usr/bin/env bash
#
# demo_failures.sh — deliberately trigger each tool's failure mode and show
# that the agent recovers gracefully (a specific message, never an exception).
#
# Run from the project root:
#     bash demo_failures.sh
#
# Uses the project virtualenv if present, otherwise falls back to `python`.

set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python"

echo "═══════════════════════════════════════════════════════════════════"
echo " FAILURE 1 — search_listings returns ZERO results"
echo "═══════════════════════════════════════════════════════════════════"
echo "\$ search_listings('designer ballgown', size='XXS', max_price=5)"
$PY -c "from tools import search_listings; print(repr(search_listings('designer ballgown', size='XXS', max_price=5)))"
echo
echo "Full agent on the same impossible query:"
$PY -c "
from agent import run_agent
from utils.data_loader import get_example_wardrobe
s = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe())
print('  error   :', s['error'])
print('  fit_card :', s['fit_card'])
"

echo
echo "═══════════════════════════════════════════════════════════════════"
echo " FAILURE 2 — suggest_outfit with an EMPTY wardrobe"
echo "═══════════════════════════════════════════════════════════════════"
$PY -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
out = suggest_outfit(results[0], get_empty_wardrobe())
print('  type     :', type(out).__name__, '| non-empty:', bool(out.strip()))
print('  response :', out)
"

echo
echo "═══════════════════════════════════════════════════════════════════"
echo " FAILURE 3 — create_fit_card with an EMPTY outfit string"
echo "═══════════════════════════════════════════════════════════════════"
$PY -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
msg = create_fit_card('', results[0])
print('  type     :', type(msg).__name__)
print('  response :', msg)
"

echo
echo "All three failure modes handled gracefully — no exceptions raised. ✅"
