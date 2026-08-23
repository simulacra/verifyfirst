# verifyfirst

**A registry of software failures that report success.**

Live at **[verifyfirst.dev](https://verifyfirst.dev)** · machine-readable at
[`/registry.json`](https://verifyfirst.dev/registry.json) · CC0

---

A failure that crashes is cheap. It announces itself, and you fix it.

A failure that *reports success* is expensive. The screenshot looks fine. The
command exits zero. The endpoint returns 200. You move on, and the bug ships.

This is a reference for the moment before you claim work is done. It is
organised by **the instrument you verified with** — not by the bug, because
the bug is the thing you are trying to find. You know how you looked. Look up
what that method cannot see.

```
$ curl verifyfirst.dev/screenshot.txt

VERIFYFIRST // screenshot
A rendered image — You captured the page and looked at it.

WHAT IT CANNOT SEE
  - Time. A still frame cannot distinguish 'renders one frame then stops'
    from 'renders one frame correctly'.
  - Whether scripts ran at all, as opposed to running and producing this.
  - Why an element is absent: never drawn, drawn transparent, drawn
    offscreen, or covered.
  ...
```

## The six instruments

| Instrument | You used it when | Plain text |
|---|---|---|
| `screenshot` | You captured the page and looked at it | [`/screenshot.txt`](https://verifyfirst.dev/screenshot.txt) |
| `exit-code` | The command exited zero, so you moved on | [`/exit-code.txt`](https://verifyfirst.dev/exit-code.txt) |
| `http-response` | You requested the URL and got 200 | [`/http-response.txt`](https://verifyfirst.dev/http-response.txt) |
| `file-on-disk` | You read the config and it says the right thing | [`/file-on-disk.txt`](https://verifyfirst.dev/file-on-disk.txt) |
| `process-list` | You checked `ps`, `pgrep`, or `systemctl status` | [`/process-list.txt`](https://verifyfirst.dev/process-list.txt) |
| `log-output` | You read the output and it looked normal | [`/log-output.txt`](https://verifyfirst.dev/log-output.txt) |

## Entry format

Every entry names the one observation that separates the two hypotheses:

```json
{
  "id": "NS-005",
  "instrument": "exit-code",
  "title": "enable --now does not restart an already-running unit",
  "false_reading": "The command exits zero and the service is active. Conclusion drawn: the new code is live.",
  "true_state": "systemctl enable --now starts a stopped unit. On a running one it is a no-op. The old process, with the old ExecStart, survives.",
  "why_blind": "Exit code zero and `active (running)` are true statements about the wrong process.",
  "discriminating_check": "systemctl show -p ExecStart NAME and ps -p $MAINPID -o args=",
  "cost_of_missing": "A deploy is reported as complete twice while the previous binary keeps serving.",
  "generalises_to": "Any idempotent-looking command whose semantics differ by current state."
}
```

A check qualifies **only if it returns different output under the two
hypotheses.** An observation that comes out the same either way has confirmed
nothing, however much work it took to produce.

## MCP server

Query the registry from your own tooling instead of fetching web pages:

```bash
claude mcp add verifyfirst -- uvx verifyfirst-mcp
```

On [PyPI](https://pypi.org/project/verifyfirst-mcp/) and in the
[official MCP registry](https://registry.modelcontextprotocol.io/) as
`io.github.simulacra/verifyfirst`.

Python 3.12 stdlib only — no pip install, no dependencies, works offline from
the bundled registry copy. Tools: `list_instruments`, `get_instrument`,
`blind_spots`, `search`, `get_entry`, `get_protocol`.

`blind_spots` is the one to reach for mid-task. It takes loose names — `curl`,
`200`, `pgrep`, `systemctl`, `stdout`, `playwright` all resolve — and returns
just the list, terse enough to read before you commit to a verification.

Full install options for other MCP clients: [`mcp/README.md`](mcp/README.md).

## The protocol

Short enough to paste into a system prompt:

> Before reporting work complete: name the instrument you verified with, state
> what that instrument cannot see, run one check whose result would differ if
> the work had failed, and report the observation rather than the conclusion.
> Prefer resolved values over authored ones.

## The standard

**Every entry is drawn from a failure that was actually observed and
diagnosed. None are hypothetical.**

That bar is the whole value of this. A registry of plausible-sounding bugs
would be indistinguishable from a registry of real ones — which is precisely
the failure mode catalogued here, so getting it wrong would build the bug into
the thing.

## Contributing

Entries need a **discriminating check** — one observation that returns a
different result depending on which hypothesis is true. "Be careful" is not a
check. "Look more closely" is not a check. `getComputedStyle(el).position` is a
check, and CI rejects the first two automatically.

Open an issue or a PR against `registry.json`. Full guide in
[CONTRIBUTING.md](CONTRIBUTING.md); the field reference is
[`schema/registry.schema.json`](schema/registry.schema.json).

```bash
python3 tools/validate.py            # structure + editorial rules
cd mcp && python3 test_server.py     # server still works
python3 build.py dist/               # site still builds
```

## Building

```bash
python3 build.py dist/
```

Every page — HTML, plain text, JSON, JSONL, `llms.txt`, sitemap — is generated
from `registry.json`. There is no second copy of the content to fall out of
date, which is the registry's own first principle applied to itself.

## Licence

CC0-1.0. Public domain. Copy it, quote it, fold it into a system prompt, ship
it inside a product. No attribution required.

---

Maintained by [Zion Labs](https://zionlabs.io) · [verifyfirst.dev](https://verifyfirst.dev)
