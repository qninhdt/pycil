#!/bin/sh
set -eu
umask 022

# A shared lock prevents two full-backup utilities racing on this cluster.
metrics=${BACKUP_METRICS_DIR:-/var/lib/pycil/backup-metrics}
exec 9>"$metrics/backup.lock"
flock -n 9 || { echo 'Another full backup is running' >&2; exit 1; }
started=$(date +%s)
previous_success=0
if [ -f "$metrics/backup.prom" ]; then
    previous_success=$(awk '$1 == "pycil_backup_last_success_timestamp_seconds" {print $2}' "$metrics/backup.prom")
fi
previous_success=${previous_success:-0}
write_metrics() {
    outcome=$1
    duration=$2
    size=$3
    success=$4
    temp=$(mktemp "$metrics/.backup.XXXXXX")
    cat >"$temp" <<METRICS
# TYPE pycil_backup_last_attempt_timestamp_seconds gauge
pycil_backup_last_attempt_timestamp_seconds $started
# TYPE pycil_backup_last_success_timestamp_seconds gauge
pycil_backup_last_success_timestamp_seconds $success
# TYPE pycil_backup_last_attempt_success gauge
pycil_backup_last_attempt_success $outcome
# TYPE pycil_backup_running gauge
pycil_backup_running $running
# TYPE pycil_backup_duration_seconds gauge
pycil_backup_duration_seconds $duration
# TYPE pycil_backup_compressed_bytes gauge
pycil_backup_compressed_bytes $size
METRICS
    chmod 644 "$temp"
    mv "$temp" "$metrics/backup.prom"
}
running=1
write_metrics 0 0 0 "$previous_success"
finish() {
    result=$?
    trap - EXIT
    running=0
    if [ "$result" -ne 0 ]; then
        write_metrics 0 "$(($(date +%s) - started))" 0 "$previous_success"
        echo 'Full backup failed; last success preserved' >&2
    fi
    exit "$result"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

attempt=$(cat /proc/sys/kernel/random/uuid)
export WALG_SENTINEL_USER_DATA
WALG_SENTINEL_USER_DATA=$(jq -nc --arg attempt "$attempt" \
    --arg fingerprint "${BACKUP_KEY_FINGERPRINT:?required}" \
    '{attempt:$attempt,encryption_key_fingerprint:$fingerprint}')
timeout --signal=TERM --kill-after=30s "${BACKUP_TIMEOUT_SECONDS:-3300}" \
    wal-g backup-push "${PGDATA:?required}"
# backup-list only lists completed sentinels; match this invocation, not an older base.
completed=$(timeout 60 wal-g backup-list --detail --json | \
    jq -ce --arg attempt "$attempt" '[.[] | select(.user_data.attempt == $attempt)] | if length == 1 then .[0] else error("Completed sentinel missing") end')
printf '%s\n' "$completed" >"$metrics/.last-completed.json"
mv "$metrics/.last-completed.json" "$metrics/last-completed.json"
size=$(printf '%s\n' "$completed" | jq -er '.compressed_size | select(type == "number" and . >= 0)')
running=0
write_metrics 1 "$(($(date +%s) - started))" "$size" "$(date +%s)"
echo 'Full backup completed and sentinel verified'
