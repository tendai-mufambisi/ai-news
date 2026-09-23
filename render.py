"""
Jinja rendering for the Daily AI Brief.

PHASE 3 of 3.

Takes the summarised stories and writes index.html: one self-contained static
file, no build step, no CDN, no fonts to fetch. It opens instantly from disk
at six in the morning on a bad connection, which is the only deployment
target that matters here.

The layout has one job: make the WHY-LINE the thing your eye lands on. The
headline tells you what happened and the summary fills it in, but the why-line
is the part you could repeat to someone - so it gets the size and the colour,
and the summary sits underneath it in grey. A page that gave all three equal
weight would just be a prettier feed reader.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from feeds import ANALYSIS, LANE_INTENT, PRIMARY

TEMPLATE = "template.html"
OUTPUT = "index.html"

# Harare is UTC+2 year round. A fixed offset is correct and safer than
# zoneinfo here: Zimbabwe has no daylight saving, and Windows ships without
# the IANA database unless tzdata is installed.
CAT = timezone(timedelta(hours=2), "CAT")


def humanise_age(published):
    """Turn a publish time into 'Just now' / '4h ago' / 'Yesterday'."""
    if published is None:
        return ""
    hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
    if hours < 1:
        return "Just now"
    if hours < 24:
        return f"{hours:.0f}h ago"
    if hours < 48:
        return "Yesterday"
    return f"{hours / 24:.0f}d ago"


def tier_label(tier):
    """
    How a source earns its badge.

    Only ANALYSIS gets a visible one. Marking every card would turn the badge
    into wallpaper; marking the small number of pieces that actually explain
    a mechanism makes it a signal worth glancing at.
    """
    if tier == ANALYSIS:
        return "Explains the mechanism"
    if tier == PRIMARY:
        return "From the source"
    return ""


def to_card(item):
    """
    Flatten a pipeline item into the fields the template uses.

    The template gets plain strings only - no datetimes, no lists - so the
    markup stays free of formatting logic.
    """
    return {
        "title": item["title"],
        "summary": item.get("summary", ""),
        "why": item.get("why", ""),
        "link": item["link"],
        "source": item["source"],
        "age": humanise_age(item.get("published")),
        "badge": tier_label(item.get("tier")),
        "is_analysis": item.get("tier") == ANALYSIS,
    }


def group_by_lane(items, lane_order):
    """
    Build the lane blocks the page is laid out in.

    Lanes with nothing in them are omitted rather than rendered empty. An
    empty lane is honest in the terminal log, but on the page it reads as a
    broken section - and the drop list at the bottom already accounts for
    where a lane's stories went.
    """
    blocks = []
    for lane in lane_order:
        cards = [to_card(i) for i in items if i["lane"] == lane]
        if cards:
            blocks.append(
                {"lane": lane, "question": LANE_INTENT[lane], "cards": cards}
            )
    return blocks


def render(items, dropped=None, lane_order=(), output=OUTPUT):
    """
    Write index.html. Returns the path written, or None if it could not be.

    autoescape is on deliberately: headlines arrive from the open web, and an
    unescaped title containing markup would be injected straight into a page
    you open every morning.
    """
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    try:
        template = env.get_template(TEMPLATE)
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all
        print(f"  [fail] could not load {TEMPLATE}: {exc}")
        return None

    now = datetime.now(CAT)
    html = template.render(
        blocks=group_by_lane(items, lane_order),
        # The rejected stories ride along so the gate stays visible on the
        # page too, not just in a terminal you will stop reading.
        dropped=[
            {"title": d["title"], "source": d["source"], "lane": d["lane"],
             "link": d["link"]}
            for d in (dropped or [])
        ],
        count=len(items),
        generated_at=now.strftime("%A %d %B %Y, %H:%M"),
        date_short=now.strftime("%d %b"),
        year=now.year,
    )

    try:
        path = Path(__file__).with_name(output)
        path.write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"  [fail] could not write {output}: {exc}")
        return None

    kb = len(html.encode("utf-8")) / 1024
    print(f"  [ok]   wrote {path.name} ({kb:.0f} KB, {len(items)} stories)")
    return path
