#!/bin/bash
# ============================================================================
# Open (and keep open) the SSH tunnel: app VM -> LANTA login node -> compute
# node :8000. RUN ON THE APP VM. The forwarded port 127.0.0.1:8000 is the
# stable endpoint the backend's vLLM client talks to; the compute node behind
# it changes on every walltime restart, and autossh + scrontab handle that.
#
# When no job is running this script exits non-zero — the chatbot then shows
# its "outside demonstration window" state. That is designed behavior.
#
# *** 2FA CAVEAT (verified July 2026): LANTA requires password + Google 2FA on
# every SSH connection, so this script currently needs a human at the keyboard
# for the initial auth, and autossh CANNOT silently reconnect after a drop.
# Unattended operation is blocked until ThaiSC confirms whether a registered
# deploy key bypasses 2FA (asked: thaisc-support@nstda.or.th). ***
#
# Usage: LANTA_SSH_USER=... LANTA_SSH_KEY_PATH=... ./tunnel.sh
# ============================================================================
set -euo pipefail

LANTA_HOST="${LANTA_SSH_HOST:-lanta.nstda.or.th}"
LANTA_USER="${LANTA_SSH_USER:?set LANTA_SSH_USER}"
SSH_KEY="${LANTA_SSH_KEY_PATH:?set LANTA_SSH_KEY_PATH (dedicated deploy key)}"
PROJECT_DIR="${LANTA_PROJECT_DIR:-/project/tn999991-cstu/chin}"
LOCAL_PORT="${TUNNEL_LOCAL_PORT:-8000}"

SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

# Discover the active compute node published by serve_vllm.sbatch
NODE=$(ssh "${SSH_OPTS[@]}" "$LANTA_USER@$LANTA_HOST" \
    "cat '$PROJECT_DIR/run/current_node.txt'" 2>/dev/null) || {
    echo "no active serving job found (run/current_node.txt missing)" >&2
    echo "chatbot is outside its demonstration window" >&2
    exit 1
}
echo ">>> forwarding 127.0.0.1:$LOCAL_PORT -> $NODE:8000 via $LANTA_HOST"

# autossh keeps the tunnel alive across drops; walltime kills still require
# a new node hostname, so scrontab resubmission + rerunning this script
# (supervised by Prefect later) completes the recovery loop.
exec autossh -M 0 -N \
    "${SSH_OPTS[@]}" \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
    -L "127.0.0.1:$LOCAL_PORT:$NODE:8000" \
    "$LANTA_USER@$LANTA_HOST"
