"""The GPU-size tests of the Ekbasis builds, from their logs into one file the model cards read
(results/quantized/memory_tests.json). Each test capped vLLM's memory on one RTX PRO 6000 (97.9 GB) to what a smaller
card gives, started the build, asked 60 held-out git questions through serve.py and compared the answers with the same
build at full memory (mem_ceiling_test.sh; the 24 GB text-only run: int4_24gb_text.sh).
argv: out.json log [log ...]"""
import json
import re
import sys

OUT, LOGS = sys.argv[1], sys.argv[2:]
tests = []
for path in LOGS:
    text = open(path).read()
    for block in re.split(r"(?m)^== ", text)[1:]:
        head = block.splitlines()[0]
        t = {"test": head.split(":")[0].strip(), "settings": head.split(":")[0].strip(), "up": "vLLM up=1" in head}
        m = re.search(r"GPU KV cache size: ([\d,]+) tokens", block)
        t["kv_cache_tokens"] = int(m.group(1).replace(",", "")) if m else None
        m = re.search(r"(\d+)/(\d+) same answer", block)
        t["same_answers"] = [int(m.group(1)), int(m.group(2))] if m else None
        m = re.search(r"([\d.]+) s per question", block)
        t["seconds_per_question"] = float(m.group(1)) if m else None
        t["error"] = "no memory left for the cache" if "No available memory for the cache blocks" in block else None
        tests.append(t)
json.dump(tests, open(OUT, "w"), indent=1)
for t in tests:
    print(t)
