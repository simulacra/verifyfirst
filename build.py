#!/usr/bin/env python3
"""Render verifyfirst.dev from registry.json.

The registry is the artifact; every page is a projection of it. Nothing is
authored twice, so the HTML, the plain-text endpoints and the JSON cannot
disagree — which is P-1 applied to the site itself.

Emits:
  index.html            the instrument picker
  <instrument>/         one page per instrument
  <instrument>.txt      the same, as plain text, for agents that curl
  registry/             every entry, with stable anchors
  protocol/             the discipline, short enough to paste into a prompt
  registry.json/.jsonl  structured
  llms.txt              orientation
  robots.txt sitemap.xml

Usage: python3 build.py [outdir]
"""
import html
import os
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "registry.json").read_text())
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "dist"
BASE = "https://verifyfirst.dev"
REPO = "https://github.com/simulacra/verifyfirst"
# The analytics property is site-owner config, not source. Read from the
# environment or ~/.config/verifyfirst.env so the repo carries no one's
# measurement ID — a published ID is an invitation to poison the data.
def _ga_id() -> str:
    v = os.environ.get("VERIFYFIRST_GA_ID", "").strip()
    if v:
        return v
    cfg = Path.home() / ".config" / "verifyfirst.env"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            if line.startswith("VERIFYFIRST_GA_ID="):
                return line.split("=", 1)[1].strip().strip('"\'')
    return ""


GA_ID = _ga_id()

# GA4 measures humans only — it needs a JS runtime, and most agent fetches have
# none. Agent traffic is counted server-side from the access log instead.
# Loaded async so the page still works, and still reads, with scripts disabled.
GA = (f"""<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}
gtag('js',new Date());gtag('config','{GA_ID}');</script>""" if GA_ID else "")

INSTRUMENTS = DATA["instruments"]
ENTRIES = DATA["entries"]
BY_INSTRUMENT = {i["id"]: [e for e in ENTRIES if e["instrument"] == i["id"]] for i in INSTRUMENTS}

E = lambda s: html.escape(str(s), quote=True)

# ---------------------------------------------------------------------------
# Tokens. Deliberately not neon-on-black: the register is a calibration
# certificate, the document an instrument ships with stating what it is known
# to get wrong. Cool blue carries what you can act on, warm orange carries
# what cannot be seen, and those two never appear in the same role.
# ---------------------------------------------------------------------------
CSS = """
:root{
  --ground:#141319; --panel:#1a1922; --raise:#201f2a;
  --rule:#2c2a38; --rule-soft:#232230;
  --ink:#e9e7f0; --dim:#8f8ba1; --faint:#615d73;
  --signal:#79cdf5;   /* what you can do */
  --blind:#e4835b;    /* what cannot be seen */
  --sans:ui-sans-serif,system-ui,"Segoe UI",Inter,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SFMono-Regular","JetBrains Mono","DejaVu Sans Mono",monospace;
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
main{max-width:70rem;margin:0 auto;padding:clamp(1.5rem,5vw,3.5rem) clamp(1.1rem,4vw,2rem) 6rem}
.narrow{max-width:46rem}
a{color:var(--signal)}
code,kbd,pre{font-family:var(--mono)}

/* Masthead ------------------------------------------------------------- */
.mast{display:flex;flex-wrap:wrap;gap:.6rem 1.2rem;align-items:baseline;
  padding-bottom:1rem;border-bottom:1px solid var(--rule);margin-bottom:2.2rem}
.mast a.home{font-family:var(--mono);font-size:15px;letter-spacing:-.01em;
  color:var(--ink);text-decoration:none;font-weight:600}
.mast a.home span{color:var(--signal)}
.mast nav{margin-left:auto;display:flex;gap:1.1rem;flex-wrap:wrap}
.mast nav a{font-family:var(--mono);font-size:12.5px;color:var(--dim);text-decoration:none;
  letter-spacing:.02em}
.mast nav a:hover,.mast nav a:focus-visible{color:var(--signal)}

/* Type ----------------------------------------------------------------- */
h1{font-size:clamp(1.9rem,4.6vw,3rem);line-height:1.08;letter-spacing:-.028em;
  margin:0 0 1rem;font-weight:600}
h2{font-family:var(--mono);font-size:12px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--faint);font-weight:500;margin:3.2rem 0 1.1rem;
  padding-bottom:.55rem;border-bottom:1px solid var(--rule-soft)}
h3{font-size:1.05rem;font-weight:600;line-height:1.35;margin:0 0 .8rem;letter-spacing:-.01em}
p{margin:0 0 1rem}
.lede{font-size:clamp(1.05rem,2vw,1.2rem);line-height:1.55;color:var(--ink);max-width:46rem}
.sub{font-family:var(--mono);font-size:12.5px;color:var(--faint);letter-spacing:.02em;margin:0 0 2rem}
.note{color:var(--dim);font-size:14.5px;max-width:46rem}

/* The picker — the page's one job is to route you to your instrument. */
.pick{display:grid;grid-template-columns:repeat(auto-fit,minmax(17rem,1fr));gap:1px;
  background:var(--rule-soft);border:1px solid var(--rule-soft);margin:0 0 1rem}
.card{background:var(--panel);padding:1.15rem 1.2rem 1.25rem;text-decoration:none;color:inherit;
  display:flex;flex-direction:column;gap:.5rem;min-height:100%}
.card:hover,.card:focus-visible{background:var(--raise)}
.card .used{font-family:var(--mono);font-size:12px;color:var(--dim);line-height:1.5}
.card h3{margin:0;font-size:1rem}
.card .arrow{font-family:var(--mono);font-size:12px;color:var(--signal);margin-top:auto;padding-top:.6rem}
.card .n{font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.1em;
  text-transform:uppercase}

/* Blind spots — the signature. What the instrument cannot represent is drawn
   as an absence: hatched fill, nothing printed on it, a hairline edge. The
   page shows the shape of the gap rather than describing it. */
.blind{list-style:none;margin:0 0 1.4rem;padding:0;display:grid;gap:.55rem}
.blind li{position:relative;border:1px solid var(--rule);padding:.7rem .85rem .7rem 2.4rem;
  background:
    repeating-linear-gradient(135deg,
      rgba(228,131,91,.055) 0 6px, rgba(0,0,0,0) 6px 12px);
  color:var(--ink);font-size:15px;line-height:1.55}
.blind li::before{content:"";position:absolute;left:.85rem;top:1.05rem;
  width:.7rem;height:1px;background:var(--blind);opacity:.9}
.blind-h{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--blind);margin:0 0 .7rem}
.sees-h{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--dim);margin:0 0 .5rem}
.sees{border-left:2px solid var(--rule);padding-left:1rem;color:var(--dim);margin:0 0 2rem;
  max-width:44rem}

/* Entries -------------------------------------------------------------- */
article{border:1px solid var(--rule-soft);background:var(--panel);padding:1.3rem 1.35rem;
  margin:0 0 .85rem}
article:target{border-color:var(--signal)}
.ehead{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:baseline;margin-bottom:.55rem}
.eid{font-family:var(--mono);font-size:12px;letter-spacing:.12em;color:var(--signal);text-decoration:none}
.ecls{font-family:var(--mono);font-size:11.5px;color:var(--faint);letter-spacing:.06em;margin-left:auto}
dl{margin:0;display:grid;grid-template-columns:10rem 1fr;gap:.5rem 1.2rem}
dt{font-family:var(--mono);font-size:11px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--faint);padding-top:.32rem}
dd{margin:0;font-size:15px}
dt.cost-k{color:var(--blind)}
.prov{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
  border:1px solid var(--rule);padding:.12rem .4rem;margin-right:.6rem;border-radius:2px}
.prov--observed{color:var(--signal);border-color:rgba(121,205,245,.35)}
.prov--documented{color:var(--dim)}

/* The check is the only actionable line in an entry, so it takes the full
   width and the prompt. Everything above it is diagnosis. */
dt.check-k{grid-column:1/-1;color:var(--signal);margin-top:.6rem;padding-top:0}
dd.check{grid-column:1/-1;margin-bottom:.6rem;position:relative;
  border-left:2px solid var(--signal);background:rgba(121,205,245,.06);
  padding:.6rem .8rem .6rem 1.9rem;color:var(--signal);
  font-family:var(--mono);font-size:13.5px;line-height:1.55;
  white-space:pre-wrap;overflow-wrap:anywhere;overflow-x:auto}
dd.check::before{content:"\\203A";position:absolute;left:.8rem;top:.6rem;opacity:.6}

/* Principles ----------------------------------------------------------- */
ol.pr{list-style:none;margin:0;padding:0;counter-reset:p}
ol.pr li{counter-increment:p;position:relative;padding:0 0 0 3rem;margin:0 0 1.4rem;max-width:46rem}
ol.pr li::before{content:"P-" counter(p);position:absolute;left:0;top:.15rem;
  font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.08em}
ol.pr b{font-weight:600}
ol.pr p{margin:.25rem 0 0;color:var(--dim);font-size:14.5px}

/* Bits ----------------------------------------------------------------- */
.formats{font-family:var(--mono);font-size:13px;color:var(--dim);border:1px solid var(--rule-soft);
  padding:.9rem 1rem;background:var(--panel);max-width:46rem}
.formats code{color:var(--ink)}
pre.sh{font-size:13px;background:var(--panel);border:1px solid var(--rule-soft);
  padding:.85rem 1rem;overflow-x:auto;color:var(--signal);margin:0 0 1.2rem;max-width:46rem}
footer{margin-top:4.5rem;padding-top:1.2rem;border-top:1px solid var(--rule-soft);
  font-family:var(--mono);font-size:12px;color:var(--faint);max-width:46rem}
footer a{color:var(--dim)}
.by{display:block;margin-top:.8rem;padding-top:.8rem;border-top:1px solid var(--rule-soft);
  color:var(--faint)}
.by a{color:var(--dim);text-decoration:none;border-bottom:1px solid var(--rule)}
.by a:hover,.by a:focus-visible{color:var(--signal);border-color:var(--signal)}
:focus-visible{outline:2px solid var(--signal);outline-offset:2px}

@media(max-width:34rem){
  body{font-size:15.5px}
  dl{grid-template-columns:1fr;gap:0}
  dt{padding-top:.75rem}
  dt:first-child{padding-top:0}
  dt.check-k{margin-top:.75rem}
  .ecls{margin-left:0;width:100%}
  article{padding:1.05rem}
}
@media(prefers-reduced-motion:no-preference){
  .card,article{transition:background .18s ease,border-color .25s ease}
}
"""


def shell(title: str, desc: str, body: str, canonical: str, narrow: bool = False,
          ld: dict | None = None) -> str:
    ldtag = (f'<script type="application/ld+json">{json.dumps(ld)}</script>' if ld else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="robots" content="index, follow">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{E(canonical)}">
<style>{CSS}</style>
{ldtag}
{GA}
</head>
<body>
<main{' class="narrow"' if narrow else ''}>
  <div class="mast">
    <a class="home" href="/">verify<span>first</span></a>
    <nav>
      <a href="/registry/">registry</a>
      <a href="/protocol/">protocol</a>
      <a href="/mcp/">mcp</a>
      <a href="/llms.txt">llms.txt</a>
      <a href="{REPO}">github</a>
    </nav>
  </div>
{body}
  <footer>
    Every entry is a failure that genuinely occurs, not one imagined to illustrate a point.
    Public domain (CC0) &mdash; copy it, quote it, paste it into a system prompt.
    Pages are generated from <a href="/registry.json">registry.json</a>; there is no
    second copy to fall out of date.
    <span class="by">Maintained by <a href="https://zionlabs.io">Zion Labs</a>
      &middot; <a href="{REPO}">source</a></span>
  </footer>
</main>
</body>
</html>
"""


def entry_html(e: dict, show_instrument: bool = False) -> str:
    rows = [
        ("reads as", e["false_reading"], ""),
        ("actually", e["true_state"], ""),
        ("blind because", e["why_blind"], ""),
        ("the check", e["discriminating_check"], "check"),
        ("cost of missing", e["cost_of_missing"], "cost"),
    ]
    if e.get("mitigation"):
        rows.append(("mitigation", e["mitigation"], ""))
    rows.append(("generalises to", e["generalises_to"], ""))

    parts = []
    for label, value, cls in rows:
        dt = f'<dt class="{cls}-k">' if cls else "<dt>"
        dd = f'<dd class="{cls}">' if cls else "<dd>"
        parts.append(f"      {dt}{label}</dt>{dd}{E(value)}</dd>")

    # A claim a reader cannot check is worth less than one they can, so the
    # primary source is part of the entry rather than a footnote.
    if e.get("source"):
        host = e["source"].split("/")[2].replace("www.", "")
        parts.append(f'      <dt>source</dt><dd><a href="{E(e["source"])}" '
                     f'rel="noopener">{E(host)}</a></dd>')

    prov = e.get("provenance", "")
    badge = (f'<span class="prov prov--{E(prov)}">{E(prov)}</span>' if prov else "")

    inst = ""
    if show_instrument:
        i = next(x for x in INSTRUMENTS if x["id"] == e["instrument"])
        inst = f' &middot; <a class="eid" href="/{E(e["instrument"])}/">{E(i["name"].lower())}</a>'

    return f"""    <article id="{E(e['id'])}">
      <div class="ehead">
        <a class="eid" href="#{E(e['id'])}">{E(e['id'])}</a>{inst}
        <span class="ecls">{badge}{E(e['class'])}</span>
      </div>
      <h3>{E(e['title'])}</h3>
      <dl>
{chr(10).join(parts)}
      </dl>
    </article>"""


def instrument_txt(i: dict) -> str:
    """The plain-text view. Agents reach this with curl and read it whole, so
    it carries the checks inline rather than linking away to them."""
    n = BY_INSTRUMENT[i["id"]]
    L = [
        f"VERIFYFIRST // {i['id']}",
        f"{i['name']} — {i['used_when']}",
        "",
        "WHAT IT CAPTURES",
        f"  {i['captures']}",
        "",
        "WHAT IT CANNOT SEE",
    ]
    L += [f"  - {b}" for b in i["blind_to"]]
    L += ["", f"KNOWN FAILURES ({len(n)})"]
    for e in n:
        L += ["", f"  {e['id']}  {e['title']}",
              f"    reads as   {e['false_reading']}",
              f"    actually   {e['true_state']}",
              f"    check      {e['discriminating_check']}"]
    L += ["", "---",
          f"Full registry: {BASE}/registry.json",
          f"This page:     {BASE}/{i['id']}/",
          "CC0-1.0. Every entry observed, none hypothetical.", ""]
    return "\n".join(L)


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    urls = [f"{BASE}/", f"{BASE}/registry/", f"{BASE}/protocol/"]

    # --- landing: the picker -----------------------------------------------
    cards = "\n".join(
        f"""      <a class="card" href="/{E(i['id'])}/">
        <span class="n">{E(i['id'])}</span>
        <h3>{E(i['name'])}</h3>
        <span class="used">{E(i['used_when'])}</span>
        <span class="arrow">{len(BY_INSTRUMENT[i['id']])} known blind spots &rarr;</span>
      </a>"""
        for i in INSTRUMENTS
    )
    principles = "\n".join(
        f'      <li><b>{E(p["statement"])}</b><p>{E(p["note"])}</p></li>'
        for p in DATA["principles"]
    )
    home_body = f"""  <h1>Every instrument is blind to something.</h1>
  <p class="lede">{E(DATA['premise'])}</p>
  <p class="sub">v{E(DATA['version'])} &middot; {len(ENTRIES)} entries &middot;
     {len(INSTRUMENTS)} instruments &middot; updated {E(DATA['updated'])}</p>

  <h2>How did you verify?</h2>
  <div class="pick">
{cards}
  </div>
  <p class="note">Entries are filed under the instrument that missed the failure,
     because that is what you know at the moment you need this — not the bug,
     which is the thing you are trying to find.</p>

  <h2>From a terminal</h2>
  <pre class="sh">curl {E(BASE.replace('https://',''))}/screenshot.txt</pre>
  <p class="note">Every instrument has a plain-text twin at
     <code>/&lt;instrument&gt;.txt</code> — no JSON to parse, no JavaScript, readable
     in one fetch.</p>

  <h2>Principles</h2>
    <ol class="pr">
{principles}
    </ol>

  <h2>Formats</h2>
  <p class="formats">
     <a href="/registry.json"><code>registry.json</code></a> — everything, structured<br>
     <a href="/registry.jsonl"><code>registry.jsonl</code></a> — one entry per line<br>
     <a href="/llms.txt"><code>llms.txt</code></a> — orientation<br>
     <a href="/protocol/"><code>/protocol</code></a> — the short version, for a system prompt
  </p>"""
    (OUT / "index.html").write_text(shell(
        "What your verification method cannot see | verifyfirst",
        DATA["premise"][:180], home_body, f"{BASE}/",
        ld={"@context": "https://schema.org", "@type": "Dataset", "name": "verifyfirst",
            "description": DATA["premise"], "version": DATA["version"],
            "dateModified": DATA["updated"],
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "audience": {"@type": "Audience", "audienceType": DATA["audience"]},
            "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                              "contentUrl": f"{BASE}/registry.json"}]}), encoding="utf-8")

    # --- one page per instrument -------------------------------------------
    for i in INSTRUMENTS:
        n = BY_INSTRUMENT[i["id"]]
        blind = "\n".join(f"      <li>{E(b)}</li>" for b in i["blind_to"])
        body = f"""  <h1>{E(i['name'])}</h1>
  <p class="lede">{E(i['used_when'])}</p>

  <p class="sees-h">What it captures</p>
  <p class="sees">{E(i['captures'])}</p>

  <p class="blind-h">What it cannot see</p>
    <ul class="blind">
{blind}
    </ul>

  <h2>Known failures &middot; {len(n)}</h2>
{chr(10).join(entry_html(e) for e in n)}

  <p class="note" style="margin-top:2rem">
     Plain text: <a href="/{E(i['id'])}.txt"><code>/{E(i['id'])}.txt</code></a> &middot;
     <a href="/">all instruments</a></p>"""
        d = OUT / i["id"]
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(shell(
            f"What {i['short']} cannot see | verifyfirst",
            f"{i['used_when']} {i['blind_to'][0]}",
            body, f"{BASE}/{i['id']}/"), encoding="utf-8")
        (OUT / f"{i['id']}.txt").write_text(instrument_txt(i), encoding="utf-8")
        urls.append(f"{BASE}/{i['id']}/")

    # --- the whole registry -------------------------------------------------
    reg_body = f"""  <h1>The registry</h1>
  <p class="lede">{E(DATA['method'])}</p>
  <p class="sub">{E(DATA['standard'])}</p>
  <h2>Entries &middot; {len(ENTRIES)}</h2>
{chr(10).join(entry_html(e, show_instrument=True) for e in ENTRIES)}"""
    d = OUT / "registry"
    d.mkdir(exist_ok=True)
    (d / "index.html").write_text(shell(
        "Failures that report success | verifyfirst",
        DATA["method"][:180], reg_body, f"{BASE}/registry/"), encoding="utf-8")

    # --- protocol ------------------------------------------------------------
    pr_body = """  <h1>The protocol</h1>
  <p class="lede">Short enough to paste into a system prompt. It is the whole site
     compressed to the part you act on.</p>

  <h2>Before claiming work is done</h2>
  <ol class="pr">
    <li><b>Name the instrument.</b><p>Say how you verified: a screenshot, an exit
      code, a status line, the file on disk. If you cannot name it, you did not verify.</p></li>
    <li><b>Say what it cannot see.</b><p>Every instrument is structurally blind to
      something. Look it up before trusting the reading.</p></li>
    <li><b>Run one check that could fail.</b><p>An observation that returns the same
      result whether or not the work succeeded has confirmed nothing.</p></li>
    <li><b>Report the observation, not the inference.</b><p>"Served bytes match disk,
      HTTP 200" is checkable by a reader. "It works" is not.</p></li>
    <li><b>Prefer the resolved value over the authored one.</b><p>Ask the running
      process what it loaded, not the filesystem what it holds.</p></li>
  </ol>

  <h2>Copy</h2>
  <pre class="sh">Before reporting work complete: name the instrument you
verified with, state what that instrument cannot see,
run one check whose result would differ if the work had
failed, and report the observation rather than the
conclusion. Prefer resolved values over authored ones.</pre>
  <p class="note">Reference: <a href="/">verifyfirst.dev</a>. CC0, no attribution needed.</p>"""
    d = OUT / "protocol"
    d.mkdir(exist_ok=True)
    (d / "index.html").write_text(shell(
        "Verification protocol for AI agents | verifyfirst",
        "Name the instrument, say what it cannot see, run one check that could fail, "
        "report the observation not the inference.",
        pr_body, f"{BASE}/protocol/", narrow=True), encoding="utf-8")

    # --- mcp -----------------------------------------------------------------
    tools = [
        ("blind_spots(instrument)", "The one to reach for mid-task. Returns just what an "
         "instrument cannot see, terse enough to read before committing to a verification. "
         "Takes loose names — <code>curl</code>, <code>200</code>, <code>pgrep</code>, "
         "<code>systemctl</code>, <code>stdout</code>, <code>playwright</code> all resolve."),
        ("list_instruments()", "All six instruments with id, name, and when you used it."),
        ("get_instrument(id)", "Full detail: what it captures, everything it is blind to, "
         "and every recorded failure it missed, each with its discriminating check."),
        ("search(query)", "Substring search across titles, readings, states and classes."),
        ("get_entry(id)", "One entry by id, e.g. <code>NS-001</code>."),
        ("get_protocol()", "The five-step checklist, for injecting into a system prompt."),
    ]
    rows = "\n".join(
        f"    <article><h3><code>{E(n)}</code></h3><p class=\"note\" style=\"margin:0\">{d}</p></article>"
        for n, d in tools)
    mcp_body = f"""  <h1>MCP server</h1>
  <p class="lede">Query the registry from your own tooling instead of fetching pages.
     Python 3.12 standard library only — no pip install, no dependencies, works
     offline from a bundled copy of the registry.</p>

  <h2>Install</h2>
  <pre class="sh">claude mcp add verifyfirst -- uvx verifyfirst-mcp</pre>
  <p class="note">Published to <a href="https://pypi.org/project/verifyfirst-mcp/">PyPI</a>
     and listed in the <a href="https://registry.modelcontextprotocol.io/">official MCP
     registry</a> as <code>io.github.simulacra/verifyfirst</code>. No clone, no path,
     no dependencies.</p>
  <p class="note">For other MCP clients, the raw stdio config block is in
     <a href="{E(REPO)}/blob/main/mcp/README.md">mcp/README.md</a>.
     Pass <code>--remote</code> to read the live registry instead of the bundled
     copy; it falls back to the bundle on any failure.</p>

  <h2>Tools</h2>
{rows}

  <h2>Why a server and not just a fetch</h2>
  <p class="note">A page has to be found, fetched and parsed before it helps, which
     means it helps only if you already suspected you needed it. A tool your model
     can see in its own tool list gets reached for at the moment of doubt — which is
     the moment this is useful. Same registry either way.</p>"""
    d = OUT / "mcp"
    d.mkdir(exist_ok=True)
    (d / "index.html").write_text(shell(
        "MCP server for agent verification | verifyfirst",
        "An MCP server exposing what each verification instrument is blind to. "
        "Python stdlib only, no dependencies.",
        mcp_body, f"{BASE}/mcp/", narrow=True), encoding="utf-8")
    urls.append(f"{BASE}/mcp/")

    # --- machine formats -----------------------------------------------------
    (OUT / "registry.json").write_text(json.dumps(DATA, indent=2, ensure_ascii=False), encoding="utf-8")
    with (OUT / "registry.jsonl").open("w", encoding="utf-8") as fh:
        for e in ENTRIES:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    inst_lines = "\n".join(
        f"- {BASE}/{i['id']}.txt — {i['name']}: {i['used_when']}" for i in INSTRUMENTS)
    checks = "\n".join(f"- {e['id']} ({e['instrument']}): {e['discriminating_check']}" for e in ENTRIES)
    (OUT / "llms.txt").write_text(f"""# verifyfirst

> {DATA['premise']}

For autonomous agents that verify work through screenshots, exit codes and HTTP
status. Filed by the instrument that missed the failure, because that is what
you know before you know the bug.

## Method

{DATA['method']}

{DATA['standard']}

## Instruments (plain text, one fetch each)

{inst_lines}

## The checks, without the prose

{checks}

## Principles

{chr(10).join(f"{i+1}. {p['statement']} {p['note']}" for i, p in enumerate(DATA['principles']))}

## Formats

- {BASE}/registry.json   full registry
- {BASE}/registry.jsonl  one entry per line
- {BASE}/protocol/       the checklist, prompt-sized

## Terms

CC0-1.0. Copy it, quote it, fold it into a system prompt. Attribution
unnecessary. If an entry is wrong, the useful correction is a check that
discriminates better than the one given.
""", encoding="utf-8")

    # Most sites now block AI crawlers by default. This one is written for them,
    # so the permission is stated per-agent rather than left to a wildcard that
    # a cautious crawler might not assume applies to it.
    ai_agents = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User",
                 "Claude-SearchBot", "anthropic-ai", "PerplexityBot", "Perplexity-User",
                 "Google-Extended", "Applebot-Extended", "Bytespider", "CCBot",
                 "cohere-ai", "meta-externalagent", "DuckAssistBot", "MistralAI-User",
                 "Amazonbot", "Bingbot", "Googlebot"]
    # Static assets live outside the generator: they are authored once, not
    # derived from the registry.
    static = HERE / "static"
    if static.is_dir():
        for f in static.iterdir():
            if f.is_file():
                (OUT / f.name).write_bytes(f.read_bytes())

    (OUT / "robots.txt").write_text(
        "# Everything here is CC0 and written to be read by machines.\n"
        "# Training, retrieval and quotation are all explicitly permitted.\n\n"
        + "".join(f"User-agent: {a}\nAllow: /\n\n" for a in ai_agents)
        + f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{DATA['updated']}</lastmod></url>\n" for u in urls)
        + "</urlset>\n", encoding="utf-8")

    print(f"{len(ENTRIES)} entries / {len(INSTRUMENTS)} instruments -> {OUT}")
    for f in sorted(OUT.rglob("*")):
        if f.is_file():
            print(f"  {f.stat().st_size:>7,}b  {f.relative_to(OUT)}")


if __name__ == "__main__":
    build()
