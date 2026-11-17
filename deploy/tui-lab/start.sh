#!/bin/sh
# Fixed local fixture work. CPU is shared with Java inside the container quota.
set -eu
mkdir -p mods config .java .fixture
cp /runtime/mods/*.jar mods/
cp /seed/exporter.cfg config/prometheus_exporter.cfg
if [ -f /runtime/.omk/core-mods.properties ] && [ ! -f config/omkalitycore-mods.properties ]; then
  cp /runtime/.omk/core-mods.properties config/omkalitycore-mods.properties
fi
if [ ! -f server.properties ]; then cp /seed/server.properties server.properties; fi
printf 'eula=true\n' > eula.txt

case "${OMK_FIXTURE_PROFILE:-alpha}" in
  alpha) period=75; burst=12; offset=30 ;;
  beta) period=110; burst=18; offset=60 ;;
  *) echo 'Unknown TUI fixture profile' >&2; exit 2 ;;
esac

write_phase() {
  printf '{"fixture":true,"phase":"%s","cycle":%s,"period_seconds":%s,"burst_seconds":%s}\n' \
    "$1" "$cycle" "$period" "$burst" > .fixture/load.pending
  mv .fixture/load.pending .fixture/load.json
  printf 'OMK_TUI_LOAD '; cat .fixture/load.json
}
(
  cycle=0
  write_phase idle
  sleep "$offset"
  while true; do
    cycle=$((cycle + 1))
    write_phase burst
    # No input file growth or world edits. timeout bounds each CPU-only pulse.
    result=0
    timeout -s TERM "$burst" sha256sum /dev/zero >/dev/null || result=$?
    if [ "$result" -ne 0 ] && [ "$result" -ne 124 ]; then
      write_phase failed
      exit "$result"
    fi
    write_phase idle
    sleep "$((period - burst))"
  done
) &

exec java -Xms128m -Xmx384m -Duser.home=/data/.java \
  -Dlog4j.configurationFile=/runtime/.omk/log4j2.xml \
  -cp "$(cat /runtime/.omk/classpath)" net.minecraftforge.fml.relauncher.ServerLaunchWrapper nogui
