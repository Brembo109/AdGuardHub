#!/bin/sh
#
# Runs one upgrade, as root, on behalf of the hub's "update now" button.
#
# The hub itself has none of the privilege this needs and is not given any: it
# writes an empty file, a systemd path unit notices, and this runs. Nothing the
# hub writes reaches this script — it takes no arguments, reads no request, and
# always installs the newest release. That is the whole point of the split.
#
# Everything it prints goes to the log the hub reads back, so the operator
# watches the upgrade from the interface they pressed the button in.
set -eu

DATA_DIR="${ADGUARDHUB_DATA_DIR:-/var/lib/adguardhub}"
SERVICE_USER="${ADGUARDHUB_SERVICE_USER:-adguardhub}"
INSTALLER_URL="${ADGUARDHUB_INSTALLER_URL:-https://raw.githubusercontent.com/fgrfn/adguardhub/main/install.sh}"
LOG="$DATA_DIR/update.log"

# Truncated per run: this is the record of *this* upgrade, not a history.
: >"$LOG"
# Readable by the hub, which runs as its own user, and by nobody else.
chown "$SERVICE_USER:$SERVICE_USER" "$LOG" 2>/dev/null || true
chmod 640 "$LOG" 2>/dev/null || true

exec >>"$LOG" 2>&1

WORK=""
finish() {
    status=$?
    if [ -n "$WORK" ]; then
        rm -rf "$WORK"
    fi
    if [ "$status" -eq 0 ]; then
        printf '\n[done] AdGuardHub was upgraded.\n'
    else
        printf '\n[failed] The upgrade stopped with status %s. Nothing was rolled back; the hub is still running the version it was.\n' "$status"
    fi
    # The marker the hub looks for to know the run has ended, and how.
    printf '[exit %s]\n' "$status"
}
trap finish EXIT

printf '[start] %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')"

WORK=$(mktemp -d)

printf '[fetch] %s\n' "$INSTALLER_URL"
# Downloaded first rather than piped into a shell: `curl … | sh` reports success
# when the download fails, because the shell simply reads nothing and exits 0 —
# which would turn a network failure into a silent "upgraded".
curl -fsSL "$INSTALLER_URL" -o "$WORK/install.sh"
[ -s "$WORK/install.sh" ] || {
    printf '[failed] the installer came back empty\n'
    exit 1
}

printf '[run] installing the newest release\n'
sh "$WORK/install.sh"
