#!/usr/bin/env bash
# tunnel.sh — open a local port-forward to the currently running vLLM server on LANTA.
#
# Deliberately plain `ssh -N`, NOT autossh: LANTA requires password + Google 2FA on
# every SSH connection (see hpc/LANTA_CONFIG_NOTES.md), so an auto-reconnecting tunnel
# would just hang silently on the 2FA prompt with nobody there to answer it — autossh
# buys nothing here unless/until key-based auth is confirmed to bypass 2FA, which it
# has not been. If the tunnel drops, just re-run this script by hand.
#
# Config via env: LANTA_SSH_USER, LANTA_PROJECT_DIR (required),
# LANTA_SSH_HOST (default lanta.nstda.or.th), optional LANTA_SSH_KEY_PATH,
# LOCAL_PORT / REMOTE_PORT (default 8000 / 8000).

set -euo pipefail

: "${LANTA_SSH_USER:?set LANTA_SSH_USER}"
: "${LANTA_PROJECT_DIR:?set LANTA_PROJECT_DIR}"
LANTA_SSH_HOST="${LANTA_SSH_HOST:-lanta.nstda.or.th}"
LOCAL_PORT="${LOCAL_PORT:-8000}"
REMOTE_PORT="${REMOTE_PORT:-8000}"

TARGET="${LANTA_SSH_USER}@${LANTA_SSH_HOST}"

SSH_OPTS=(-o "ControlMaster=auto" -o "ControlPath=~/.ssh/lanta-%r@%h-%p" -o "ControlPersist=15m")
if [[ -n "${LANTA_SSH_KEY_PATH:-}" ]]; then
  SSH_OPTS+=(-i "${LANTA_SSH_KEY_PATH}")
fi

echo "Fetching current serving node from ${LANTA_PROJECT_DIR}/run/current_node.txt ..."
NODE=$(ssh "${SSH_OPTS[@]}" "${TARGET}" "cat ${LANTA_PROJECT_DIR}/run/current_node.txt" 2>/dev/null || true)

if [[ -z "${NODE}" ]]; then
  echo "error: could not read current_node.txt — is the vLLM serving job (serve_vllm.sbatch) actually running? Check 'myqueue' on LANTA." >&2
  exit 1
fi

echo "Serving node: ${NODE}"
echo "Opening tunnel: localhost:${LOCAL_PORT} -> ${NODE}:${REMOTE_PORT} (via ${LANTA_SSH_HOST})"
echo "This will block and stay in the foreground. Leave it running. Ctrl+C to close the tunnel."

exec ssh "${SSH_OPTS[@]}" -N -L "${LOCAL_PORT}:${NODE}:${REMOTE_PORT}" "${TARGET}"