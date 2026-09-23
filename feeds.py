"""
RSS sources for the daily AI Brief.

Every feed here was probed live before being added: it must return HTTP 200
(or redirect to one) AND carry genuinely recent items. Feeds that answered but
were abandoned are excluded - SemiAnalysis returns HTTP 200 with a healthy
lastBuildDate and its newest article is over a year old. Check item dates, not
just that a feed responds.

Probed and deliberately left out:

    Anthropic       publishes NO feed. /rss.xml, /feed.xml, /news/rss.xml and
                    /blog/rss.xml all 404, and anthropic.com/news advertises
                    nothing in its <head>. This is a real gap in the primary
                    sources - Anthropic coverage arrives here second-hand via
                    Simon Willison, Interconnects, Latent Space, Ars Technica
                    and Hacker News. Re-check occasionally; it may appear.
    Meta AI         ai.meta.com/blog advertises no feed and every path 404s.
                    engineering.fb.com carries the systems work instead, which
                    is the more useful half for you anyway.
    VentureBeat AI  answers 429 to every request, browser user-agent included.
                    Rate-limiting, not a dead feed, but unusable unattended.
    a16z, Microsoft AI, arXiv cs.AI    404 / 410 / no response.
    SemiAnalysis    live feed, year-old articles. See above.

Reaching Anthropic or Meta would mean scraping their HTML, which is a
different job with a different legal footing - a deliberate decision, not a
quiet workaround.

LANES
-----
Every feed belongs to one lane, and the lanes implement the information diet:
agents and coding get the most room, then frontier models, then infrastructure
and Africa, then security and business. See LANE_QUOTA in run.py.

A feed's lane is only its STARTING lane. What a story is actually about is
decided per-item by the keyword classifier in run.py, so a TechCrunch piece
about a data centre in Lagos can move from Frontier Models to Africa. The lane
here is the fallback for stories the classifier cannot place.
"""

# tier 2 = primary source: the lab, the vendor or the engineer who did the work.
# tier 1 = reporting and analysis about someone else's work.
# Used as a small ranking bonus, not a filter. A launch should be read from the
# people who shipped it before it is read from someone summarising the launch.
PRIMARY, REPORTING = 2, 1

FEEDS = [
    # --- Agents & coding: the 30%, your biggest lane -------------------
    {"name": "Simon Willison",      "lane": "Agents & Coding", "tier": PRIMARY,   "url": "https://simonwillison.net/atom/everything/"},
    {"name": "Latent Space",        "lane": "Agents & Coding", "tier": PRIMARY,   "url": "https://www.latent.space/feed"},
    {"name": "Import AI",           "lane": "Agents & Coding", "tier": PRIMARY,   "url": "https://jack-clark.net/feed/"},
    {"name": "Interconnects",       "lane": "Agents & Coding", "tier": PRIMARY,   "url": "https://www.interconnects.ai/feed"},
    {"name": "GitHub Blog",         "lane": "Agents & Coding", "tier": PRIMARY,   "url": "https://github.blog/ai-and-ml/feed/"},
    {"name": "Pragmatic Engineer",  "lane": "Agents & Coding", "tier": PRIMARY,   "url": "https://newsletter.pragmaticengineer.com/feed"},
    # Points threshold, not the raw front page: 200+ is the bar at which a
    # story is something the whole field is discussing, not just noise.
    {"name": "Hacker News",         "lane": "Agents & Coding", "tier": REPORTING, "url": "https://hnrss.org/frontpage?points=200"},

    # --- Frontier models: the 20% --------------------------------------
    {"name": "OpenAI",              "lane": "Frontier Models", "tier": PRIMARY,   "url": "https://openai.com/news/rss.xml"},
    {"name": "Google DeepMind",     "lane": "Frontier Models", "tier": PRIMARY,   "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "Google AI",           "lane": "Frontier Models", "tier": PRIMARY,   "url": "https://blog.google/innovation-and-ai/technology/ai/rss/"},
    {"name": "Google Research",     "lane": "Frontier Models", "tier": PRIMARY,   "url": "https://research.google/blog/rss/"},
    # Advertised in the mistral.ai/news <head>, but NOT at the /news/feed.xml
    # or /news/rss.xml you would guess. Read the head; do not guess URLs.
    {"name": "Mistral",             "lane": "Frontier Models", "tier": PRIMARY,   "url": "https://mistral.ai/news/rss"},
    {"name": "Hugging Face",        "lane": "Frontier Models", "tier": PRIMARY,   "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "Meta Engineering",    "lane": "Frontier Models", "tier": PRIMARY,   "url": "https://engineering.fb.com/feed/"},
    {"name": "MIT Tech Review",     "lane": "Frontier Models", "tier": REPORTING, "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
    {"name": "Ars Technica",        "lane": "Frontier Models", "tier": REPORTING, "url": "https://arstechnica.com/ai/feed/"},
    {"name": "The Verge",           "lane": "Frontier Models", "tier": REPORTING, "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "TechCrunch",          "lane": "Frontier Models", "tier": REPORTING, "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},

    # --- Infrastructure: the 15% ---------------------------------------
    {"name": "NVIDIA",              "lane": "Infrastructure",  "tier": PRIMARY,   "url": "https://blogs.nvidia.com/feed/"},
    {"name": "AWS Machine Learning","lane": "Infrastructure",  "tier": PRIMARY,   "url": "https://aws.amazon.com/blogs/machine-learning/feed/"},
    {"name": "Cloudflare",          "lane": "Infrastructure",  "tier": PRIMARY,   "url": "https://blog.cloudflare.com/rss/"},
    {"name": "Data Center Dynamics","lane": "Infrastructure",  "tier": REPORTING, "url": "https://www.datacenterdynamics.com/en/rss/"},
    {"name": "The Register",        "lane": "Infrastructure",  "tier": REPORTING, "url": "https://www.theregister.com/software/ai_ml/headlines.atom"},

    # --- Africa: the 15%, and the lane nobody else is reading ----------
    {"name": "TechCabal",           "lane": "Africa",          "tier": REPORTING, "url": "https://techcabal.com/feed/"},
    {"name": "TechCentral",         "lane": "Africa",          "tier": REPORTING, "url": "https://techcentral.co.za/feed/"},
    {"name": "Techpoint Africa",    "lane": "Africa",          "tier": REPORTING, "url": "https://techpoint.africa/feed/"},
    {"name": "Disrupt Africa",      "lane": "Africa",          "tier": REPORTING, "url": "https://disruptafrica.com/feed/"},
    {"name": "Technext",            "lane": "Africa",          "tier": REPORTING, "url": "https://technext24.com/feed/"},
    {"name": "ITWeb",               "lane": "Africa",          "tier": REPORTING, "url": "https://www.itweb.co.za/rss"},
    {"name": "Ventureburn",         "lane": "Africa",          "tier": REPORTING, "url": "https://ventureburn.com/feed/"},
    # Not African, but it covers technology from everywhere that is not
    # Silicon Valley, which is the same habit of mind you are building.
    {"name": "Rest of World",       "lane": "Africa",          "tier": REPORTING, "url": "https://restofworld.org/feed/latest/"},

    # --- Security & safety: the 10% ------------------------------------
    {"name": "Schneier",            "lane": "Security",        "tier": PRIMARY,   "url": "https://www.schneier.com/feed/atom/"},
    {"name": "Krebs on Security",   "lane": "Security",        "tier": PRIMARY,   "url": "https://krebsonsecurity.com/feed/"},
    {"name": "The Hacker News",     "lane": "Security",        "tier": REPORTING, "url": "https://feeds.feedburner.com/TheHackersNews"},
    {"name": "BleepingComputer",    "lane": "Security",        "tier": REPORTING, "url": "https://www.bleepingcomputer.com/feed/"},
    {"name": "Normal Technology",   "lane": "Security",        "tier": PRIMARY,   "url": "https://www.normaltech.ai/feed"},
    {"name": "Don't Worry",         "lane": "Security",        "tier": PRIMARY,   "url": "https://thezvi.substack.com/feed"},

    # --- Business & economics: the 10% ---------------------------------
    {"name": "Stratechery",         "lane": "Business",        "tier": PRIMARY,   "url": "https://stratechery.com/feed/"},
    {"name": "Tomasz Tunguz",       "lane": "Business",        "tier": PRIMARY,   "url": "https://tomtunguz.com/index.xml"},
    {"name": "Sifted",              "lane": "Business",        "tier": REPORTING, "url": "https://sifted.eu/feed"},
]


# What each lane is FOR, in your own words. Printed above each group so the
# brief keeps asking you the question rather than just handing you headlines.
LANE_INTENT = {
    "Agents & Coding": "What can an agent now DO without a human?",
    "Frontier Models": "What capability just became possible?",
    "Infrastructure":  "Compute, power, data centres - what did they cost?",
    "Africa":          "What does this mean for Zimbabwe?",
    "Security":        "What new attack or failure mode appears?",
    "Business":        "Where is the money actually moving?",
}


# Keyword matching, same three rules as the Vintage build - they were worked
# out against real misfires and there is no reason to relearn them:
#
#   "gpu", "llm"  1-3 letters -> whole word only. Anything looser and "ai"
#                 hits aim/air/aid, "ml" hits HTML.
#   "agent"       a normal word -> the word plus ordinary endings:
#                 agent, agents, agented. It will NOT match a longer word that
#                 merely starts the same way.
#   "infer*"      ends in * -> a stem matching ANY continuation. Needed for
#                 inference/inferencing, autonom* for autonomy/autonomous.
#
# If a term is not matching the way you expect, it probably needs a *.
#
# Note "ai" is NOT a keyword anywhere. Every story here is an AI story; the
# job of these lists is to tell the lanes apart, and a term that matches
# everything tells you nothing.
LANE_KEYWORDS = {
    "Agents & Coding": [
        "agent", "agentic", "autonom*", "tool use", "tool call*", "function call*",
        "mcp", "model context protocol", "claude code", "codex", "copilot",
        "cursor", "devin", "aider", "coding assistant", "pair program*",
        "pull request", "code review", "refactor*", "debug*", "test suite",
        "orchestrat*", "multi-agent", "workflow", "automat*", "scaffold*",
        "computer use", "browser use", "sandbox*", "software engineer*",
        "developer", "programm*", "codebase", "repository", "commit", "ci/cd",
        "swe-bench", "terminal", "harness", "context window", "ide",
    ],
    "Frontier Models": [
        "gpt*", "claude", "gemini", "llama", "mistral", "deepseek", "qwen",
        "grok", "frontier model", "foundation model", "llm", "llms",
        "reasoning", "chain of thought", "multimodal", "vision model",
        "benchmark*", "eval*", "fine-tun*", "pretrain*", "post-train*",
        "open weight*", "open source model", "parameter*", "token*", "distill*",
        "rlhf", "reinforcement learning", "transformer", "diffusion",
        "text-to-video", "text-to-image", "speech", "voice model", "embedding*",
        "model card", "context length", "state of the art",
    ],
    "Infrastructure": [
        "gpu", "gpus", "tpu", "chip*", "semiconductor", "nvidia", "amd", "intel",
        "blackwell", "hopper", "wafer", "foundry", "tsmc", "data centre",
        "data center", "datacenter", "cluster", "supercomput*", "compute",
        "infer*", "training run", "flops", "bandwidth", "electricity",
        "power grid", "megawatt", "gigawatt", "cooling", "energy", "capex",
        "cloud", "hyperscal*", "quantiz*", "distributed", "latency",
        "throughput", "serving", "on-device", "local model", "network*",
        "fibre", "fiber", "undersea cable", "bare metal", "edge",
    ],
    "Africa": [
        "africa", "african", "zimbabwe", "harare", "nigeria", "lagos", "kenya",
        "nairobi", "south africa", "johannesburg", "cape town", "ghana",
        "accra", "egypt", "rwanda", "kigali", "ethiopia", "tanzania", "uganda",
        "zambia", "senegal", "morocco", "botswana", "mozambique", "malawi",
        "swahili", "yoruba", "hausa", "amharic", "shona", "ndebele", "zulu",
        "afrikaans", "low-resource language", "global south", "emerging market*",
        "mobile money", "m-pesa", "ecocash", "paynow", "sme", "smes",
        "leapfrog*", "informal sector", "diaspora",
    ],
    "Security": [
        "prompt injection", "jailbreak*", "data poison*", "supply chain",
        "vulnerab*", "exploit*", "zero-day", "zero day", "cve", "malware",
        "ransomware", "breach", "leak*", "phish*", "attack*", "threat actor",
        "red team*", "adversarial", "backdoor", "malicious", "compromise*",
        "permission*", "authorization", "authentication", "sandbox escape",
        "privilege", "credential*", "secret*", "misalign*", "safety", "alignment",
        "guardrail*", "governance", "regulation", "eu ai act", "policy",
        "privacy", "surveillance", "deepfake", "watermark*",
    ],
    "Business": [
        "funding", "raise*", "raised", "series a", "series b", "series c",
        "seed round", "valuation", "ipo", "acquisition", "acquire*", "merger",
        "venture capital", "investor*", "startup*", "revenue", "arr",
        "profit*", "burn rate", "pricing", "price cut", "cheaper",
        "cost per", "margin*", "subscription", "enterprise", "adoption",
        "market share", "layoff*", "hiring", "partnership", "contract",
        "monetis*", "monetiz*", "business model", "customer*", "churn",
        "api pricing", "free tier", "token cost", "deal",
    ],
}
