#!/bin/bash
set -eu
export LC_ALL=C

directory=/var/lib/omkalitycraft-owner-reports
file="$directory/OmkalityCraft-Wipe.log"

report_version() {
    stat -c '%d:%i:%y' -- "$1" 2>/dev/null || :
}

shopt -s nullglob
declare -A sent_crashes=()
for crash in "$directory"/client-crash-*.json; do
    sent_crashes["$crash"]=$(report_version "$crash")
done

# A report already present at connection time is history.
sent=$(report_version "$file")
while :; do
    if code=$(tmux -L omkalitycraft-owner-tui-hourly show-buffer -b omk-invite-clipboard \; delete-buffer -b omk-invite-clipboard 2>/dev/null); then
        case "$code" in
            ''|*[!A-Za-z0-9_-]*) ;;
            *) if [[ ${#code} -le 128 ]]; then
                   printf 'CLIP '
                   printf '%s' "$code" | base64 -w0
                   printf '\n'
               fi ;;
        esac
    fi
    current=$(report_version "$file")
    if [ -n "$current" ] && [ "$current" != "$sent" ]; then
        head -c 8193 -- "$file" | base64 -w0
        sent=$current
    fi
    printf '\n'
    for crash in "$directory"/client-crash-*.json; do
        [[ -f "$crash" && ! -L "$crash" ]] || continue
        name=${crash##*/}
        [[ "$name" =~ ^client-crash-([0-9a-f]{32})\.json$ ]] || continue
        id=${BASH_REMATCH[1]}
        current=$(report_version "$crash")
        if [[ -n "$current" && "$current" != "${sent_crashes[$crash]-}" ]]; then
            if data=$(head -c 98305 -- "$crash" | base64 -w0) && [[ -n "$data" ]]; then
                printf 'CRASH %s %s\n' "$id" "$data"
                sent_crashes["$crash"]=$current
            fi
        fi
    done
    for crash in "${!sent_crashes[@]}"; do
        [[ -e "$crash" ]] || unset 'sent_crashes[$crash]'
    done
    sleep 1
done
