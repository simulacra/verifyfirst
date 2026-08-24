#!/usr/bin/env python3
"""traffic — who actually fetched verifyfirst.dev.

GA4 counts humans: it needs a JS runtime, and almost no agent fetch has one.
This reads Caddy's access log instead, which counts every request including
the ones GA is structurally blind to. Using only GA on a site written for
agents would be NS-004 in miniature — a plausible reading of the wrong thing.

Usage:
  traffic.py              last 7 days
  traffic.py --days 30
  traffic.py --paths      break down by URL instead of by client
"""
import argparse
import collections
import gzip
import json
import re
import time
from pathlib import Path

LOG_DIR = Path("/var/log/caddy")
LOG_GLOB = "verifyfirst.access.log*"

# Declared AI agents. Matched case-insensitively against the User-Agent.
AI_AGENTS = {
    "GPTBot": "OpenAI (training)",
    "OAI-SearchBot": "OpenAI (search)",
    "ChatGPT-User": "ChatGPT (user-initiated fetch)",
    "ClaudeBot": "Anthropic (training)",
    "Claude-User": "Claude (user-initiated fetch)",
    "Claude-SearchBot": "Anthropic (search)",
    "anthropic-ai": "Anthropic (legacy)",
    "PerplexityBot": "Perplexity",
    "Perplexity-User": "Perplexity (user-initiated)",
    "Google-Extended": "Google (AI training)",
    "GoogleOther": "Google (other)",
    "Applebot-Extended": "Apple (AI training)",
    "meta-externalagent": "Meta",
    "Bytespider": "ByteDance",
    "CCBot": "Common Crawl",
    "cohere-ai": "Cohere",
    "Amazonbot": "Amazon",
    "DuckAssistBot": "DuckDuckGo",
    "MistralAI-User": "Mistral",
}
# Generic automation: not identifiably an AI agent, but not a browser either.
TOOLING = ["curl", "wget", "python-requests", "httpx", "aiohttp", "node-fetch",
           "Go-http-client", "okhttp", "libwww-perl", "PostmanRuntime", "undici"]
SEARCH = ["Googlebot", "bingbot", "DuckDuckBot", "YandexBot", "Baiduspider",
          "Applebot", "facebookexternalhit", "Slackbot", "Twitterbot"]


# Paths that only exist on a marketing site. A client asking for these on a
# reference with nine pages is enumerating, not reading.
SCANNER_PATHS = {
    "/contact", "/contact-us", "/about", "/about-us", "/support", "/help",
    "/team", "/pricing", "/get-in-touch", "/reach-us", "/careers", "/blog",
    "/login", "/signup", "/admin", "/wp-admin", "/wp-login.php", "/.env",
    "/privacy", "/terms", "/services", "/products", "/faq",
}


def classify(ua: str) -> tuple[str, str]:
    """Return (bucket, label). Order matters: declared AI agents win over the
    generic tooling strings that some of them also contain."""
    low = ua.lower()
    for token, label in AI_AGENTS.items():
        if token.lower() in low:
            return "ai", label
    for token in SEARCH:
        if token.lower() in low:
            return "search", token
    for token in TOOLING:
        if token.lower() in low:
            return "tooling", token
    if "mozilla" in low or "safari" in low:
        return "browser", "browser"
    if not ua or ua == "-":
        return "unknown", "(no user-agent)"
    return "unknown", ua[:48]


def real_client_ip(req: dict) -> str:
    """The address that actually made the request.

    Behind a proxy, Caddy's client_ip is the edge that connected, so counting
    it would show a handful of Cloudflare addresses making every request and
    the scanner detection would never fire. Cloudflare sets CF-Connecting-IP,
    and Caddy already records it — no server configuration needed.

    This is only safe because the log is written by our own origin: a forged
    CF-Connecting-IP from a direct connection would be recorded too. Requests
    that did not arrive through Cloudflare are identified by the absence of
    Cf-Ray, and fall back to the connection address.
    """
    h = req.get("headers", {})
    via_cloudflare = bool(h.get("Cf-Ray") or h.get("CF-Ray"))
    if via_cloudflare:
        cf = h.get("Cf-Connecting-Ip") or h.get("CF-Connecting-IP")
        if cf:
            return cf[0]
    return req.get("client_ip", "?")


def read_lines(days: int):
    cutoff = time.time() - days * 86400
    files = sorted(LOG_DIR.glob(LOG_GLOB))
    if not files:
        raise SystemExit(f"no log yet at {LOG_DIR}/{LOG_GLOB} — has the site had traffic?")
    for f in files:
        opener = gzip.open if f.suffix == ".gz" else open
        try:
            with opener(f, "rt", errors="replace") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("ts", 0) < cutoff:
                        continue
                    yield r
        except PermissionError:
            raise SystemExit(f"cannot read {f} — run with sudo, or add yourself to the "
                             f"group that owns it")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--paths", action="store_true")
    a = ap.parse_args()

    # A user-agent is a claim the client makes about itself, not evidence.
    # Anything spoofing a browser lands in the browser bucket, so track what
    # each client asked for and demote the ones that only probe for pages this
    # site has never had.
    per_ip_scanner = collections.Counter()
    per_ip_total = collections.Counter()
    referrers = collections.Counter()
    via_cf = 0

    buckets = collections.Counter()
    labels = collections.Counter()
    paths = collections.Counter()
    ai_paths = collections.Counter()
    status = collections.Counter()
    total = 0

    for r in read_lines(a.days):
        total += 1
        ua = (r.get("request", {}).get("headers", {}).get("User-Agent") or ["-"])[0]
        uri = r.get("request", {}).get("uri", "-")
        bucket, label = classify(ua)
        client = real_client_ip(r.get("request", {}))
        per_ip_total[client] += 1
        if uri.rstrip("/").lower() in SCANNER_PATHS:
            per_ip_scanner[client] += 1
        referer = (r.get("request", {}).get("headers", {}).get("Referer") or [""])[0]
        if referer and "verifyfirst.dev" not in referer:
            referrers[referer.split("?")[0][:60]] += 1
        if (r.get("request", {}).get("headers", {}).get("Cf-Ray")):
            via_cf += 1
        buckets[bucket] += 1
        labels[(bucket, label)] += 1
        paths[uri] += 1
        status[r.get("status", 0)] += 1
        if bucket == "ai":
            ai_paths[uri] += 1

    if not total:
        print(f"no requests in the last {a.days} days")
        return

    print(f"verifyfirst.dev — last {a.days} days — {total:,} requests\n")
    order = ["ai", "tooling", "search", "browser", "unknown"]
    for b in order:
        if buckets[b]:
            print(f"  {b:<9} {buckets[b]:>7,}  {buckets[b]/total*100:5.1f}%")

    if a.paths:
        print("\ntop paths")
        for u, n in paths.most_common(20):
            print(f"  {n:>6,}  {u}")
        print("\ntop paths — AI agents only")
        for u, n in ai_paths.most_common(20):
            print(f"  {n:>6,}  {u}")
    else:
        print("\nAI agents")
        rows = [(n, l) for (b, l), n in labels.items() if b == "ai"]
        if not rows:
            print("  none yet")
        for n, l in sorted(rows, reverse=True):
            print(f"  {n:>6,}  {l}")
        print("\nother clients")
        rows = [(n, f"{b}/{l}") for (b, l), n in labels.items() if b != "ai"]
        for n, l in sorted(rows, reverse=True)[:12]:
            print(f"  {n:>6,}  {l}")

    if via_cf:
        print(f"\n  {via_cf:,} of {total:,} requests arrived through Cloudflare; "
              f"client addresses for those come from CF-Connecting-IP")

    scanners = {ip for ip, n in per_ip_scanner.items() if n >= 3}
    if scanners:
        hits = sum(per_ip_total[ip] for ip in scanners)
        print(f"\nprobable scanners: {len(scanners)} client(s), {hits:,} requests "
              f"({hits/total*100:.1f}%) — they asked for pages this site has never had, "
              f"while claiming to be browsers")

    if referrers:
        print("\nreferrers (real discovery)")
        for u, n in referrers.most_common(8):
            print(f"  {n:>6,}  {u}")

    bad = {k: v for k, v in status.items() if k >= 400}
    if bad:
        print("\nerrors")
        for k, v in sorted(bad.items()):
            print(f"  {k}: {v:,}")


if __name__ == "__main__":
    main()
