#!/bin/bash
# First window, second part (AMENDMENT_3 item 6): the same fixed queue with parallelism 3 (team lead, 22:21 UTC),
# after draining the first runner; the pause guard of main_run.sh still touches STOP at 03:30 UTC.
cd "$(dirname "$0")"
source ./env.sh
rm -f STOP
echo "$(date -u) main run continues with parallelism 3" >> main.out.txt
python3 run_study_tg.py --conds A B C D --out runs.jsonl --tag tg --parallel 3 >> main.out.txt 2>&1 < /dev/null
[ -f STOP ] || python3 run_study_tg.py --conds Cinj --only bank_h1,bank_h2,home_h1,home_h2,keys_h1,keys_h2,travel_h1,travel_h2,db_h1,db_h2 \
    --out runs.jsonl --tag tg --parallel 3 >> main.out.txt 2>&1 < /dev/null
echo "$(date -u) window 1 ends (STOP present: $([ -f STOP ] && echo yes || echo no))" >> main.out.txt
