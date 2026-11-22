#!/bin/sh
set -eu

file=/var/lib/omkalitycraft-owner-reports/OmkalityCraft-Wipe.log

report_version() {
    stat -c '%d:%i:%y' -- "$file" 2>/dev/null || :
}

# A report already present at connection time is history.
sent=$(report_version)
while :; do
    current=$(report_version)
    if [ -n "$current" ] && [ "$current" != "$sent" ]; then
        head -c 8193 -- "$file" | base64 -w0
        sent=$current
    fi
    printf '\n'
    sleep 2
done
