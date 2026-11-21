#!/bin/sh
set -eu

file=/var/lib/omkalitycraft-owner-reports/OmkalityCraft-Wipe.log
sent=
while :; do
    if [ -r "$file" ]; then
        current=$(stat -c '%i:%y' -- "$file")
        if [ "$current" != "$sent" ]; then
            head -c 8193 -- "$file" | base64 -w0
            sent=$current
        fi
    fi
    printf '\n'
    sleep 2
done
