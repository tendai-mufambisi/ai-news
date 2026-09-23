# PROJECT: The Daily AI Brief — a personal AI intelligence system

## Who this is for
Me (Tendai — Digits Digital, Zimbabwe). This is NOT client work. It is a tool for one
reader: a software engineer building products for African SMEs, who wants to lead in
AI and tech rather than merely comment on it.

It is a sibling of `../vintage-news` (client work for Vintage Capital) and shares its
pipeline shape, but the two projects are separate: separate venv, separate git history,
separate rules. Do not edit one from the other.

## The point of it
Not "show me AI news". The goal is a 15-minute daily scan that keeps a deliberate
information diet, so reading does not turn into a treadmill of model-release headlines.

Six lanes, with fixed shares of a 12-story brief:

| Lane | Share | The question it answers |
|---|---|---|
| Agents & Coding | 30% | What can an agent now DO without a human? |
| Frontier Models | 20% | What capability just became possible? |
| Infrastructure | 15% | Compute, power, data centres — what did they cost? |
| Africa | 15% | What does this mean for Zimbabwe? |
| Security | 10% | What new attack or failure mode appears? |
| Business | 10% | Where is the money actually moving? |

The diet IS the product. A quiet day in agent-land must not be filled with model-release
noise, and Africa must never be crowded out by Silicon Valley. If a change would let one
lane dominate, it is wrong even if it surfaces "better" stories.

## Hard rules (do not violate)
1. COPYRIGHT: never reproduce article text. A brief entry is an ORIGINAL summary plus a
   link to the source. Same rule as the Vintage build, for the same reason.
2. ACCURACY: never invent facts, figures, dates or sources. Thin feed data means a thin
   summary, not an invented one.
3. SECRETS: the Gemini key lives in .env, gitignored. Never hardcoded, printed or committed.
4. FEEDS ARE PROBED, NOT GUESSED: a feed enters feeds.py only after it returns HTTP 200
   AND is shown to carry recent items. A feed can answer 200 with year-old articles
   (SemiAnalysis does); check item dates. If a site advertises no feed, read its <head>
   before concluding that — Mistral's feed was at an unadvertised path.
5. NO SCRAPING: Anthropic and Meta AI publish no RSS. That is a documented gap, not a
   problem to route around with HTML scraping.

## Tech stack
- Windows, Python 3, venv at `aienv/` (NOT vintage-news's `vintageenv/`)
- Phase 1 needs only `feedparser`. Gemini + Jinja get added when their phase does.
- Gemini: `google-genai` SDK (not the deprecated google-generativeai), gemini-2.5-flash
  or a free-tier-eligible Gemini 3 flash model — check, do not assume.

## Files
- `feeds.py`   — 38 probed feeds, their lanes and tiers, plus LANE_KEYWORDS
- `run.py`     — fetch → filter → classify → quota-balance → print
- `aienv/`     — the virtualenv
- Later: `summarise.py`, `render.py`, `template.html`, `index.html`

## Architecture (keep it boring)
Local-first, one command: `python run.py`.
Fail gracefully — a dead feed logs a line and the run continues. One bad source must
never take down the morning brief.

## Phases
- **Phase 1 — FETCH (done)**: feeds.py + fetch/filter/lane-ranking, printed to terminal.
- **Phase 2 — SUMMARISE (next)**: Gemini, strict JSON. For each story: an original
  2-sentence summary AND a one-line "why this matters to you", written against the lane's
  question. This is the step that should also gate relevance — see the open question below.
- **Phase 3 — RENDER**: a clean HTML page, grouped by lane, that opens in one keystroke
  each morning.

## Open question, carried into Phase 2
The Africa lane fills from general African tech feeds (TechCabal, Technext, ITWeb…), which
publish far more fintech and telecoms news than AI news. On a typical day the lane fills
with good stories that are not AI stories. Two options, not yet decided:
  (a) require an AI signal in the Africa lane — sharper, but the lane will often be empty;
  (b) let Gemini judge relevance in Phase 2 and drop the misses — better judgement, costs
      API calls on stories that get thrown away.
Do not pick one silently.

## HOW TO WORK WITH ME
Build in phases and STOP after each one for me to verify. Explain what you did in plain
terms afterwards — I am learning, not just shipping. Do not scaffold every phase at once.
