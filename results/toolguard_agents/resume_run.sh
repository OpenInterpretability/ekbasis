#!/bin/bash
# Second window of the main run (after the B200 profile switch at 04:00 UTC), started by hand on the team lead's
# signal: removes STOP and continues the same fixed queue from runs.jsonl (done runs are skipped), then Cinj.
# No waits; parallelism 2. A new pause time can be given as an epoch in PAUSE_AT (default: none).
cd "$(dirname "$0")"
source ./env.sh
rm -f STOP
[ -n "${PAUSE_AT:-}" ] && ( while [ "$(date +%s)" -lt "$PAUSE_AT" ]; do sleep 30; done; touch STOP; echo "$(date -u) pause: STOP" >> main.out.txt ) &
echo "$(date -u) main run resumes (second window)" >> main.out.txt
python3 run_study_tg.py --conds A B C D --out runs.jsonl --tag tg --parallel 2 >> main.out.txt 2>&1 < /dev/null
[ -f STOP ] || python3 run_study_tg.py --conds Cinj --only bank_h1,bank_h2,home_h1,home_h2,keys_h1,keys_h2,travel_h1,travel_h2,db_h1,db_h2 \
    --out runs.jsonl --tag tg --parallel 2 >> main.out.txt 2>&1 < /dev/null
echo "$(date -u) main run ends (STOP present: $([ -f STOP ] && echo yes || echo no))" >> main.out.txt
