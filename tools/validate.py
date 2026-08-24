#!/usr/bin/env python3
"""validate — check registry.json before it becomes a website.

Standard library only, so CI needs no install step.

Two layers. The structural rules mirror schema/registry.schema.json: fields,
formats, cross-references. The editorial rules are the ones a schema cannot
express, and they are the reason this file exists — above all, that a
discriminating check actually discriminates. "Be careful" satisfies every type
constraint and is worth nothing.

Exit 0 clean, 1 on any error. Warnings never fail the build.

Usage:
  validate.py [registry.json]
  validate.py --candidates candidates/batch-03.json   # check a batch pre-merge
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ENTRY_REQUIRED = [
    "id", "instrument", "title", "class", "false_reading", "true_state",
    "why_blind", "discriminating_check", "cost_of_missing", "generalises_to",
    "provenance", "added",
]
ENTRY_OPTIONAL = ["mitigation", "source", "title_short"]

ID_RE = re.compile(r"^NS-\d{3}$")
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# Phrases that describe an attitude rather than an observation. A check must
# name something you can look at whose result differs between the two
# hypotheses; none of these do.
NON_CHECKS = [
    "be careful", "look closely", "look more closely", "pay attention",
    "double check", "double-check", "make sure", "ensure that", "remember to",
    "keep in mind", "verify carefully", "check carefully", "review the code",
    "test thoroughly", "consider whether", "think about",
]

# A check should point at something inspectable. This is a weak signal, so it
# only ever warns.
CHECK_HINTS = [
    "(", "--", "/", "$", "compare", "diff", "hash", "print", "read", "query",
    "inspect", "ask", "count", "curl", "grep", "stat", "ps ", "systemctl",
    "getcomputedstyle", "console.log", "python", "git ", "returns", "exits",
]


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


def check_entry(e: dict, r: Report, instrument_ids: set[str], seen: dict) -> None:
    eid = e.get("id", "<no id>")

    for f in ENTRY_REQUIRED:
        if not str(e.get(f, "")).strip():
            r.err(eid, f"missing required field '{f}'")

    extra = set(e) - set(ENTRY_REQUIRED) - set(ENTRY_OPTIONAL)
    if extra:
        r.err(eid, f"unknown field(s): {', '.join(sorted(extra))}")

    if not ID_RE.match(eid):
        r.err(eid, "id must look like NS-001")
    elif eid in seen:
        r.err(eid, "duplicate id")
    else:
        seen[eid] = e

    inst = e.get("instrument", "")
    if inst and inst not in instrument_ids:
        r.err(eid, f"instrument '{inst}' is not one of: {', '.join(sorted(instrument_ids))}")

    if e.get("class") and not SLUG_RE.match(e["class"]):
        r.err(eid, f"class '{e['class']}' should be kebab-case")

    prov = e.get("provenance")
    if prov not in ("observed", "documented"):
        r.err(eid, "provenance must be 'observed' or 'documented'")
    if prov == "documented" and not e.get("source"):
        r.err(eid, "provenance is 'documented' but no source is cited")
    if e.get("source") and not e["source"].startswith("https://"):
        r.err(eid, "source must be an https URL")

    # --- the editorial rules -------------------------------------------------
    chk = e.get("discriminating_check", "")
    low = chk.lower()
    for phrase in NON_CHECKS:
        if phrase in low:
            r.err(eid, f"check contains {phrase!r} — that is an attitude, not an "
                       f"observation. State what to look at and how the two "
                       f"hypotheses differ in its result.")
            break
    if chk and len(chk) < 25:
        r.err(eid, f"check is {len(chk)} chars — too short to name an observation")
    if chk and not any(h in low for h in CHECK_HINTS):
        r.warn(eid, "check names no command, path or comparison — confirm it is "
                    "something a reader can actually run or inspect")

    fr = e.get("false_reading", "")
    if fr and "conclusion drawn" not in fr.lower():
        r.warn(eid, "false_reading usually ends with 'Conclusion drawn: ...' — the "
                    "wrong inference is the point of the field")

    ts = e.get("title_short")
    if ts:
        if len(ts) > 60:
            r.err(eid, f"title_short is {len(ts)} chars, must be <= 60")
        if ts.rstrip(" .…") and e.get("title", "").startswith(ts.rstrip(" .…")[:24]) \
                and len(ts) < len(e.get("title", "")) and ts.endswith(("...", "…")):
            r.err(eid, "title_short looks like a truncation; write a short form instead")
    elif len(e.get("title", "")) > 60:
        r.warn(eid, f"title is {len(e['title'])} chars with no title_short — page "
                    f"titles will be cut")

    if e.get("added") and not re.match(r"^\d{4}-\d{2}-\d{2}$", e["added"]):
        r.err(eid, "added must be YYYY-MM-DD")

    if e.get("title", "").endswith("?"):
        r.warn(eid, "title is a question; entries state the mechanism")


def validate(data: dict, r: Report, full: bool = True) -> None:
    instruments = data.get("instruments", [])
    instrument_ids = {i.get("id") for i in instruments}

    if full:
        for f in ["site", "version", "updated", "premise", "method", "standard",
                  "license", "instruments", "entries", "principles"]:
            if f not in data:
                r.err("registry", f"missing top-level field '{f}'")
        if data.get("license") != "CC0-1.0":
            r.err("registry", "license must be CC0-1.0")
        if not re.match(r"^\d+\.\d+\.\d+$", str(data.get("version", ""))):
            r.err("registry", "version must be semver")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(data.get("updated", ""))):
            r.err("registry", "updated must be YYYY-MM-DD")

        for i in instruments:
            iid = i.get("id", "<no id>")
            for f in ["id", "name", "short", "used_when", "captures", "blind_to"]:
                if not i.get(f):
                    r.err(f"instrument {iid}", f"missing '{f}'")
            if len(i.get("blind_to", [])) < 2:
                r.err(f"instrument {iid}", "needs at least two blind spots")

    seen: dict = {}
    for e in data.get("entries", []):
        check_entry(e, r, instrument_ids, seen)

    ids = set(seen)
    if full:
        # Every entry should be reachable from the symptom index. One that is
        # not can only be found by someone already browsing the instrument it
        # belongs to, which is the reader who least needs it.
        reachable = set()
        for s in data.get("symptoms", []):
            for f in ["symptom", "note", "entries"]:
                if not s.get(f):
                    r.err(f"symptom {s.get('symptom', '?')!r}", f"missing '{f}'")
            for ref in s.get("entries", []):
                if ref not in ids:
                    r.err(f"symptom {s.get('symptom')!r}", f"references unknown entry {ref}")
                reachable.add(ref)
        orphans = sorted(ids - reachable)
        if orphans:
            r.warn("symptoms", f"{len(orphans)} entr{'y' if len(orphans)==1 else 'ies'} "
                               f"not reachable by symptom: {', '.join(orphans)}")

        # Recipes are content and get the same treatment: every step must name
        # a command and point at the entry it guards against, or it is advice.
        for rec in data.get("recipes", []):
            rid = rec.get("id", "<no id>")
            where = f"recipe {rid}"
            for f in ["id", "task", "when", "steps"]:
                if not rec.get(f):
                    r.err(where, f"missing '{f}'")
            if rid != "<no id>" and not SLUG_RE.match(rid):
                r.err(where, "id should be kebab-case")
            for i, st in enumerate(rec.get("steps", []), 1):
                for f in ["check", "how", "guards_against"]:
                    if not st.get(f):
                        r.err(where, f"step {i} missing '{f}'")
                low = str(st.get("check", "")).lower()
                for phrase in NON_CHECKS:
                    if phrase in low:
                        r.err(where, f"step {i} says {phrase!r} — a step must name an "
                                     f"observation, not an attitude")
                        break
                for g in st.get("guards_against", []):
                    if g not in ids:
                        r.err(where, f"step {i} guards against unknown entry {g}")

        counts: dict = {}
        for e in data.get("entries", []):
            counts[e.get("instrument")] = counts.get(e.get("instrument"), 0) + 1
        for iid in sorted(instrument_ids):
            if counts.get(iid, 0) == 0:
                r.err(f"instrument {iid}", "has no entries")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="registry.json")
    ap.add_argument("--candidates", metavar="FILE",
                    help="validate a bare array of candidate entries against the "
                         "live registry, before merging")
    a = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    reg_path = Path(a.path) if Path(a.path).is_absolute() else root / a.path
    try:
        data = json.loads(reg_path.read_text())
    except FileNotFoundError:
        print(f"no registry at {reg_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"{reg_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    r = Report()

    if a.candidates:
        cand = json.loads(Path(a.candidates).read_text())
        if not isinstance(cand, list):
            print("--candidates expects a JSON array of entries", file=sys.stderr)
            return 1
        existing = {e["id"] for e in data.get("entries", [])}
        seen: dict = {}
        iids = {i["id"] for i in data.get("instruments", [])}
        for e in cand:
            check_entry(e, r, iids, seen)
            if e.get("id") in existing:
                r.err(e.get("id", "?"), "id already exists in the registry")
        subject = f"{len(cand)} candidate entries from {a.candidates}"
    else:
        validate(data, r, full=True)
        subject = (f"{len(data.get('entries', []))} entries, "
                   f"{len(data.get('instruments', []))} instruments, "
                   f"{len(data.get('symptoms', []))} symptoms")

    for w in r.warnings:
        print(f"warn  {w}")
    for e in r.errors:
        print(f"ERROR {e}", file=sys.stderr)

    print()
    if r.errors:
        print(f"FAILED — {len(r.errors)} error(s), {len(r.warnings)} warning(s) "
              f"in {subject}", file=sys.stderr)
        return 1
    print(f"OK — {subject}; {len(r.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
