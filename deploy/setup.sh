#!/usr/bin/env bash
# verifyfirst.dev — one-time root setup. Run with sudo, interactively.
#
#   sudo bash ~/verifyfirst/deploy/setup.sh
#
# Creates the web root ben-owned (so every later deploy needs no sudo at all),
# installs the Caddy site config, and reloads. Idempotent — safe to re-run.
set -euo pipefail

SITE=verifyfirst.dev
ROOT=/var/www/$SITE
CONF=/etc/caddy/conf.d/$SITE.caddy

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

# 1. Web root, owned by ben so deploys are a plain cp forever after.
mkdir -p "$ROOT"
chown ben:ben "$ROOT"
chmod 755 "$ROOT"
echo "web root: $ROOT (ben-owned)"

# 2. Access log. This is how agent traffic gets counted — GA4 needs a JS
#    runtime and most agent fetches have none, so the log is the real meter.
#
#    But a log Caddy cannot open makes the whole config fail to load, taking
#    every other site on this box down with it. So test the write as the caddy
#    user first and only ask for logging if it actually works. Guessing here is
#    how you trade a missing access log for an outage.
LOGDIR=/var/log/caddy
LOGFILE=$LOGDIR/verifyfirst.access.log
mkdir -p "$LOGDIR"
chown caddy:caddy "$LOGDIR"
chmod 755 "$LOGDIR"

# A leftover root-owned file from an earlier failed run is enough to make the
# write test fail forever. Clear a file the caddy user cannot open, rather than
# diagnosing the same permission error twice.
if [ -e "$LOGFILE" ] && ! sudo -u caddy test -w "$LOGFILE"; then
  echo "removing unwritable $LOGFILE ($(stat -c '%U:%G %a' "$LOGFILE"))"
  rm -f "$LOGFILE"
fi

if sudo -u caddy test -w "$LOGDIR" && sudo -u caddy touch "$LOGFILE" 2>/dev/null; then
  chown caddy:caddy "$LOGFILE"
  chmod 644 "$LOGFILE"
  LOGGING=1
  echo "access log: $LOGFILE (writable by caddy)"
else
  LOGGING=0
  echo "access log: DISABLED — the caddy user cannot write to $LOGDIR."
  echo "            Site config will be installed without logging so it can load."
  echo "            Likely AppArmor; check: aa-status | grep -i caddy"
fi

# 3. Site config. Backed up first if it already exists (global rule 3).
mkdir -p /etc/caddy/conf.d
[ -f "$CONF" ] && cp "$CONF" "$CONF.$(date +%Y-%m-%d_%H-%M-%S).bak"

cat > "$CONF" <<'CADDY'
verifyfirst.dev, www.verifyfirst.dev {
	root * /var/www/verifyfirst.dev
	encode zstd gzip

	@www host www.verifyfirst.dev
	redir @www https://verifyfirst.dev{uri} permanent

	# Caddy has no MIME mapping for .jsonl, so it would send no Content-Type
	# at all and leave every client sniffing.
	@jsonl path *.jsonl
	header @jsonl Content-Type "application/x-ndjson; charset=utf-8"

	# The plain-text instrument pages are the point of the site for anything
	# arriving by curl. They must never be served as a download.
	@txt path *.txt
	header @txt Content-Type "text/plain; charset=utf-8"

	# Explicit freshness. With no Cache-Control a browser applies heuristic
	# caching and holds a stale copy for hours, which reads as a failed
	# deploy to the one person most likely to check — see NS-007.
	header Cache-Control "public, max-age=300, must-revalidate"
	header X-Content-Type-Options nosniff

	# URLs arrive with prose punctuation stuck to them — the access log showed
	# five hits on "/registry.json," within a day of launch. A model quoting a
	# URL mid-sentence produces exactly that. Redirect instead of 404ing.
	@trailing_punct path_regexp tp ^(/.+?)[,.;:!?)\]}'"]+$
	redir @trailing_punct {re.tp.1} permanent

	file_server
}
CADDY

# Logging is appended only if the write test above passed. roll_size/roll_keep
# are subdirectives of `output file`, not of `log`.
if [ "$LOGGING" = "1" ]; then
  # Insert the log block before the final closing brace.
  sed -i '$ d' "$CONF"
  cat >> "$CONF" <<CADDYLOG

	log {
		output file $LOGFILE {
			# Caddy defaults new log files to 0600, which would make this
			# readable only by the caddy user and by root. 644 so it can be
			# read without sudo — a log nobody can open measures nothing.
			mode 644
			roll_size 20mb
			roll_keep 5
		}
		format json
	}
}
CADDYLOG
fi

echo "config: $CONF"

# 4. Validate. Sourcing the Cloudflare env matters: geosim's wildcard block
#    uses DNS-01 and validation of the WHOLE config fails without the token,
#    which under `set -e` would abort this script before the reload — a real
#    failure this box has already had once (NS-008).
[ -f /etc/caddy/cloudflare.env ] && set -a && . /etc/caddy/cloudflare.env && set +a
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
echo "config valid"

# A config that validates can still fail to LOAD (a log file the process cannot
# open, a port already taken). Caddy keeps serving the old config in that case,
# so nothing breaks now — but the bad file stays on disk and the next reboot
# would take every site on this box down. Pull it if the reload fails.
if systemctl reload caddy; then
  echo "caddy reloaded"
else
  rm -f "$CONF"
  systemctl reload caddy || true
  echo >&2
  echo "RELOAD FAILED — new config removed so a reboot cannot break the box." >&2
  echo "Other sites are unaffected. Cause:" >&2
  journalctl -u caddy -n 15 --no-pager | grep -i error | tail -3 >&2
  exit 1
fi

echo
echo "Now verify — not by trusting this script's exit code:"
echo "  curl -sI https://$SITE/ | head -1"
echo "  curl -s https://$SITE/screenshot.txt | head -3"
