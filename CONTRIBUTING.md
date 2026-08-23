# Contributing

The registry takes entries from anyone, human or agent. There is one bar, and
it is the whole point of the project.

## The bar: a discriminating check

Every entry must name **one observation that returns a different result
depending on which hypothesis is true.**

That is the entire test. If the same observation comes out the same way whether
or not the bug is present, it has confirmed nothing — however much work it took
to produce.

| Not a check | A check |
|---|---|
| "Be careful with headless browsers" | `let n=0; requestAnimationFrame(()=>n++); setTimeout(()=>console.log('rAF fired:', n), 1000)` |
| "Make sure the service restarted" | `systemctl show -p ExecStart NAME` compared against `ps -p $MAINPID -o args=` |
| "Double-check the config is loaded" | Ask the running process what it loaded, not the filesystem what it holds |
| "Look closely at the rendered page" | `getComputedStyle(el).position` — the resolved value, never the authored one |

The left column describes an attitude. The right column names something you can
look at. CI rejects the left column automatically.

## The other bar: it has to be real

Every entry is a failure that genuinely occurs. Two kinds are accepted, and the
`provenance` field says which:

- **`observed`** — you diagnosed it first-hand. Say what you saw.
- **`documented`** — cite primary documentation in `source` (a man page, an
  official reference, a spec, an RFC, a release note), **and reproduce the check
  before submitting.** Reasoning that a check should work is not reproducing it.

A registry of plausible-sounding bugs would be indistinguishable from a registry
of real ones — which is precisely the failure this catalogues. Getting it wrong
would build the bug into the thing.

## Adding an entry

1. Add an object to `entries` in `registry.json`. Copy the shape of a neighbour;
   `schema/registry.schema.json` documents every field.
2. Use the next free `NS-0XX` id.
3. File it under the **instrument that missed the failure** — `screenshot`,
   `exit-code`, `http-response`, `file-on-disk`, `process-list`, `log-output` —
   not under the technology involved. The instrument is what a reader knows
   before they know the bug.
4. Add it to at least one entry in `symptoms`, phrased the way someone would
   describe the problem rather than the mechanism. An entry reachable only by
   browsing its instrument can only be found by the reader who least needs it.
5. If the title runs over 60 characters, write a `title_short`. Write it — do
   not truncate it.
6. Run the checks below.

```bash
python3 tools/validate.py            # structure + editorial rules
cd mcp && python3 test_server.py     # the server still works
python3 build.py dist/               # the site still builds
```

The registry is the single source of truth. Every page, plain-text file, JSON
export and MCP response is generated from it, so **never hand-edit anything in
`dist/`.** Two copies of the same content is how they start disagreeing.

If you change `registry.json`, copy it to the two bundles that ship offline
copies — CI checks they are byte-identical:

```bash
cp registry.json mcp/registry.json
cp registry.json pypi/src/verifyfirst_mcp/registry.json
```

## Correcting an entry

The useful correction is **a check that discriminates better than the one
given.** "This is wrong" is a start; "this check returns the same thing in both
cases, and here is one that doesn't" is a contribution.

If an entry's mechanism has changed — a tool fixed the behaviour, a default
flipped — say so with the version and a source. Entries can be retired; they
should not quietly rot.

## Style

Calm, declarative, specific. State the mechanism; do not sell it. No second
person imperatives, no hedging, no "you might be surprised". British spelling
(`generalises`, `behaviour`) for consistency with what is there.

`false_reading` ends with `Conclusion drawn: ...` — the wrong inference is the
point of the field, not decoration.

## Licence

CC0-1.0. By contributing you place your contribution in the public domain. No
CLA, no attribution requirement, no way for anyone to take it back out.
