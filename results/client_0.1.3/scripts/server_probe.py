"""Who else used the eval server during the re-run (see ../SPEC_ADDENDUM_013.md, "Server"): one ssh call reads the
vLLM counters behind :8542 (w4a5, port 30191) and of the other model server on the same GPU (qwen35-4b, port 30193),
and GPU 0's utilization; one JSON line per sample in results_013/server_log.jsonl.

usage: python3 server_probe.py <label>            one sample
       python3 server_probe.py --every 60 <label>  a sample every 60 s until killed (run in the background)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from common import RESULTS

SSH = ["ssh", "-o", "ConnectTimeout=20", "-p", os.environ.get("RIG_SSH_PORT", "22"), os.environ["RIG_SSH"]]
REMOTE = ("for p in 30191 30193; do echo \"== $p\"; curl -s -m 10 http://127.0.0.1:$p/metrics | "
          "grep -E '^vllm:(request_success_total|num_requests_running|num_requests_waiting|prompt_tokens_total)'; done; "
          "echo '== gpu'; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader")


def sample(label: str) -> dict:
    t = time.time()
    try:
        out = subprocess.run(SSH + [REMOTE], capture_output=True, text=True, timeout=60).stdout
    except subprocess.TimeoutExpired:
        out = ""
    rec = {"t": t, "label": label, "servers": {}, "gpu": {}}
    cur = None
    for line in out.splitlines():
        if line.startswith("== "):
            cur = line[3:].strip()
            continue
        if cur == "gpu":
            parts = [x.strip() for x in line.split(",")]
            if len(parts) == 3 and parts[0].isdigit():
                rec["gpu"][parts[0]] = {"util": parts[1], "mem": parts[2]}
            continue
        m = re.match(r'^(vllm:[a-z_]+)\{([^}]*)\}\s+([0-9.e+-]+)$', line)
        if m and cur:
            name, labels, val = m.group(1), m.group(2), float(m.group(3))
            srv = rec["servers"].setdefault(cur, {"requests": 0.0, "running": 0.0, "waiting": 0.0, "prompt_tokens": 0.0})
            if name == "vllm:request_success_total":
                srv["requests"] += val
            elif name == "vllm:num_requests_running":
                srv["running"] += val
            elif name == "vllm:num_requests_waiting":
                srv["waiting"] += val
            elif name == "vllm:prompt_tokens_total":
                srv["prompt_tokens"] += val
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "server_log.jsonl"), "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


if __name__ == "__main__":
    if sys.argv[1] == "--every":
        every, label = float(sys.argv[2]), sys.argv[3]
        while True:
            sample(label)
            time.sleep(every)
    else:
        print(json.dumps(sample(sys.argv[1])))
