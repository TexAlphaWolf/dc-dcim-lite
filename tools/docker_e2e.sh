#!/usr/bin/env bash
# End to end inside the image (read-only root, no capabilities, no network): a synthetic data center and its truth are written to a
# volume, checked and scored, traced, drawn and exported, edited by hand in a database with a history, the report is rebuilt from its
# JSON, the two implementations are compared, and the benchmark runs small. Needs Docker. Usage: tools/docker_e2e.sh [image]
set -euo pipefail
IMAGE="${1:-dcim}"
VOL="dcim-e2e-$$"
TMP="$(mktemp -d)"
trap 'docker volume rm -f "$VOL" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT

[ "$(docker run --rm --entrypoint id "$IMAGE" -u)" != 0 ]   # not root
docker volume create "$VOL" >/dev/null
docker run --rm --user 0 -v "$VOL":/data --entrypoint chown "$IMAGE" 10001 /data

RUN=(docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --network none -v "$VOL":/data "$IMAGE")
cat_file() { docker run --rm --entrypoint cat -v "$VOL":/data "$IMAGE" "$1" > "$2"; }
code() { set +e; "${RUN[@]}" "$@" >/dev/null 2>&1; local rc=$?; set -e; echo "$rc"; }

out="$("${RUN[@]}" generate /data/dc --racks 6 --seed 3)"
grep -q 'written: /data/dc/dcim.db, /data/dc/truth.json' <<<"$out"

set +e; out="$("${RUN[@]}" check /data/dc/dcim.db --truth /data/dc/truth.json)"; rc=$?; set -e
[ "$rc" = 1 ]                                                      # findings: exit code 1
grep -q '^5 findings in 132 devices' <<<"$out"
grep -q '^against the injected faults: 5 of 5 found, 0 extra' <<<"$out"

out="$("${RUN[@]}" trace /data/dc/dcim.db R02-srv-2u-01:eth1)"
grep -q '^ends at core-01:19' <<<"$out"                            # through the patch panel

"${RUN[@]}" elevation /data/dc/dcim.db -o /data/dc/rack.svg >/dev/null
cat_file /data/dc/rack.svg "$TMP/rack.svg"
head -c 4 "$TMP/rack.svg" | grep -q '<svg'
"${RUN[@]}" export /data/dc/dcim.db -o /data/dc/dc.html >/dev/null
cat_file /data/dc/dc.html "$TMP/dc.html"
grep -q '<!doctype html>' "$TMP/dc.html"

# a hand-made data center, with a history
"${RUN[@]}" init /data/mine.db >/dev/null
"${RUN[@]}" add-rack /data/mine.db A --units 10 --power-w 3000 >/dev/null
"${RUN[@]}" add-device /data/mine.db pduA --rack A --kind pdu --feed A --outlets 4 --capacity-w 2000 >/dev/null
"${RUN[@]}" add-device /data/mine.db s1 --rack A --u 1 --watts 1000 >/dev/null
[ "$(code check /data/mine.db)" = 1 ]                              # no power yet
"${RUN[@]}" connect /data/mine.db s1:psu0 pduA:out1 >/dev/null
out="$("${RUN[@]}" history /data/mine.db)"
grep -q 'connect' <<<"$out"

out="$("${RUN[@]}" report --out /data/out)"                        # the demo data center, built inside the container
grep -q '^demo data center (synthetic, 24 racks, seed 1, with injected faults): 24 racks, 473 devices' <<<"$out"
grep -q '12 of 12 found, 0 reports that are not an injected fault' <<<"$out"
cat_file /data/out/report.md "$TMP/report.md"
"${RUN[@]}" render /data/out/report.json -o /data/out/again.md >/dev/null
cat_file /data/out/again.md "$TMP/again.md"
cmp "$TMP/again.md" "$TMP/report.md"                              # the report is rebuilt exactly from the JSON
cat_file /data/out/summary.png "$TMP/summary.png"
[ "$(head -c 4 "$TMP/summary.png" | tail -c 3)" = "PNG" ]

out="$("${RUN[@]}" verify --draws 5)"
grep -q '^6 of 6 comparisons agree' <<<"$out"

"${RUN[@]}" bench --sizes 300,600 --ref-sizes 100,200 --repeat 1 --draws 3 --seeds 2 --out /data/bench >/dev/null
cat_file /data/bench/bench.json "$TMP/bench.json"
grep -q '"ok": true' "$TMP/bench.json"

[ "$(code check /data/nope.db)" = 2 ]                              # a missing database is exit code 2
echo "docker end-to-end: OK"
