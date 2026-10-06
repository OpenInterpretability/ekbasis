#!/bin/bash
# WS-RA local services, each with a PID file (stopped only by those PIDs):
#   tunnel   127.0.0.1:18564 -> 127.0.0.1:${EKBASIS_REMOTE_PORT:-8544} on $EKBASIS_SSH, only when EKBASIS_SSH is set
#   tunnel4b 127.0.0.1:18596 -> rig 127.0.0.1:30193 (Qwen 3.5 4B, Caio's GLM-session server; used, never restarted)
#   tunnelq  127.0.0.1:18595 -> rig 127.0.0.1:30194 (Qwen 3.5 9B, Caio's GLM-session server; used, never restarted; 18594 is the GLM session's own tunnel)
#   foresee  :8781 (foresee_ra.py -> tunnel)       oracle :8782 (oracle_ra.py, Claude Sonnet; only for oracle_llm runs)
#   spec     :8783 (adapters/spec_server.py)
#   services.sh start [oracle] | stop | status      (QWEN=1 also opens the two Qwen tunnels; the Qwen servers were stopped 06/10)
set -u
H="$(cd "$(dirname "$0")" && pwd)"; RA="$(cd "$H/.." && pwd)"; P="$RA/logs/pids"; mkdir -p "$P" "$RA/logs"
up() { [ -f "$P/$1.pid" ] && kill -0 "$(cat "$P/$1.pid")" 2>/dev/null; }
start_one() {  # name, command...
  local n="$1"; shift
  if up "$n"; then echo "$n already up (PID $(cat "$P/$n.pid"))"; return; fi
  nohup "$@" > "$RA/logs/$n.log" 2>&1 < /dev/null &
  echo $! > "$P/$n.pid"; echo "$n started (PID $!)"
}
case "${1:-status}" in
  start)
    [ -n "${EKBASIS_SSH:-}" ] && start_one tunnel ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ConnectTimeout=20 -L 18564:127.0.0.1:${EKBASIS_REMOTE_PORT:-8544} $EKBASIS_SSH
    [ "${QWEN:-0}" = 1 ] && start_one tunnelq ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ConnectTimeout=20 -L 18595:127.0.0.1:30194 ${QWEN_SSH:?set QWEN_SSH to the SSH destination of the Qwen servers}
    [ "${QWEN:-0}" = 1 ] && start_one tunnel4b ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ConnectTimeout=20 -L 18596:127.0.0.1:30193 ${QWEN_SSH:?set QWEN_SSH to the SSH destination of the Qwen servers}
    start_one foresee env PORT=8781 EKBASIS_URL="${EKBASIS_URL:-http://127.0.0.1:18564}" python3 "$H/foresee_ra.py"
    start_one spec env PORT=8783 python3 "$RA/adapters/spec_server.py"
    [ "${2:-}" = oracle ] && start_one oracle env PORT=8782 python3 "$H/oracle_ra.py"
    sleep 3; "$0" status ;;
  stop)
    for n in oracle spec foresee tunnel4b tunnelq tunnel; do
      if up "$n"; then kill "$(cat "$P/$n.pid")" && echo "$n stopped"; fi; rm -f "$P/$n.pid"
    done ;;
  status)
    for n in tunnel tunnelq tunnel4b foresee spec oracle; do up "$n" && echo "$n up (PID $(cat "$P/$n.pid"))" || echo "$n down"; done
    curl -s -m 5 127.0.0.1:8781/health | head -c 160; echo
    curl -s -m 5 127.0.0.1:8783/ | head -c 100; echo ;;
esac
