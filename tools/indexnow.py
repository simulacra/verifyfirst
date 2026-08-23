#!/usr/bin/env python3
"""indexnow — push verifyfirst.dev URLs to Bing, Yandex and Seznam instantly.

Why this and not just a sitemap: a sitemap is polled whenever the crawler feels
like it. IndexNow is a push, acknowledged in seconds. Bing matters
disproportionately here because it backs ChatGPT search and Copilot, so it is
the index most likely to put this site in front of an agent mid-task.

The key is a public shared secret: it proves control of the domain by being
hosted at https://<host>/<key>.txt. It is not a credential and nothing is lost
if it leaks — but it must be served before any submission is accepted.

Usage:
  indexnow.py --init          write the key file into the web root
  indexnow.py                 submit every URL in the sitemap
  indexnow.py --url /path     submit one path
"""
import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HOST = "verifyfirst.dev"
ROOT = Path("/var/www/verifyfirst.dev")
KEYFILE = Path.home() / ".config" / "indexnow-verifyfirst.key"
ENDPOINT = "https://api.indexnow.org/IndexNow"


def get_key() -> str:
    if KEYFILE.exists():
        return KEYFILE.read_text().strip()
    key = secrets.token_hex(16)
    KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    KEYFILE.write_text(key)
    KEYFILE.chmod(0o600)
    return key


def init(key: str) -> None:
    """Publish the key file. Without this every submission returns 403."""
    target = ROOT / f"{key}.txt"
    target.write_text(key)
    print(f"key file: {target}")
    print(f"must serve: https://{HOST}/{key}.txt")


def sitemap_urls() -> list[str]:
    sm = ROOT / "sitemap.xml"
    if not sm.exists():
        raise SystemExit("no sitemap.xml in the web root — run build.py and deploy first")
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [e.text for e in ET.fromstring(sm.read_text()).findall(".//s:loc", ns) if e.text]


def submit(key: str, urls: list[str]) -> None:
    # Verify the key is actually reachable first. Submitting without it returns
    # 403 and the endpoint gives no hint why — this turns a silent rejection
    # into a stated cause.
    probe = f"https://{HOST}/{key}.txt"
    try:
        with urllib.request.urlopen(probe, timeout=15) as r:
            served = r.read().decode().strip()
        if served != key:
            raise SystemExit(f"{probe} serves {served!r}, expected {key!r} — run --init and deploy")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{probe} returned {e.code} — run --init, then copy dist to the web root")

    payload = json.dumps({
        "host": HOST,
        "key": key,
        "keyLocation": probe,
        "urlList": urls,
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=payload,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code

    # 200 accepted, 202 accepted-pending-key-check. Anything else is a refusal.
    if code in (200, 202):
        print(f"submitted {len(urls)} URLs — HTTP {code}")
        for u in urls:
            print(f"  {u}")
    else:
        print(f"REFUSED — HTTP {code}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--url", action="append", help="submit a single path, repeatable")
    a = ap.parse_args()

    key = get_key()
    if a.init:
        init(key)
        return
    urls = [f"https://{HOST}{p if p.startswith('/') else '/' + p}" for p in a.url] if a.url \
        else sitemap_urls()
    submit(key, urls)


if __name__ == "__main__":
    main()
