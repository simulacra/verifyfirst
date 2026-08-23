# verifyfirst MCP server

An MCP server that lets an agent ask, from inside its own tooling, **what the
instrument it is about to trust cannot see.**

A failure that reports success costs more than one that crashes. This server is
for the moment before you claim work is done: you are verifying through some
instrument — a screenshot, an exit code, an HTTP status, a file you read, a
process list, a log — and every one of them is structurally blind to something.
Look up what yours cannot see.

Same data as <https://verifyfirst.dev>, without the fetch-and-parse round trip:
6 instruments, 14 recorded failures, 8 principles. Every entry is drawn from a
failure that was actually observed and diagnosed.

---

## Install

### Claude Code

```
claude mcp add verifyfirst -- python3 path/to/verifyfirst/mcp/server.py
```

Verify it came up:

```
claude mcp list | grep verifyfirst
# verifyfirst: python3 path/to/verifyfirst/mcp/server.py - ✔ Connected
```

Scope flags, if the default (local, this directory only) is not what you want:

```
claude mcp add verifyfirst --scope user    -- python3 path/to/verifyfirst/mcp/server.py   # every project
claude mcp add verifyfirst --scope project -- python3 path/to/verifyfirst/mcp/server.py   # checked-in .mcp.json
```

Remove with `claude mcp remove verifyfirst`.

### Raw JSON config (any other MCP client)

For `.mcp.json`, `claude_desktop_config.json`, Cursor, Zed, Continue, or
anything else that takes the standard stdio server block:

```json
{
  "mcpServers": {
    "verifyfirst": {
      "type": "stdio",
      "command": "python3",
      "args": ["path/to/verifyfirst/mcp/server.py"],
      "env": {}
    }
  }
}
```

To serve the live registry from verifyfirst.dev instead of the bundled copy,
add `"--remote"` after the script path. On any network or parse failure it falls
back to the bundled copy, so the server always starts.

```json
"args": ["path/to/verifyfirst/mcp/server.py", "--remote"]
```

---

## Requirements

Python 3.12, standard library only. No pip installs, no venv, no dependencies.
Runs offline by default from the `registry.json` bundled beside `server.py`.

---

## Tools

| Tool | Use it when |
|---|---|
| `blind_spots(instrument)` | **The pre-flight check.** About to say "done", "fixed", "deployed". Terse list of what the instrument you trusted cannot show you. |
| `list_instruments()` | You are not sure what to call the instrument you just used. |
| `get_instrument(id)` | A blind spot might apply and you want the concrete check that settles it. |
| `search(query)` | You have a symptom, not an instrument: `blank`, `cache`, `font`, `hang`, `oom`. |
| `get_entry(id)` | Full account of one recorded failure, e.g. `NS-001`. |
| `get_protocol()` | The five-step checklist, once per verification pass. |

`blind_spots` and `get_instrument` accept loose instrument names — `curl`, `200`,
`ps`, `pgrep`, `systemctl`, `journalctl`, `stdout`, `config`, `playwright`,
`"the exit code of the command"` all resolve to the right one.

### The six instruments

| id | Used when |
|---|---|
| `screenshot` | You captured the page and looked at it. |
| `exit-code` | The command exited zero, so you moved on. |
| `http-response` | You requested the URL and got 200. |
| `file-on-disk` | You read the config or the source and confirmed it says the right thing. |
| `process-list` | You checked `ps`, `pgrep`, or `systemctl status`. |
| `log-output` | You read the output and it looked normal. |

### The protocol

1. Name the instrument.
2. Say what it cannot see.
3. Run one check that could fail.
4. Report the observation, not the inference.
5. Prefer resolved values over authored ones.

---

## Files

```
server.py       the MCP server — stdio, JSON-RPC 2.0, newline-delimited
registry.json   bundled copy of the registry, so the server works offline
test_server.py  integration tests: spawns server.py and speaks real JSON-RPC to it
README.md       this file
```

## Tests

```
python3 path/to/verifyfirst/mcp/test_server.py
```

36 tests. They do not import `server.py`; they spawn it as a subprocess and
speak the protocol to it over a pipe, which is the only thing a real client will
ever do. Covers the initialize handshake, `notifications/initialized` producing
no reply, all six tools against known inputs checked against `registry.json`
itself, alias resolution, unknown tool ids returning a JSON-RPC `-32602` rather
than crashing, malformed JSON returning `-32700` with the server still alive,
and offline-by-default startup.

## Updating the bundled registry

```
cp path/to/verifyfirst/registry.json path/to/verifyfirst/mcp/registry.json
python3 path/to/verifyfirst/mcp/test_server.py
```

The tests read `registry.json` as their source of truth, so they will catch a
copy that did not land.

## License

Registry content: CC0-1.0, same as verifyfirst.dev.
