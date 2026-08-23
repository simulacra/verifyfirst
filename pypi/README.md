# verifyfirst-mcp

**An MCP server for what your verification method cannot see.**

<!-- mcp-name: io.github.simulacra/verifyfirst -->

A failure that crashes is cheap. A failure that *reports success* is expensive:
the screenshot looks fine, the command exits zero, the endpoint returns 200,
and the bug ships.

This server exposes [verifyfirst.dev](https://verifyfirst.dev) — a registry of
30 such failures, organised by the **instrument that missed them** rather than
by the technology involved, because the instrument is what you know before you
know the bug.

## Install

```bash
uvx verifyfirst-mcp          # run it directly
pip install verifyfirst-mcp  # or install it
```

Register with Claude Code:

```bash
claude mcp add verifyfirst -- uvx verifyfirst-mcp
```

Or any MCP client:

```json
{
  "mcpServers": {
    "verifyfirst": { "command": "uvx", "args": ["verifyfirst-mcp"] }
  }
}
```

## Tools

| Tool | What it does |
|---|---|
| `from_symptom(description)` | Start here when something is wrong but you do not know why. Describe what you see — "deploy ran but nothing changed", "200 but the data is wrong" — and get the failures that produce that appearance, each with its check. |
| `blind_spots(instrument)` | The one to reach for mid-task. What an instrument cannot see, terse. Takes loose names — `curl`, `200`, `pgrep`, `systemctl`, `stdout`, `playwright` all resolve. |
| `list_instruments()` | All six instruments. |
| `get_instrument(id)` | Full detail plus every recorded failure it missed, each with its check. |
| `search(query)` | Substring search across the registry. |
| `get_entry(id)` | One entry, e.g. `NS-001`. |
| `get_protocol()` | A five-step checklist for claiming work is done. |

## Example

```
> blind_spots("screenshot")

screenshot (A rendered image) is blind to:
  - Time. A still frame cannot distinguish 'renders one frame then stops'
    from 'renders one frame correctly'.
  - Whether scripts ran at all, as opposed to running and producing this.
  ...
```

## Notes

Zero dependencies — Python standard library only. Works offline from a bundled
copy of the registry; pass `--remote` to read the live one, which falls back to
the bundle on any failure.

Every entry in the registry is a failure that genuinely occurs, marked
`observed` (diagnosed first-hand) or `documented` (primary source cited and the
check reproduced). None are hypothetical.

CC0-1.0 — public domain. Maintained by [Zion Labs](https://zionlabs.io).
