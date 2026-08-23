#!/usr/bin/env bash
# release — sync, test, build, publish. In that order, with the publish gated.
#
#   bash release.sh 1.2.2
#
# This exists because on 2026-08-23 I ran the tests and the publish as separate
# statements in one shell. The tests failed, the publish went ahead anyway, and
# a broken from_symptom reached PyPI. Chaining commands is not a gate; only a
# non-zero exit that stops the script is. Everything below runs under `set -e`
# with the test step ahead of every artifact-producing step.
set -euo pipefail

VERSION="${1:?usage: release.sh <version>}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"
cd "$ROOT"

echo "== 1/7  sync registry into every copy that ships"
cp registry.json mcp/registry.json
cp registry.json pypi/src/verifyfirst_mcp/registry.json
cp mcp/server.py pypi/src/verifyfirst_mcp/server.py
diff -q registry.json mcp/registry.json
diff -q registry.json pypi/src/verifyfirst_mcp/registry.json
diff -q mcp/server.py pypi/src/verifyfirst_mcp/server.py
echo "   copies identical"

echo "== 2/7  tests (gate — nothing is published if this fails)"
( cd mcp && python3 test_server.py 2>&1 | tail -3 )
# The pipe above would mask a failure behind tail's exit status, so ask again
# without the pipe. PIPESTATUS is the registry's own NS-015.
( cd mcp && python3 test_server.py >/dev/null 2>&1 )
echo "   tests pass"

echo "== 3/7  stamp version $VERSION"
sed -i "s/^SERVER_VERSION = .*/SERVER_VERSION = \"$VERSION\"/" mcp/server.py
cp mcp/server.py pypi/src/verifyfirst_mcp/server.py
sed -i "s/^version = \".*\"/version = \"$VERSION\"/" pypi/pyproject.toml
sed -i "s/^__version__ = \".*\"/__version__ = \"$VERSION\"/" pypi/src/verifyfirst_mcp/__init__.py
python3 - "$VERSION" <<'PY'
import json, sys
from pathlib import Path
v = sys.argv[1]
p = Path("pypi/server.json"); d = json.loads(p.read_text())
d["version"] = d["packages"][0]["version"] = v
p.write_text(json.dumps(d, indent=2) + "\n")
PY

echo "== 4/7  build"
( cd pypi && rm -rf dist && uv build >/dev/null && ls dist/ )

echo "== 5/7  validate the registry manifest before publishing anywhere"
( cd pypi && "$HOME/bin/mcp-publisher" validate )

echo "== 6/7  publish to PyPI"
set -a; . "$HOME/.config/pypi.env"; set +a
( cd pypi && uv publish --token "$TWINE_PASSWORD" dist/* 2>&1 | tail -2 )

echo "== 7/7  publish to the MCP registry"
# The registry JWT expires per session, so log in every time rather than
# discovering it is stale halfway through a release.
( cd pypi && "$HOME/bin/mcp-publisher" login github --token "$(gh auth token)" >/dev/null \
  && "$HOME/bin/mcp-publisher" publish 2>&1 | tail -2 )

echo
echo "Published $VERSION. Now verify it — do not trust this script's exit code:"
echo "  uvx --refresh --from verifyfirst-mcp verifyfirst-mcp --help"
echo "  curl -s 'https://registry.modelcontextprotocol.io/v0/servers?search=verifyfirst'"
