#!/usr/bin/env python3
"""
verifyfirst MCP server — stdio transport, JSON-RPC 2.0, newline-delimited.

Python 3.12 standard library only. No third-party dependencies, no venv.

The registry it serves answers one question: the instrument you are about to
verify through — what is it structurally unable to see?

Usage:
    python3 server.py              # serve the bundled local registry (offline)
    python3 server.py --remote     # fetch https://verifyfirst.dev/registry.json,
                                   # falling back to the bundled copy on failure
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from typing import Any

SERVER_NAME = "verifyfirst"
SERVER_VERSION = "1.5.0"

# Protocol versions this server knows how to speak. If the client asks for one
# of these we echo it back; otherwise we answer with our preferred version and
# let the client decide whether it can proceed.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
PREFERRED_PROTOCOL_VERSION = "2025-06-18"

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_REGISTRY = os.path.join(HERE, "registry.json")
REMOTE_REGISTRY_URL = "https://verifyfirst.dev/registry.json"

# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# --------------------------------------------------------------------------
# Registry loading
# --------------------------------------------------------------------------

def log(msg: str) -> None:
    """Diagnostics go to stderr. stdout is the protocol channel and nothing else."""
    print(f"[{SERVER_NAME}] {msg}", file=sys.stderr, flush=True)


def load_local_registry() -> dict[str, Any]:
    with open(LOCAL_REGISTRY, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_remote_registry(timeout: float = 10.0) -> dict[str, Any]:
    import urllib.request

    req = urllib.request.Request(
        REMOTE_REGISTRY_URL,
        headers={"User-Agent": f"{SERVER_NAME}-mcp/{SERVER_VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_registry(remote: bool = False) -> tuple[dict[str, Any], str]:
    """Returns (registry, source_description)."""
    if remote:
        try:
            reg = load_remote_registry()
            log(f"loaded remote registry from {REMOTE_REGISTRY_URL}")
            return reg, REMOTE_REGISTRY_URL
        except Exception as exc:  # noqa: BLE001 - any network/parse failure falls back
            log(f"remote fetch failed ({exc!r}); falling back to bundled copy")
    reg = load_local_registry()
    log(f"loaded bundled registry from {LOCAL_REGISTRY}")
    return reg, LOCAL_REGISTRY


# --------------------------------------------------------------------------
# Instrument resolution
# --------------------------------------------------------------------------

# Agents will not always name the instrument the way the registry does. These
# aliases let "curl", "200", "ps", "journalctl" and friends resolve to the right
# instrument instead of returning nothing useful.
ALIASES: dict[str, str] = {
    "screenshot": "screenshot",
    "screenshots": "screenshot",
    "image": "screenshot",
    "images": "screenshot",
    "render": "screenshot",
    "rendered-image": "screenshot",
    "rendered": "screenshot",
    "visual": "screenshot",
    "visual-check": "screenshot",
    "browser": "screenshot",
    "headless-browser": "screenshot",
    "puppeteer": "screenshot",
    "playwright": "screenshot",
    "chrome": "screenshot",
    "chromium": "screenshot",
    "looking-at-it": "screenshot",

    "exit-code": "exit-code",
    "exitcode": "exit-code",
    "exit-status": "exit-code",
    "return-code": "exit-code",
    "returncode": "exit-code",
    "status": "exit-code",
    "$?": "exit-code",
    "shell": "exit-code",
    "command": "exit-code",
    "bash": "exit-code",
    "cli": "exit-code",
    "it-exited-zero": "exit-code",

    "http-response": "http-response",
    "http": "http-response",
    "https": "http-response",
    "status-code": "http-response",
    "http-status": "http-response",
    "response": "http-response",
    "curl": "http-response",
    "wget": "http-response",
    "fetch": "http-response",
    "200": "http-response",
    "request": "http-response",
    "url": "http-response",

    "file-on-disk": "file-on-disk",
    "file": "file-on-disk",
    "files": "file-on-disk",
    "disk": "file-on-disk",
    "config": "file-on-disk",
    "config-file": "file-on-disk",
    "source": "file-on-disk",
    "source-code": "file-on-disk",
    "stylesheet": "file-on-disk",
    "css": "file-on-disk",
    "read": "file-on-disk",
    "cat": "file-on-disk",
    "grep": "file-on-disk",

    "process-list": "process-list",
    "process": "process-list",
    "processes": "process-list",
    "ps": "process-list",
    "pgrep": "process-list",
    "pkill": "process-list",
    "systemctl": "process-list",
    "systemd": "process-list",
    "service-status": "process-list",
    "top": "process-list",

    "log-output": "log-output",
    "log": "log-output",
    "logs": "log-output",
    "logging": "log-output",
    "stdout": "log-output",
    "stderr": "log-output",
    "output": "log-output",
    "console": "log-output",
    "journalctl": "log-output",
    "journal": "log-output",
    "dmesg": "log-output",
    "terminal-output": "log-output",
}


def normalise(text: str) -> str:
    return text.strip().lower().replace("_", "-").replace(" ", "-").replace("/", "-")


class Registry:
    def __init__(self, data: dict[str, Any], source: str) -> None:
        self.data = data
        self.source = source
        self.instruments: list[dict[str, Any]] = data.get("instruments", [])
        self.entries: list[dict[str, Any]] = data.get("entries", [])
        self.principles: list[dict[str, Any]] = data.get("principles", [])
        self.symptoms: list[dict[str, Any]] = data.get("symptoms", [])
        self.recipes: list[dict[str, Any]] = data.get("recipes", [])
        self._by_id = {i["id"]: i for i in self.instruments}

    def instrument_ids(self) -> list[str]:
        return [i["id"] for i in self.instruments]

    def resolve_instrument(self, raw: str) -> dict[str, Any] | None:
        if not raw:
            return None
        key = normalise(raw)
        if key in self._by_id:
            return self._by_id[key]
        alias = ALIASES.get(key)
        if alias and alias in self._by_id:
            return self._by_id[alias]
        # Substring pass: "the exit code of the command" -> exit-code
        for iid in self._by_id:
            if iid in key:
                return self._by_id[iid]
        for alias_key, iid in ALIASES.items():
            if len(alias_key) >= 4 and alias_key in key:
                return self._by_id.get(iid)
        # Last pass: match against the human-readable name.
        for inst in self.instruments:
            if key in normalise(inst.get("name", "")):
                return inst
        return None

    def match_symptoms(self, text: str, limit: int = 3) -> list[tuple[float, dict[str, Any]]]:
        """Rank symptoms against a free-text description.

        Callers describe what they are seeing in their own words, so exact
        matching would miss almost every real query. Score on token overlap
        against the symptom, its note, and the false readings of the entries it
        points at — the false readings are phrased the way someone describes a
        problem, which makes them the most useful part of the haystack.
        """
        want = tokens(text)
        if not want:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for sy in self.symptoms:
            hay = sy.get("symptom", "") + " " + sy.get("note", "")
            for eid in sy.get("entries", []):
                e = self.entry(eid)
                if e:
                    hay += " ".join((
                        " ", e.get("false_reading", ""), e.get("title", ""),
                        e.get("discriminating_check", ""), e.get("class", "")))
            have = tokens(hay)
            if not have:
                continue
            hits = want & have
            if not hits:
                continue
            title_words = tokens(sy.get("symptom", ""))
            # One incidental word is not a match: "zzzqqq unrelated gibberish"
            # collides with the class name "unrelated-precondition" and would
            # otherwise return the deploy symptom with a straight face. But a
            # single hit on the symptom's OWN wording is a real match — "blank"
            # against "the page renders blank" needs no corroboration.
            if len(hits) < 2 and len(want) > 1 and not (want & title_words):
                continue
            # Favour covering the caller's words over merely being a long entry.
            score = len(hits) / len(want)
            score += 1.2 * len(want & title_words) / max(1, len(title_words))
            scored.append((score, sy))
        scored.sort(key=lambda t: -t[0])
        return scored[:limit]

    def match_recipes(self, text: str, limit: int = 2) -> list[dict[str, Any]]:
        """Rank task recipes against a description of what was just done.

        Same shape as match_symptoms, scored against the task line, the
        situation it covers, and the wording of its own checks — a caller
        saying "pushed the new build to the server" should reach the deploy
        recipe without using the word deploy.
        """
        want = tokens(text)
        if not want:
            return []
        scored = []
        for r in self.recipes:
            hay = r.get("task", "") + " " + r.get("when", "")
            for st in r.get("steps", []):
                hay += " " + st.get("check", "") + " " + st.get("how", "")
            have = tokens(hay)
            hits = want & have
            if not hits:
                continue
            title_words = tokens(r.get("task", "") + " " + r.get("when", ""))
            if len(hits) < 2 and len(want) > 1 and not (want & title_words):
                continue
            score = len(hits) / len(want)
            score += 1.2 * len(want & title_words) / max(1, len(title_words))
            scored.append((score, r))
        scored.sort(key=lambda t: -t[0])
        return [r for _, r in scored[:limit]]

    def entries_for(self, instrument_id: str) -> list[dict[str, Any]]:
        return [e for e in self.entries if e.get("instrument") == instrument_id]

    def entry(self, entry_id: str) -> dict[str, Any] | None:
        want = entry_id.strip().upper()
        for e in self.entries:
            if e.get("id", "").upper() == want:
                return e
        return None

    def entry_ids(self) -> list[str]:
        return [e.get("id", "") for e in self.entries]


def stem(word: str) -> str:
    """Crude suffix stripping, deliberately not a real stemmer.

    Without it "find" and "finds" are different tokens, and a query like
    "pgrep cannot find my daemon" misses the symptom literally named "a search
    for a process finds something unexpected". Over-stemming would collapse
    distinct words, so this only touches the endings that actually cost matches.
    """
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS}


STOPWORDS = {
    "a", "an", "the", "is", "it", "its", "i", "my", "we", "and", "or", "but", "of",
    "to", "in", "on", "at", "for", "with", "that", "this", "was", "were", "be",
    "been", "am", "are", "not", "no", "do", "does", "did", "have", "has", "had",
    "so", "if", "then", "there", "when", "what", "why", "how", "me", "you",
}

REGISTRY: Registry | None = None


# --------------------------------------------------------------------------
# Rendering helpers — the text a model actually reads
# --------------------------------------------------------------------------

def render_instrument_summary(inst: dict[str, Any], entry_count: int) -> str:
    return (
        f"{inst['id']}  —  {inst['name']}\n"
        f"  used when: {inst['used_when']}\n"
        f"  recorded failures: {entry_count}"
    )


def render_entry(e: dict[str, Any], full: bool = True) -> str:
    lines = [
        f"{e.get('id')}  [{e.get('instrument')}]  ({e.get('class')})",
        f"  {e.get('title')}",
        f"  FALSE READING: {e.get('false_reading')}",
        f"  TRUE STATE:    {e.get('true_state')}",
    ]
    if full:
        if e.get("why_blind"):
            lines.append(f"  WHY BLIND:     {e['why_blind']}")
        if e.get("discriminating_check"):
            lines.append(f"  CHECK:         {e['discriminating_check']}")
        if e.get("cost_of_missing"):
            lines.append(f"  COST:          {e['cost_of_missing']}")
        if e.get("mitigation"):
            lines.append(f"  MITIGATION:    {e['mitigation']}")
        if e.get("generalises_to"):
            lines.append(f"  GENERALISES:   {e['generalises_to']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Tool definitions
# --------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_instruments",
        "description": (
            "List the six verification instruments an agent can observe a system through: "
            "screenshot, exit-code, http-response, file-on-disk, process-list, log-output. "
            "Each entry says what the instrument is used for so you can identify which one "
            "you are actually relying on right now. Start here when you are not sure how to "
            "name the instrument you just used, then call blind_spots on it."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "blind_spots",
        "description": (
            "PRE-FLIGHT CHECK. Call this in the moment before you claim a task is done or a "
            "fix is verified. Give it the instrument you are trusting — a screenshot, an exit "
            "code, an HTTP status, a file you read, a process list, a log — and it returns the "
            "terse list of failure modes that instrument is structurally incapable of showing "
            "you. A screenshot cannot see time. An exit code cannot see semantics. A 200 cannot "
            "see staleness. A config file cannot see what the running process loaded. Reading "
            "this list takes seconds and is the difference between 'the command exited zero' and "
            "'the change is live'. Accepts loose names: 'curl', 'ps', 'journalctl', 'I looked at "
            "the screenshot' all resolve. Use get_instrument afterwards for the worked examples."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": (
                        "The instrument you are verifying through. Canonical ids: screenshot, "
                        "exit-code, http-response, file-on-disk, process-list, log-output. "
                        "Common aliases also work (curl, 200, ps, pgrep, systemctl, journalctl, "
                        "stdout, config, browser, playwright)."
                    ),
                }
            },
            "required": ["instrument"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_instrument",
        "description": (
            "Full dossier on one instrument: what it genuinely captures, everything it is blind "
            "to, and every recorded real-world failure it missed — each with the false reading, "
            "the true state, and one concrete check that separates them. Use this after "
            "blind_spots when a listed blind spot might apply to what you are doing and you want "
            "the specific command or expression that would settle it. Every failure here was "
            "actually observed and diagnosed; none are hypothetical."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": (
                        "Instrument id: screenshot, exit-code, http-response, file-on-disk, "
                        "process-list, or log-output. Aliases are accepted."
                    ),
                }
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search",
        "description": (
            "Case-insensitive substring search across every recorded failure's title, false "
            "reading, true state, and failure class. Use it when you have a symptom rather than "
            "an instrument: 'blank page', 'cache', 'font', 'hang', 'oom', 'systemctl', 'opacity', "
            "'no output'. Also useful for checking whether a surprising behaviour you just hit is "
            "a known instrument artifact before you spend rounds tuning against it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring to look for, e.g. 'cache', 'blank', 'font', 'oom'.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_entry",
        "description": (
            "Retrieve one recorded failure in full by its id, e.g. 'NS-001'. Returns the false "
            "reading, the true state, why the instrument could not separate them, the "
            "discriminating check, the cost of missing it, and what it generalises to. Use after "
            "search or get_instrument surfaces an id you want the complete account of."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Entry id such as NS-001 through NS-014.",
                }
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "from_symptom",
        "description": (
            "Start here when something is wrong but you do not yet know why. Describe what you "
            "are actually observing, in your own words — 'the page is blank', 'deploy ran but "
            "nothing changed', 'API returns 200 but the data is wrong', 'the service says active "
            "but is not serving', 'the command hangs and never returns' — and this returns the "
            "recorded failures that produce that exact appearance, each with the one check that "
            "tells them apart. This is the symptom-first door into the registry; blind_spots is "
            "the instrument-first one. Use this when you have a symptom, and blind_spots when you "
            "are about to verify something and want to know what your method cannot see."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "What you are seeing, in plain words. A sentence works better than a "
                        "keyword: 'screenshot shows a blank page in headless chrome'."
                    ),
                }
            },
            "required": ["description"],
            "additionalProperties": False,
        },
    },
    {
        "name": "before_claiming",
        "description": (
            "Call this immediately before reporting a task complete — before writing "
            "'done', 'fixed', 'deployed', 'working' or 'the tests pass'. Describe what you "
            "just did ('deployed a static site', 'restarted the service', 'changed a config "
            "file', 'ran the test suite', 'fetched a URL', 'published a package') and it "
            "returns an ordered preflight: the specific checks that would catch this task "
            "failing silently, each with the command to run and the recorded failure it "
            "guards against. Unlike from_symptom, nothing has to have gone wrong yet — this "
            "is for the moment when you believe the work succeeded."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "What you just did, in plain words. 'I copied the built "
                                   "files to the web root' works as well as 'deploy'.",
                }
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_protocol",
        "description": (
            "The five-step verification checklist to run before reporting any work as complete: "
            "name the instrument, say what it cannot see, run one check that could actually come "
            "out either way, report the observation rather than the inference, and prefer "
            "resolved values over authored ones. Returns the checklist plus the underlying "
            "principles. Call it once at the start of a verification pass, or any time you are "
            "about to write the words 'done', 'fixed', 'working', or 'deployed'."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------

PROTOCOL_STEPS = [
    (
        "Name the instrument.",
        "State explicitly how you are observing this: a screenshot, an exit code, an HTTP "
        "status, a file you read, a process list, a log. You cannot reason about a blind spot "
        "you have not named an instrument for.",
    ),
    (
        "Say what it cannot see.",
        "Every instrument is structurally silent about something. Call blind_spots on the "
        "instrument you just named and state which of its blind spots could plausibly apply "
        "to this change.",
    ),
    (
        "Run one check that could fail.",
        "A check is only diagnostic if it returns different output under the two hypotheses. "
        "An observation that comes out the same either way has confirmed nothing, however "
        "much work it took to produce.",
    ),
    (
        "Report the observation, not the inference.",
        "'The unit is active and curl returned the new hash' can be verified by a reader. "
        "'It works' cannot. Write down what you saw, not what you concluded from it.",
    ),
    (
        "Prefer resolved values over authored ones.",
        "Configuration records intent; computed styles, running processes and served bytes "
        "record outcome. When they disagree, only one of them is what users experience.",
    ),
]


def tool_list_instruments(reg: Registry, args: dict[str, Any]) -> str:
    lines = [
        f"{len(reg.instruments)} verification instruments "
        f"(registry v{reg.data.get('version', '?')}, updated {reg.data.get('updated', '?')})",
        "",
    ]
    for inst in reg.instruments:
        lines.append(render_instrument_summary(inst, len(reg.entries_for(inst["id"]))))
        lines.append("")
    lines.append("Next: blind_spots(instrument=<id>) for what it cannot see.")
    return "\n".join(lines)


def tool_blind_spots(reg: Registry, args: dict[str, Any]) -> str:
    raw = args.get("instrument")
    if not isinstance(raw, str) or not raw.strip():
        raise ToolInputError(
            "blind_spots requires a non-empty 'instrument' string. "
            f"Known ids: {', '.join(reg.instrument_ids())}."
        )
    inst = reg.resolve_instrument(raw)
    if inst is None:
        raise ToolInputError(
            f"Unknown instrument {raw!r}. Known ids: {', '.join(reg.instrument_ids())}. "
            "Call list_instruments to see what each one covers."
        )
    n = len(reg.entries_for(inst["id"]))
    lines = [f"{inst['id']} ({inst['name']}) is blind to:"]
    for b in inst.get("blind_to", []):
        lines.append(f"  - {b}")
    lines.append("")
    lines.append(
        f"{n} recorded failure(s) this instrument missed. "
        f"get_instrument(id='{inst['id']}') for each one's discriminating check."
    )
    return "\n".join(lines)


def tool_get_instrument(reg: Registry, args: dict[str, Any]) -> str:
    raw = args.get("id")
    if not isinstance(raw, str) or not raw.strip():
        raise ToolInputError(
            "get_instrument requires a non-empty 'id' string. "
            f"Known ids: {', '.join(reg.instrument_ids())}."
        )
    inst = reg.resolve_instrument(raw)
    if inst is None:
        raise ToolInputError(
            f"Unknown instrument {raw!r}. Known ids: {', '.join(reg.instrument_ids())}."
        )
    entries = reg.entries_for(inst["id"])
    lines = [
        f"INSTRUMENT: {inst['id']} — {inst['name']}",
        f"USED WHEN:  {inst['used_when']}",
        f"CAPTURES:   {inst['captures']}",
        "",
        "BLIND TO:",
    ]
    for b in inst.get("blind_to", []):
        lines.append(f"  - {b}")
    lines.append("")
    lines.append(f"RECORDED FAILURES ({len(entries)}):")
    if not entries:
        lines.append("  (none recorded yet)")
    for e in entries:
        lines.append("")
        lines.append(render_entry(e, full=True))
    return "\n".join(lines)


SEARCH_FIELDS = ("title", "false_reading", "true_state", "class")


def tool_search(reg: Registry, args: dict[str, Any]) -> str:
    q = args.get("query")
    if not isinstance(q, str) or not q.strip():
        raise ToolInputError("search requires a non-empty 'query' string.")
    needle = q.strip().lower()
    hits = []
    for e in reg.entries:
        haystack = " ".join(str(e.get(f, "")) for f in SEARCH_FIELDS).lower()
        if needle in haystack:
            hits.append(e)
    if not hits:
        return (
            f"No entries match {q!r} in title/false_reading/true_state/class.\n"
            f"Searchable entries: {len(reg.entries)}. "
            "Try a broader term, or list_instruments to browse by instrument."
        )
    lines = [f"{len(hits)} of {len(reg.entries)} entries match {q!r}:", ""]
    for e in hits:
        lines.append(render_entry(e, full=False))
        lines.append(f"  CHECK:         {e.get('discriminating_check')}")
        lines.append("")
    lines.append("get_entry(id=...) for the full account of any of these.")
    return "\n".join(lines)


def tool_get_entry(reg: Registry, args: dict[str, Any]) -> str:
    raw = args.get("id")
    if not isinstance(raw, str) or not raw.strip():
        raise ToolInputError("get_entry requires a non-empty 'id' string, e.g. 'NS-001'.")
    e = reg.entry(raw)
    if e is None:
        raise ToolInputError(
            f"No entry with id {raw!r}. Known ids: {', '.join(reg.entry_ids())}."
        )
    return render_entry(e, full=True)


def tool_from_symptom(reg: Registry, args: dict[str, Any]) -> str:
    raw = args.get("description")
    if not isinstance(raw, str) or not raw.strip():
        raise ToolInputError(
            "from_symptom requires a non-empty 'description' string — what you are "
            "observing, e.g. 'the deploy ran but the site is unchanged'."
        )
    if not reg.symptoms:
        raise ToolInputError("This registry copy carries no symptom index.")
    matches = reg.match_symptoms(raw)
    if not matches:
        lines = [f"Nothing matched {raw!r}. The recorded symptoms are:", ""]
        lines += [f"  - {sy['symptom']}" for sy in reg.symptoms]
        lines.append("")
        lines.append("Or use search(query=...) across every entry.")
        return "\n".join(lines)

    lines = [f"Symptoms matching {raw!r}:", ""]
    for score, sy in matches:
        lines.append(f"* {sy['symptom']}")
        if sy.get("note"):
            lines.append(f"  {sy['note']}")
        lines.append("")
        for eid in sy.get("entries", []):
            e = reg.entry(eid)
            if not e:
                continue
            lines.append(f"  {e['id']}  {e.get('title')}")
            lines.append(f"    actually: {e.get('true_state', '')}")
            lines.append(f"    CHECK:    {e.get('discriminating_check')}")
            lines.append("")
    lines.append("get_entry(id=...) for the full account, including what it costs to miss.")
    return "\n".join(lines)


def tool_before_claiming(reg: Registry, args: dict[str, Any]) -> str:
    raw = args.get("task")
    if not isinstance(raw, str) or not raw.strip():
        raise ToolInputError(
            "before_claiming requires a non-empty 'task' string — what you just "
            "did, e.g. 'restarted the service' or 'deployed the site'."
        )
    if not reg.recipes:
        raise ToolInputError("This registry copy carries no recipes.")
    matches = reg.match_recipes(raw)
    if not matches:
        lines = [f"No preflight matches {raw!r}. Tasks covered:", ""]
        lines += [f"  - {r['task']}" for r in reg.recipes]
        lines += ["", "Or call get_protocol() for the general five-step version."]
        return "\n".join(lines)

    lines = [f"Before claiming {raw!r} is done:", ""]
    for r in matches:
        lines += [f"== {r['task']} ==", f"   {r['when']}", ""]
        for i, st in enumerate(r.get("steps", []), 1):
            lines.append(f"  {i}. {st['check']}")
            lines.append(f"     $ {st['how']}")
            guards = []
            for g in st.get("guards_against", []):
                e = reg.entry(g)
                if e:
                    guards.append(f"{g} ({e.get('title_short') or e.get('title')})")
            if guards:
                lines.append(f"     guards against: {'; '.join(guards)}")
            lines.append("")
    lines.append("get_entry(id=...) for any of these in full.")
    return "\n".join(lines)


def tool_get_protocol(reg: Registry, args: dict[str, Any]) -> str:
    lines = ["VERIFY-FIRST PROTOCOL — run before reporting any work complete.", ""]
    for i, (step, note) in enumerate(PROTOCOL_STEPS, start=1):
        lines.append(f"{i}. {step}")
        lines.append(f"   {note}")
        lines.append("")
    if reg.principles:
        lines.append("PRINCIPLES:")
        for p in reg.principles:
            lines.append(f"  {p.get('id')}  {p.get('statement')}")
            if p.get("note"):
                lines.append(f"      {p['note']}")
    return "\n".join(lines).rstrip()


HANDLERS = {
    "list_instruments": tool_list_instruments,
    "blind_spots": tool_blind_spots,
    "get_instrument": tool_get_instrument,
    "search": tool_search,
    "get_entry": tool_get_entry,
    "from_symptom": tool_from_symptom,
    "before_claiming": tool_before_claiming,
    "get_protocol": tool_get_protocol,
}


class ToolInputError(Exception):
    """Bad arguments to a known tool — reported as tool-level isError content."""


# --------------------------------------------------------------------------
# JSON-RPC plumbing
# --------------------------------------------------------------------------

def make_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def make_error(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    requested = params.get("protocolVersion")
    version = (
        requested
        if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS
        else PREFERRED_PROTOCOL_VERSION
    )
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": (
            "verifyfirst tells an agent what its verification method is blind to. "
            "Before you report work as done, call blind_spots with the instrument you are "
            "trusting (screenshot, exit-code, http-response, file-on-disk, process-list, "
            "log-output) and confirm none of its blind spots apply. get_protocol returns the "
            "five-step checklist; search finds known failures by symptom."
        ),
    }


def handle_tools_call(params: dict[str, Any]) -> dict[str, Any] | None:
    """Returns a tools/call result, or raises MethodError for an unknown tool."""
    name = params.get("name")
    if not isinstance(name, str):
        raise MethodError(INVALID_PARAMS, "tools/call requires a string 'name' parameter.")
    if name not in HANDLERS:
        raise MethodError(
            INVALID_PARAMS,
            f"Unknown tool: {name}",
            {"available_tools": sorted(HANDLERS)},
        )
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        raise MethodError(INVALID_PARAMS, "'arguments' must be an object.")
    assert REGISTRY is not None
    try:
        text = HANDLERS[name](REGISTRY, args)
    except ToolInputError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    return {"content": [{"type": "text", "text": text}], "isError": False}


class MethodError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def dispatch(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Returns a response dict, or None for notifications (which get no reply)."""
    req_id = msg.get("id")
    method = msg.get("method")
    is_notification = "id" not in msg

    if not isinstance(method, str):
        if is_notification:
            return None
        return make_error(req_id, INVALID_REQUEST, "Missing or non-string 'method'.")

    params = msg.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    # Notifications: acknowledge by doing nothing, never by erroring.
    if is_notification:
        if method.startswith("notifications/"):
            return None
        return None

    try:
        if method == "initialize":
            return make_result(req_id, handle_initialize(params))
        if method == "ping":
            return make_result(req_id, {})
        if method == "tools/list":
            return make_result(req_id, {"tools": TOOLS})
        if method == "tools/call":
            return make_result(req_id, handle_tools_call(params))
        if method in ("resources/list", "prompts/list"):
            # Some clients probe these even when the capability was not advertised.
            key = "resources" if method.startswith("resources") else "prompts"
            return make_result(req_id, {key: []})
        raise MethodError(METHOD_NOT_FOUND, f"Method not found: {method}")
    except MethodError as exc:
        return make_error(req_id, exc.code, exc.message, exc.data)
    except Exception as exc:  # noqa: BLE001 - never let one bad call kill the server
        log("unhandled exception:\n" + traceback.format_exc())
        return make_error(req_id, INTERNAL_ERROR, f"Internal error: {exc!r}")


def serve(stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            resp = make_error(None, PARSE_ERROR, f"Parse error: {exc}")
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
            continue

        # A batch is a list; handle each member and reply with the non-empty results.
        if isinstance(msg, list):
            out = [r for r in (dispatch(m) for m in msg if isinstance(m, dict)) if r]
            if out:
                stdout.write(json.dumps(out) + "\n")
                stdout.flush()
            continue

        if not isinstance(msg, dict):
            resp = make_error(None, INVALID_REQUEST, "Top-level JSON must be an object or array.")
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
            continue

        resp = dispatch(msg)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


def main(argv: list[str]) -> int:
    global REGISTRY
    remote = "--remote" in argv
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    data, source = load_registry(remote=remote)
    REGISTRY = Registry(data, source)
    log(
        f"ready: {len(REGISTRY.instruments)} instruments, "
        f"{len(REGISTRY.entries)} entries, {len(TOOLS)} tools"
    )
    try:
        serve()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
