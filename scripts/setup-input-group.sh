#!/usr/bin/env bash
# One-time setup: add the current user to the `input` group so raw mouse
# events (/dev/input/eventX) can be read without root. Requires sudo, so
# this is meant to be run by hand, not invoked automatically by the app --
# see the README/capture.py for why we don't silently escalate for you.
set -euo pipefail

if id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
    echo "Already in the 'input' group -- nothing to do."
    exit 0
fi

echo "Adding $USER to the 'input' group (needs sudo)..."
sudo usermod -aG input "$USER"

cat <<'EOF'

Done. Group membership only takes effect for new sessions, so log out and
back in (or reboot) before running omarchy-mb-mapper.
EOF
