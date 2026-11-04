umask 077
cleanup() {
    trap '' TERM INT
    test -z "${watchdog:-}" || kill "$watchdog" 2>/dev/null
    test -z "${child:-}" || kill -TERM "$child" 2>/dev/null
    wait
    exit 0
}
trap cleanup TERM INT
while [ ! -s /tmp/launch ]; do sleep 1 & child=$!; wait "$child"; done
read -r name host lease </tmp/launch
parent=$$
(
    while curl -fsS --max-time 2 -o /dev/null -H "Host: $host" -H "X-DCC-Remote-Lease: $lease" http://dcc-remote-panel:8791/api/health; do
        sleep 5
    done
    kill -TERM "$parent"
) >/dev/null 2>&1 &
watchdog=$!
delay=1
while :; do
    zrok2 share public --headless --force-local -n "public:$name" http://dcc-remote-panel:8791 > /tmp/share.log 2>&1 &
    child=$!
    wait "$child"
    code=$?
    if [ "$code" -ne 1 ]; then
        kill "$watchdog" 2>/dev/null
        exit "$code"
    fi
    sleep "$delay" & child=$!
    wait "$child"
    if [ "$delay" -lt 32 ]; then delay=$((delay * 2)); fi
done
