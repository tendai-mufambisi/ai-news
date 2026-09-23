"""
The Daily AI Brief
==================

Run with:  python run.py

    fetch (RSS)      feeds.py       40 AI, engineering, Africa and security feeds
    -> filter        here           last 48h, dedupe, lane-rank, pool of 26
    -> summarise     summarise.py   Gemini: summary, why-line, relevance
    -> balance       here           survivors back down to a brief of 12
    -> render        render.py      index.html
    -> print         here           the same brief, in the terminal

WHY THE SELECTION WORKS THE WAY IT DOES
---------------------------------------
This is not "the 12 newest AI stories". Sorting by recency alone gives you
whatever the fastest-publishing outlet posted this morning, which is how a
reading habit turns into a treadmill.

Instead every story is placed in one of six LANES and the lanes get fixed
shares of the page - the information diet, enforced in code:

    Agents & Coding  30%    Frontier Models  20%
    Infrastructure   15%    Africa           15%
    Security         10%    Business         10%

So a quiet day in agent-land does not get filled up with model-release noise,
and Africa cannot be crowded out by Silicon Valley on a busy day. The diet is
the product. Change LANE_SHARE if the diet should change.
"""

import html
import re
import socket
import sys
from datetime import datetime, timedelta, timezone

import feedparser

from feeds import ANALYSIS, FEEDS, LANE_INTENT, LANE_KEYWORDS, PRIMARY, REPORTING
from render import render
from summarise import summarise

# --- Tunables -----------------------------------------------------------
LOOKBACK_HOURS = 48      # how far back an item may be published
MAX_ITEMS = 12           # the size of one morning's brief
MAX_PER_SOURCE = 2       # no single publisher may take more slots than this

# How many candidates go to Gemini, against a finished brief of 12.
#
# The relevance gate in Phase 2 throws stories away, and a story thrown away
# must not leave a hole in the brief - so we over-select by half and let the
# gate cut it back down. It is one batched call either way, so the extra six
# cost a few hundred tokens rather than another request.
#
# Set to 26 after the first live run: the gate rejected half of an 18-item
# pool, which left a 9-story brief with an empty Business lane. The gate is
# stricter than a keyword filter and the pool has to be sized for that.
SUMMARISE_POOL = 26

# 48h, not the 24h the Vintage build uses. AI news is bursty: a quiet Tuesday
# and a forty-story Thursday. A 24h window gives you a thin brief half the week
# and throws away Wednesday's best story because you read it on Thursday.
# De-duplication, not the clock, is what stops repeats.

# The information diet, as percentages. They must sum to 100.
LANE_SHARE = {
    "Agents & Coding": 30,
    "Frontier Models": 20,
    "Infrastructure":  15,
    "Africa":          15,
    "Security":        10,
    "Business":        10,
}

FEED_TIMEOUT = 25        # seconds before we give up on a single feed
USER_AGENT = "Mozilla/5.0 (compatible; DailyAIBrief/1.0)"
# Only used to retry a feed that answered 403/429 to the honest string above.
BROWSER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

socket.setdefaulttimeout(FEED_TIMEOUT)

# Windows terminals default to cp1252 and mangle the curly quotes, em dashes
# and emoji that come out of these feeds. Force UTF-8 so headlines print clean.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


# --- Small helpers ------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(raw):
    """Strip HTML tags and entities out of a feed field and tidy whitespace."""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", str(raw))
    text = html.unescape(text)
    # Feeds sometimes double-encode, so unescape once more if it still looks encoded.
    if "&" in text and ";" in text:
        text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def dedupe_key(title):
    """Normalised headline used to spot the same story syndicated twice."""
    key = re.sub(r"[^a-z0-9 ]", "", title.lower())
    return _WS_RE.sub(" ", key).strip()


def published_at(entry):
    """Return the entry's publish time as an aware UTC datetime, or None."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def strip_source_prefix(title, source):
    """
    Drop a leading "TechCrunch | " style publisher tag from a headline.

    The brief already says where each story came from, so the tag is pure
    duplication. Only a prefix matching the publisher's own name is removed -
    never a byline or a "Sponsored:" tag, which are part of the headline as
    the publisher wrote it.
    """
    pattern = rf"^{re.escape(source)}(?:\s+\w+)?\s*[|:]\s*"
    return re.sub(pattern, "", title, count=1, flags=re.IGNORECASE).strip()


# --- Lane classification ------------------------------------------------
#
# Three matching rules, strictest to loosest (see LANE_KEYWORDS in feeds.py):
#
#   "gpu", "llm"  1-3 letters: whole word only, or "ai" hits aim/air/aid.
#   "agent"       normal words: the word plus ordinary English endings, but
#                 NOT a longer word that merely starts the same way.
#   "infer*"      explicit stems marked with *: any continuation.
#
# These rules are carried over from the Vintage build, where each one exists
# because of a real misfire: raw substrings tagged "Lagos" as gas; open
# prefixes then tagged "team" as tea.
_SHORT = 3
_ENDINGS = r"(?:s|es|d|ed|r|er|rs|ers|ing)?"


def _pattern(words):
    stems = [w[:-1] for w in words if w.endswith("*")]
    plain = [w for w in words if not w.endswith("*")]
    exact = [w for w in plain if len(w) <= _SHORT]
    normal = [w for w in plain if len(w) > _SHORT]

    alt = lambda ws: "|".join(re.escape(w) for w in ws)
    parts = []
    if stems:
        parts.append(rf"\b(?:{alt(stems)})\w*")
    if normal:
        parts.append(rf"\b(?:{alt(normal)}){_ENDINGS}\b")
    if exact:
        parts.append(rf"\b(?:{alt(exact)})\b")
    return re.compile("|".join(parts), re.IGNORECASE)


_LANE_PATTERNS = {lane: _pattern(words) for lane, words in LANE_KEYWORDS.items()}

TITLE_WEIGHT = 3        # a lane named in the headline is what the story is about
BLURB_WEIGHT = 1        # a mention in the standfirst is weaker evidence
BLURB_SCAN_CHARS = 300  # some feeds ship the whole article; only read the opening
HOME_LANE_BONUS = 1     # a lane confirming its own feed's beat

# What a source is worth, given that the point of this brief is to be able to
# explain AI to a room. See the tier comment in feeds.py.
TIER_BONUS = {ANALYSIS: 2, PRIMARY: 1, REPORTING: 0}

# Vendor marketing, which reads exactly like news and is worth nothing here.
#
# The first two runs of this brief handed over "How Reactiv automates mobile
# commerce 80% faster with Amazon Bedrock AgentCore" and "At AI Day Singapore,
# NVIDIA and Partners Showcase AI Advancements Across Southeast Asia". Both
# scored well. Both are press releases. Neither gives you a single thing you
# could say on a stage, because neither explains a mechanism - they announce
# that a customer is happy and that an event happened.
#
# This is a PENALTY, not a filter, and the distinction matters: vendor blogs
# also publish genuinely good engineering writing, and a hard block would lose
# it. A penalised story can still make the brief on a quiet day, it just has
# to beat real analysis to get there.
#
# Each pattern below comes from a headline this brief actually surfaced or
# that its feeds publish weekly. Add to it when a press release slips through;
# do not try to guess the patterns in advance.
MARKETING_PATTERNS = [
    r"^how [\w .'-]{2,40}\b(?:automat|accelerat|scal|buil[dt]|reduc|improv|transform|cut|boost|sav|power|secur|deploy|migrat|modernis|moderniz|optimis|optimiz|unlock|enabl|streamlin|deliver)\w*\b.*\bwith\b",
    # Event and meetup notices. Useful to Willison's readers, useless to a
    # brief - a talk being scheduled is not a capability changing.
    r"\bbirds of a feather\b", r"\bmeetup\b", r"\bworkshop\b",
    r"\bspeaking at\b", r"\bi(?:'ll| will) be at\b", r"\bsee you (?:at|in)\b",
    r"^\w{2,12} \w+ \d{1,2}(?:st|nd|rd|th)?\s*[:-]",
    r"\bshowcase\w*\b", r"\bspotlight\b", r"\bcelebrat\w*\b",
    r"\bpartners? (?:with|to)\b", r"\bin partnership with\b",
    r"\bnow (?:generally )?available\b", r"\bnow supports?\b",
    r"\bcustomer stor\w+\b", r"\bcase stud\w+\b", r"\bsuccess stor\w+\b",
    r"\bwebinar\b", r"\bregister (?:now|today)\b", r"\bjoin us\b",
    r"\baward\w*\b", r"\brecogni[sz]ed\b", r"\bnamed a leader\b",
    r"\bsponsored\b", r"\bwhy .{0,30}choose\b",
    r"\bat [A-Z]\w+ (?:Day|Summit|Conference|Expo|World|Connect)\b",
]
_MARKETING_RE = re.compile("|".join(MARKETING_PATTERNS), re.IGNORECASE)

# Deliberately heavy: enough to sink a vendor post below any real story, not
# so heavy that it can never appear. A press release scoring 5 lands on 2.
MARKETING_PENALTY = 3

# A story must reach this to make the brief. 3 = named its lane in the
# headline, or 2 = a primary source that named it in the standfirst. Below
# that you are reading keyword coincidence.
MIN_SCORE = 3


def classify(item):
    """
    Work out which lane a story belongs to and how strongly.

    Returns (lane, lanes, score). This only RANKS and SORTS stories we already
    fetched - it never changes their wording.

    The score is the STRONGEST single lane, not the sum across lanes. A total
    rewards breadth, so a headline brushing three lanes would beat a focused
    story on one. What matters is whether a story is squarely about a lane,
    not how many it grazes.

        4  lane in the headline, confirmed in the standfirst
        3  lane in the headline
        1  lane only in the standfirst
        +2 the source explains mechanisms (ANALYSIS), +1 if it shipped it
        +1 the lane agrees with the feed's own beat
        -3 the headline reads as vendor marketing

    That last bonus is why "NVIDIA announces Q3 earnings" lands in
    Infrastructure rather than Business: both lanes match, and NVIDIA's feed
    breaks the tie toward the one it actually covers.
    """
    head = item["title"]
    body = (item["blurb"] or "")[:BLURB_SCAN_CHARS]

    scored = []
    for lane, pattern in _LANE_PATTERNS.items():
        weight = 0
        if pattern.search(head):
            weight += TITLE_WEIGHT
        if pattern.search(body):
            weight += BLURB_WEIGHT
        if weight:
            if lane == item["home_lane"]:
                weight += HOME_LANE_BONUS
            scored.append((weight, lane))

    scored.sort(reverse=True)
    lanes = [lane for _, lane in scored]
    score = scored[0][0] if scored else 0
    if score:
        score += TIER_BONUS[item["tier"]]
        if _MARKETING_RE.search(head):
            item["marketing"] = True
            score -= MARKETING_PENALTY

    # Nothing matched: fall back to the lane its publisher normally covers.
    # The story keeps its zero score, so it only reaches the brief on a day
    # too thin to fill from properly-matched stories.
    lane = lanes[0] if lanes else item["home_lane"]
    return lane, lanes, score


# --- Step 1: fetch ------------------------------------------------------

def fetch_feed(feed):
    """
    Pull one feed. Never raises: a dead source logs a line and returns [].
    One bad feed must not take the morning run down with it.
    """
    try:
        parsed = feedparser.parse(feed["url"], agent=USER_AGENT)
    except Exception as exc:                      # noqa: BLE001 - deliberate catch-all
        print(f"  [skip] {feed['name']}: could not reach feed ({exc})")
        return []

    status = getattr(parsed, "status", None)

    # Some publishers block unfamiliar user-agents rather than being down.
    # Techpoint Africa answered 200 when probed and 403 on the first real run,
    # which is a bot filter, not a dead feed. One retry with a browser string
    # is an honest thing to do for a personal reader fetching a public feed
    # once a day - it is not an attempt to get at anything not freely offered.
    # If it still refuses, we take the no and move on.
    if status in (403, 429):
        try:
            parsed = feedparser.parse(feed["url"], agent=BROWSER_AGENT)
            status = getattr(parsed, "status", None)
        except Exception:                         # noqa: BLE001
            pass

    if status and status >= 400:
        print(f"  [skip] {feed['name']}: HTTP {status}")
        return []
    if not parsed.entries:
        print(f"  [skip] {feed['name']}: no entries returned")
        return []

    items = []
    for entry in parsed.entries:
        title = strip_source_prefix(clean_text(entry.get("title")), feed["name"])
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "blurb": clean_text(entry.get("summary") or entry.get("description")),
                "source": feed["name"],
                "home_lane": feed["lane"],
                "tier": feed["tier"],
                "marketing": False,
                "published": published_at(entry),
            }
        )

    print(f"  [ok]   {feed['name']}: {len(items)} items")
    return items


def fetch_all():
    print(f"Fetching {len(FEEDS)} feeds...")
    everything = []
    for feed in FEEDS:
        everything.extend(fetch_feed(feed))
    return everything


# --- Step 2: filter and balance -----------------------------------------

def quotas(total=MAX_ITEMS, shares=LANE_SHARE):
    """
    Turn the diet percentages into whole slots, using largest remainder.

    With 12 slots the shares come out 4/2/2/2/1/1. Rounding each share on its
    own would lose or gain a slot; largest remainder hands the leftovers to
    the lanes with the biggest fractions, so the slots always sum to total.
    """
    exact = {lane: total * pct / 100 for lane, pct in shares.items()}
    whole = {lane: int(value) for lane, value in exact.items()}
    left = total - sum(whole.values())
    order = sorted(exact, key=lambda l: (exact[l] - whole[l], shares[l]), reverse=True)
    for lane in order[:left]:
        whole[lane] += 1
    return whole


def balance(ranked, max_items=MAX_ITEMS, per_source=MAX_PER_SOURCE):
    """
    Fill the brief lane by lane, to the diet's quotas.

    Two passes:

      1. Each lane takes its best stories up to its quota, skipping any
         publisher already holding per_source slots.
      2. Lanes that could not fill their quota (a genuinely quiet day for
         Mistral and friends) release their slots, and the remaining lanes
         take turns claiming them, richest share first.

    So the diet is a target, not a straitjacket: it shapes a normal day and
    gets out of the way on an odd one. Within a lane, merit order is never
    touched - the quota decides HOW MANY, never WHICH.

    The publisher cap is SOFT, for the same reason as in the Vintage build:
    when every remaining story belongs to a publisher already at the cap, the
    cap rises by one and the rotation goes round again. Nine stories with
    thirty eligible ones unused is the worse outcome.
    """
    queues = {lane: [] for lane in LANE_SHARE}
    for item in ranked:
        queues[item["lane"]].append(item)

    quota = quotas(max_items)
    picked, per_pub, in_lane = [], {}, set()

    def take(lane, cap):
        """Claim this lane's best remaining story, or return False."""
        for pos, item in enumerate(queues[lane]):
            # Never the same publisher twice in one lane. The global cap of 2
            # is not enough protection here: Infrastructure has only two slots,
            # so a cap of 2 let NVIDIA take the whole lane - twice, on two
            # consecutive runs. A lane filled by one vendor is that vendor's
            # newsletter, not a brief. A publisher may still appear in two
            # DIFFERENT lanes, which is breadth rather than domination.
            if (lane, item["source"]) in in_lane:
                continue
            if per_pub.get(item["source"], 0) < cap:
                picked.append(queues[lane].pop(pos))
                per_pub[item["source"]] = per_pub.get(item["source"], 0) + 1
                in_lane.add((lane, item["source"]))
                return True
        return False

    # Pass 1 - every lane fills its own quota.
    for lane, slots in quota.items():
        for _ in range(slots):
            if not take(lane, per_source):
                break

    # Pass 2 - redistribute whatever pass 1 could not place.
    order = sorted(LANE_SHARE, key=LANE_SHARE.get, reverse=True)
    cap = per_source
    while len(picked) < max_items and any(queues.values()):
        progressed = False
        for lane in order:
            if len(picked) == max_items:
                break
            if take(lane, cap):
                progressed = True
        if not progressed:
            cap += 1

    return picked


def select_items(items, lookback_hours=LOOKBACK_HOURS, max_items=MAX_ITEMS):
    """
    Narrow the raw pile down to one morning's brief:
      1. published within the lookback window (undated items are dropped)
      2. de-duplicated by normalised headline and by link
      3. classified into a lane and scored
      4. filtered to stories that are squarely about their lane
      5. filled to the diet's quotas, capped at max_items
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    fresh = []
    undated = stale = 0
    for item in items:
        if item["published"] is None:
            undated += 1
        elif item["published"] < cutoff:
            stale += 1
        else:
            fresh.append(item)

    seen_titles, seen_links = set(), set()
    unique = []
    duplicates = 0
    for item in sorted(fresh, key=lambda i: i["published"], reverse=True):
        tkey, lkey = dedupe_key(item["title"]), item["link"].rstrip("/")
        if tkey in seen_titles or lkey in seen_links:
            duplicates += 1
            continue
        seen_titles.add(tkey)
        seen_links.add(lkey)
        item["lane"], item["lanes"], item["score"] = classify(item)
        unique.append(item)

    ranked = sorted(unique, key=lambda i: (i["score"], i["published"]), reverse=True)

    # Drop stories that never named their lane in the headline. The guard is
    # for freak quiet days, when a thin relevant brief beats an empty one.
    on_topic = [i for i in ranked if i["score"] >= MIN_SCORE]
    if len(on_topic) >= 4:
        off_topic = len(ranked) - len(on_topic)
        ranked = on_topic
    else:
        off_topic = 0

    picked = balance(ranked, max_items=max_items)

    stats = {
        "raw": len(items),
        "stale": stale,
        "undated": undated,
        "duplicates": duplicates,
        "off_topic": off_topic,
        "eligible": len(ranked),
        "kept": len(picked),
    }
    return picked, stats


# --- Reporting ----------------------------------------------------------

def report_selection(stats):
    """One line showing the filter's working."""
    print(
        f"\n{stats['raw']} items fetched -> "
        f"{stats['stale']} older than {LOOKBACK_HOURS}h, "
        f"{stats['undated']} undated, "
        f"{stats['duplicates']} duplicates, "
        f"{stats['off_topic']} off-topic -> "
        f"{stats['eligible']} eligible -> keeping {stats['kept']}"
    )


def report_brief(picked):
    """
    Print the brief grouped by lane, in diet order.

    Grouped rather than ranked flat, because the lane is the point: you read
    the Africa block asking a different question from the one you ask of the
    Security block, and the intent line above each group is there to make you
    ask it.
    """
    if not picked:
        print("\nNothing to show. See the log above for why.")
        return

    now = datetime.now(timezone.utc)
    print("\n" + "=" * 78)
    print(f"THE DAILY AI BRIEF - {datetime.now().strftime('%d %B %Y, %H:%M')}")
    print("=" * 78)

    for lane in sorted(LANE_SHARE, key=LANE_SHARE.get, reverse=True):
        group = [i for i in picked if i["lane"] == lane]
        if not group:
            continue
        print(f"\n{lane.upper()}  ({len(group)})")
        print(f"  {LANE_INTENT[lane]}")
        for item in sorted(group, key=lambda i: i["published"], reverse=True):
            # Clamped at zero: some publishers stamp items slightly in the
            # future (timezone sloppiness, or scheduled posts), and a brief
            # that says "-1h ago" reads like a bug even though the story is
            # fine. Future-dated items are kept - they are the freshest thing
            # in the feed - they just print as 0h.
            age_h = max(0.0, (now - item["published"]).total_seconds() / 3600)
            mark = {ANALYSIS: "**", PRIMARY: " *", REPORTING: "  "}[item["tier"]]
            print(f"\n  {mark} {item['title']}")
            print(f"     {item['source']} | {age_h:.0f}h ago")
            if item.get("summary"):
                print(f"     {item['summary']}")
            if item.get("why"):
                # Indented and arrowed, because this is the line the
                # whole project exists for. It must not read as more
                # summary - it is the part you could say out loud.
                print(f"     -> {item['why']}")
            print(f"     {item['link']}")

    print("\n" + "-" * 78)
    print("** = explains the mechanism    * = the people who shipped it")


def report_dropped(dropped):
    """
    List what the relevance gate rejected, briefly.

    Printed on purpose. A filter you cannot see is a filter you cannot argue
    with, and this one is making a judgement call on your behalf every morning.
    If it starts dropping things you wanted, this is how you find out.
    """
    if not dropped:
        return
    print(f"\nDropped as not worth reading ({len(dropped)}):")
    for item in dropped:
        print(f"  - [{item['lane']}] {item['title'][:68]}  ({item['source']})")


def main():
    """
    Run the pipeline. Returns a process exit code: 0 healthy, 1 needs a human.

    Two different empty results must not be treated the same way, which is why
    this returns a code at all - it will eventually run unattended:

      * A genuinely quiet couple of days is SUCCESS. An honest thin brief is a
        real answer.
      * Finding stories and then failing to summarise them is FAILURE, and it
        exits non-zero so a scheduled run goes red and reports itself rather
        than leaving you thinking the field went quiet.
    """
    candidates, stats = select_items(fetch_all(), max_items=SUMMARISE_POOL)
    report_selection(stats)

    if not candidates:
        print(
            "\nNothing in the window. Widen LOOKBACK_HOURS in run.py if this "
            "happens on a day that was clearly not quiet."
        )
        return 0

    kept, dropped = summarise(candidates)

    if not kept and not dropped:
        print(
            f"\nFAILED: {len(candidates)} stories were selected but none could "
            "be summarised. See the log above."
        )
        return 1

    # Re-balance the survivors down to the real brief. The first balance chose
    # a POOL, respecting the diet; this one chooses the BRIEF from whatever
    # survived the relevance gate, respecting it again. Doing it twice is what
    # stops the gate quietly reshaping the diet: if Gemini drops four Africa
    # stories, Africa's slots are refilled from Africa, not handed to whatever
    # lane happened to have leftovers.
    picked = balance(kept, max_items=MAX_ITEMS)
    report_brief(picked)
    report_dropped(dropped)

    print("\nRendering page...")
    lane_order = sorted(LANE_SHARE, key=LANE_SHARE.get, reverse=True)
    path = render(picked, dropped=dropped, lane_order=lane_order)
    if not path:
        return 1

    print(f"\nDone. Open it with:  start {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
