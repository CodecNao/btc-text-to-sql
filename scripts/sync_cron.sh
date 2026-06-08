#!/usr/bin/env bash
# HW item 3c: run the updater on a schedule.
# Edit the paths, then add to crontab with:  crontab -e
#
#   */5 * * * * /abs/path/to/btc-text-to-sql/scripts/sync_cron.sh >> /abs/path/sync.log 2>&1
#
# A lock file prevents overlapping runs if one sync takes longer than 5 minutes.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${PROJECT_DIR}/chain.db"
LOCK="/tmp/btc_sync.lock"

export BTC_RPC_USER="${BTC_RPC_USER:-bitcoinrpc}"
export BTC_RPC_PASSWORD="${BTC_RPC_PASSWORD:?set BTC_RPC_PASSWORD}"

exec 9>"$LOCK"
if ! flock -n 9; then
    echo "$(date -Is) another sync is running; skipping"
    exit 0
fi

cd "$PROJECT_DIR"
python -m src.updater --db "$DB_PATH"
