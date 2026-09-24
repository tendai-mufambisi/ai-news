# The Daily AI Brief

A self-updating morning brief on AI, built to keep a deliberate information diet
rather than to maximise headlines. It fetches 40 RSS feeds, sorts what it finds into
six lanes, asks Gemini what each story actually means, and writes one static page.

Live at **ainews.digitsdigital.co.zw**.

## Why it is shaped this way

Most AI news habits fail the same way: you end up reading whatever the fastest
publisher posted this morning, which is mostly product announcements. This is built
against that.

**Six lanes with fixed shares of a 12-story brief.** A busy day in one lane cannot
crowd out another — Africa is guaranteed its slots whatever Silicon Valley did.

| Lane | Share | The question it answers |
|---|---|---|
| Agents & Coding | 30% | What can an agent now DO without a human? |
| Frontier Models | 20% | What capability just became possible? |
| Infrastructure | 15% | Compute, power, data centres — what did they cost? |
| Africa | 15% | What does this mean for Zimbabwe? |
| Security | 10% | What new attack or failure mode appears? |
| Business | 10% | Where is the money actually moving? |

**Analysis outranks announcements.** Sources are tiered: writers who explain a
mechanism rank above the lab that shipped the thing, which ranks above a write-up of
the launch. A vendor telling you something exists is worth less than someone telling
you what changed.

**Every story gets a why-line.** Two sentences of summary, then one line answering
that lane's question. The why-line is the point — it is the part you could repeat to
someone. The page gives it the size and the colour; the summary sits underneath in grey.

**A relevance gate you can see.** Gemini rejects vendor case studies, event notices and
business stories with no AI substance. Rejections are listed at the bottom of every
brief, on the page and in the terminal, because a filter you cannot see is a filter you
cannot argue with.

## Running it locally

```bash
python -m venv aienv
aienv\Scripts\activate          # Windows
pip install -r requirements.txt
echo GEMINI_API_KEY=your_key_here > .env
python run.py
```

It writes `index.html` next to `run.py` and prints the same brief to the terminal.

## How it goes live

```
GitHub Actions (04:10 UTC daily)
  -> runs the pipeline, commits index.html
     -> Cloudflare Pages sees the commit, deploys it
        -> ainews.digitsdigital.co.zw
```

The built page is committed to the repository on purpose: what you get locally is
exactly what is served, with no build step in between.

### One-time setup

1. **Add the API key to GitHub.** Settings → Secrets and variables → Actions → New
   repository secret, named `GEMINI_API_KEY`. The workflow reads it from the
   environment; it is never written to a file.
2. **Connect Cloudflare Pages.** Workers & Pages → Create → Pages → Connect to Git →
   this repository. Build command: **none**. Build output directory: **`/`**. The page
   is already built when it arrives.
3. **Point the subdomain.** In the Pages project, Custom domains → `ainews.digitsdigital.co.zw`.
   Cloudflare adds the CNAME itself if the zone is on the same account.
4. **Check it.** Actions tab → Daily AI Brief → Run workflow, rather than waiting for
   the morning.

### Failure behaviour

`run.py` exits non-zero when it found stories but could not summarise them, which fails
the workflow and leaves the previous page up. That is deliberate: yesterday's correct
brief beats today's empty one, and a red run is how you find out something broke. A
genuinely quiet news day is different — it exits 0 and writes an honest thin page.

Free-tier Gemini models return 503 fairly often, so `summarise.py` tries three models
with backoff before giving up.

## Not indexed

The page carries `noindex` in three places (meta tag, `_headers`, and AI crawlers
blocked in `robots.txt`). Crawling is allowed on purpose — a crawler has to fetch the
page to read the noindex instruction; `Disallow: /` would hide the instruction and the
URL could still be listed.

## On copyright

No article text is ever reproduced. Each entry is an original summary written from the
headline and standfirst, plus a link to the original. The publishers do the reporting;
this page points at it.

## Files

| File | What it does |
|---|---|
| `feeds.py` | The 40 feeds, their lanes and tiers, and the lane keywords |
| `run.py` | Fetch, filter, classify, quota-balance, report |
| `summarise.py` | Gemini: summary, why-line, relevance judgement |
| `render.py` | Jinja → `index.html` |
| `template.html` | The page. One file, no CDN, no webfont, no external request |

Every feed in `feeds.py` was probed live before being added, and the ones that were
rejected are documented there with the reason — including the several that return
HTTP 200 while serving year-old articles.
