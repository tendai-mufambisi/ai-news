"""
Gemini summarisation for the Daily AI Brief.

PHASE 2 of 3.

The model is allowed to write PROSE and to make one JUDGEMENT. Nothing else.
Headlines, sources and links are carried through from the RSS feed untouched,
because a model asked to repeat a URL will eventually invent one, and a brief
that links somewhere that does not exist is worse than no brief.

Each story comes back with three things:

    summary    two original sentences: what happened
    why        one line: why it matters, answering THIS LANE'S question
    relevant   the judgement - is this worth your time at all?

The "why" line is the reason this project exists. A summary tells you what
happened, which a headline mostly already did. The why-line is the
interpretation step, and interpretation is the thing you cannot outsource to
a newsletter - it is what you would actually say about the story to a room.

The "relevant" flag is what a keyword filter could not do. Two problems it
solves, both found in real runs:

  * The Africa lane fills from general African tech feeds, which publish far
    more fintech and telecoms than AI. "Is this an AI story that matters to a
    builder in Zimbabwe?" is a judgement call, not a keyword test.
  * Vendor blogs publish customer case studies that read exactly like
    engineering posts. "How BMW Group detects cost anomalies" beat the
    marketing regex in run.py; it does not beat being asked directly whether
    the piece explains a mechanism or announces a happy customer.
"""

import logging
import os
import pathlib
import time

from pydantic import BaseModel, Field

from feeds import LANE_INTENT

# The SDK logs an "automatic function calling" advisory on every call. We pass
# no tools, so it does not apply to us and only clutters the morning log.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

# gemini-2.5-flash is 404 for newly issued API keys ("no longer available to
# new users"), which the Vintage build discovered the hard way - so the 2.5
# default is not an option here either. The Gemini 3 flash models all answer
# on the free tier. Pinned to exact versions, not a "-latest" alias, so the
# output does not change under us without warning.
#
# Free-tier models return 503 "high demand" fairly often. We try each in turn
# with a short backoff before giving up.
MODELS = ("gemini-3.8-flash", "gemini-3-flash-preview", "gemini-3.5-flash")
MODEL = MODELS[0]

ATTEMPTS_PER_MODEL = 2
BACKOFF_SECONDS = 5

# Worth retrying (server busy or rate-limited); anything else is a real fault
# and retrying it just wastes quota - which matters here, because this key is
# shared with the Vintage Capital pipeline.
RETRY_CODES = (429, 500, 502, 503, 504)

# Low temperature: this is a factual summarising job, not a creative one.
TEMPERATURE = 0.2

# How much of the feed blurb the model may read. Enough for context, short
# enough to keep one batched request comfortably inside the free tier.
BLURB_CHARS = 700


class Brief(BaseModel):
    """One story as Gemini must return it."""

    id: int = Field(description="The id of the source item, copied exactly.")
    relevant: bool = Field(
        description="True only if this story teaches something about AI capability, "
        "cost, mechanism or consequence. False for vendor case studies, event "
        "notices, and stories with no AI or frontier-technology content."
    )
    summary: str = Field(description="Exactly two original sentences: what happened.")
    why: str = Field(description="One sentence answering this item's 'question' field.")


class BriefBatch(BaseModel):
    briefs: list[Brief]


PROMPT = """You are preparing a daily AI intelligence brief for one reader: a software \
engineer in Zimbabwe who builds products for African SMEs. He is working toward being \
able to explain AI on a conference stage, to technical people and to the general public.

That goal decides what is useful to him. He does not need to know THAT a product \
shipped. He needs to understand WHAT CHANGED, what it now costs, and what it makes \
possible that was not possible before. A story he cannot say anything interesting \
about is a story he should not have read.

Below are {count} news items. Each has a LANE and that lane's QUESTION. For EACH item \
return a relevance judgement, a summary, and a why-line.

RULES - these are requirements, not style preferences:

1. RELEVANCE. Set relevant=false if the item is any of these:
   - a vendor customer story or case study ("How <company> did <thing> with <product>")
   - an event notice, meetup, webinar, awards or conference announcement
   - a funding, fintech, telecoms or general business story with no AI, compute or
     frontier-technology substance
   - an item so thin you cannot tell what actually happened
   Set relevant=true when it teaches something real about capability, cost, a mechanism,
   a failure mode, or a consequence. BE STRICT. Dropping a weak story costs nothing;
   a brief padded with noise defeats its whole purpose. Still return summary and why
   for items you mark false - just keep them short.

2. ORIGINAL WORDING. Write it yourself, in your own words. Do NOT copy or lightly
reword sentences from the supplied text, and never quote it. If a sentence of yours
would share more than four consecutive words with the source text, rewrite it.

3. SUMMARY: EXACTLY TWO SENTENCES. Plain English. No bullets, no headings. Do not
begin with "This article", "The piece" or "According to".

4. NEVER INVENT ANYTHING. Use only facts present in the item you are given. Do not add
figures, dates, percentages, version numbers, company names or background from your own
knowledge, even when you are confident it is correct. If the item is thin, write a
shorter and vaguer summary - that is the correct outcome, not a failure.

5. WHY: ONE SENTENCE, answering that item's QUESTION directly. This is the most
important field. Write what he could actually SAY about this story - the shift, the
cost change, the new possibility, the risk. Not a restatement of the summary.
   Weak:   "This is important for AI development."
   Strong: "Inference dropping by half is what moves an AI feature from something an
            SME cannot justify to something you can put in a R200/month product."
If the honest answer is that it changes little, say so plainly.

6. NO HYPE. Never "exciting", "game-changing", "revolutionary", "poised to". Write the
way a good engineer explains something to another engineer.

7. FIGURES IN NUMERALS, as they appeared in the source: "$10 billion", "50%", "1.1%".
Never spell a figure out in words.

Return the id of every item exactly as it was given to you.

ITEMS:
{items}"""


def load_env(path=None):
    """
    Read KEY=VALUE lines out of .env into the environment.

    Hand-rolled rather than adding python-dotenv - one less dependency for
    four lines of parsing. Never prints or logs the value.

    Resolved relative to THIS file, not the working directory, so the brief
    still finds its key when run from somewhere else (a scheduled task, or a
    shortcut, which is how this will eventually run every morning).
    """
    env_file = pathlib.Path(path) if path else pathlib.Path(__file__).with_name(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_client():
    """Build the Gemini client, or explain clearly what is missing."""
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("  [fail] GEMINI_API_KEY not found in .env - cannot summarise.")
        return None
    try:
        from google import genai

        return genai.Client(api_key=key)
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all
        print(f"  [fail] could not start Gemini client: {exc}")
        return None


def build_items_block(items):
    """
    Render the shortlist into the numbered block the prompt expects.

    Each item carries its lane's question, so the model answers the right one
    per story rather than a single generic "why does this matter".
    """
    chunks = []
    for i, item in enumerate(items):
        blurb = (item["blurb"] or "")[:BLURB_CHARS]
        chunks.append(
            f"--- id: {i}\n"
            f"lane: {item['lane']}\n"
            f"question: {LANE_INTENT[item['lane']]}\n"
            f"headline: {item['title']}\n"
            f"publisher: {item['source']}\n"
            f"text: {blurb or '(no description supplied)'}"
        )
    return "\n\n".join(chunks)


def is_retryable(exc):
    """True if the error looks like a busy server rather than a broken request."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in RETRY_CODES:
        return True
    return any(str(c) in str(exc) for c in RETRY_CODES)


def call_gemini(client, items, model):
    """
    One request for the whole shortlist, with the schema enforced by the API.

    response_schema makes the model return JSON matching BriefBatch - we are
    not scraping JSON out of prose with a regex and hoping for the best.
    """
    from google.genai import types

    prompt = PROMPT.format(count=len(items), items=build_items_block(items))

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=TEMPERATURE,
            response_mime_type="application/json",
            response_schema=BriefBatch,
        ),
    )
    return BriefBatch.model_validate_json(response.text)


def call_with_fallback(client, items):
    """
    Try each model in turn, retrying the ones that fail for temporary reasons.

    Returns the batch, or None once every option is exhausted. A hard error
    (bad key, bad request) aborts immediately instead of burning through the
    whole chain - and through quota the Vintage pipeline also needs.
    """
    for model in MODELS:
        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                batch = call_gemini(client, items, model)
                if model != MODEL:
                    print(f"  [note] fell back to {model}")
                return batch
            except Exception as exc:  # noqa: BLE001 - deliberate catch-all
                label = f"{type(exc).__name__}"
                if not is_retryable(exc):
                    print(f"  [fail] {model}: {label}: {str(exc)[:160]}")
                    return None
                print(f"  [busy] {model} attempt {attempt}/{ATTEMPTS_PER_MODEL}: {label}")
                if attempt < ATTEMPTS_PER_MODEL:
                    time.sleep(BACKOFF_SECONDS * attempt)

    print("  [fail] every model was busy - try again in a few minutes.")
    return None


def summarise(items):
    """
    Attach a summary, a why-line and a relevance verdict to each candidate.

    Returns (kept, dropped). Items the model judged irrelevant go in dropped,
    and are reported rather than silently discarded: if the gate starts
    throwing away things you wanted, you need to be able to SEE that, or the
    brief quietly becomes narrower than you asked for.

    Items the model skipped or mangled are dropped with a log line rather than
    published half-finished. A missing story is fine; a wrong one is not.
    """
    if not items:
        return [], []

    client = get_client()
    if client is None:
        return [], []

    print(f"\nSummarising {len(items)} candidates with {MODEL}...")

    batch = call_with_fallback(client, items)
    if batch is None:
        return [], []

    by_id = {brief.id: brief for brief in batch.briefs}

    kept, dropped = [], []
    for i, item in enumerate(items):
        brief = by_id.get(i)
        if brief is None:
            print(f"  [skip] nothing returned for: {item['title'][:60]}")
            continue

        summary = " ".join(brief.summary.split())
        why = " ".join(brief.why.split())
        if not summary:
            print(f"  [skip] empty summary for: {item['title'][:60]}")
            continue

        # Everything except these fields stays exactly as the feed gave it.
        item["summary"] = summary
        item["why"] = why
        (kept if brief.relevant else dropped).append(item)

    print(f"  [ok]   {len(kept)} relevant, {len(dropped)} dropped as not worth reading")
    return kept, dropped
