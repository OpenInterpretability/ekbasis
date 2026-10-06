#!/bin/bash
# WS-RA2 local services, each with a PID file (stopped only by those PIDs). Shares the real apps with RA; own ports:
#   tunnel  127.0.0.1:18574 -> 127.0.0.1:${EKBASIS_REMOTE_PORT:-8544} on $EKBASIS_SSH, only when EKBASIS_SSH is set
#   foresee :8791 (foresee_ra2.py -> tunnel)      spec :8793 (adapters/spec_server2.py)
#   services.sh start | stop | status
set -u
H="$(cd "$(dirname "$0")" && pwd)"; R2="$(cd "$H/.." && pwd)"; P="$R2/logs/pids"; mkdir -p "$P" "$R2/logs"
up() { [ -f "$P/$1.pid" ] && kill -0 "$(cat "$P/$1.pid")" 2>/dev/null; }
start_one() { local n="$1"; shift; if up "$n"; then echo "$n already up (PID $(cat "$P/$n.pid"))"; return; fi
  nohup "$@" > "$R2/logs/$n.log" 2>&1 < /dev/null & echo $! > "$P/$n.pid"; echo "$n started (PID $!)"; }
case "${1:-status}" in
  start)
    [ -n "${EKBASIS_SSH:-}" ] && start_one tunnel ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ConnectTimeout=20 -L 18574:127.0.0.1:${EKBASIS_REMOTE_PORT:-8544} $EKBASIS_SSH
    start_one foresee env PORT=8791 EKBASIS_URL="${EKBASIS_URL:-http://127.0.0.1:18574}" python3 "$H/foresee_ra2.py"
    start_one spec env PORT=8793 python3 "$R2/adapters/spec_server2.py"
    sleep 3; "$0" status ;;
  stop) for n in spec foresee tunnel; do if up "$n"; then kill "$(cat "$P/$n.pid")" && echo "$n stopped"; fi; rm -f "$P/$n.pid"; done ;;
  status)
    for n in tunnel foresee spec; do up "$n" && echo "$n up (PID $(cat "$P/$n.pid"))" || echo "$n down"; done
    curl -s -m 5 127.0.0.1:8791/health | head -c 160; echo; curl -s -m 5 127.0.0.1:8793/ | head -c 100; echo ;;
esac
