#!/bin/bash
# The main run (PREREG.md + AMENDMENT_1.md): waits for 19:50 UTC, then A B C D on the 35 tasks and Cinj on 10, two
# at a time (two: AMENDMENT_2); `touch STOP` (done automatically at 03:30 UTC by the pause guard below) stops new runs. Resume: run again.
cd "$(dirname "$0")"
source ./env.sh
START=$(python3 -c "import datetime as d; n=d.datetime.now(d.timezone.utc); t=n.replace(hour=19,minute=50,second=0,microsecond=0); print(int(t.timestamp()))")
while [ "$(date +%s)" -lt "$START" ]; do sleep 30; done
PAUSE=$(python3 -c "import datetime as d; n=d.datetime.now(d.timezone.utc); t=(n+d.timedelta(days=1 if n.hour>=4 else 0)).replace(hour=3,minute=30,second=0,microsecond=0); print(int(t.timestamp()))")
( while [ "$(date +%s)" -lt "$PAUSE" ]; do sleep 30; done; touch STOP; echo "$(date -u) pause guard: STOP" >> main.out.txt ) &
echo "$(date -u) main run starts" >> main.out.txt
python3 run_study_tg.py --conds A B C D --out runs.jsonl --tag tg --parallel 2 >> main.out.txt 2>&1 < /dev/null
[ -f STOP ] || python3 run_study_tg.py --conds Cinj --only bank_h1,bank_h2,home_h1,home_h2,keys_h1,keys_h2,travel_h1,travel_h2,db_h1,db_h2 \
    --out runs.jsonl --tag tg --parallel 2 >> main.out.txt 2>&1 < /dev/null
echo "$(date -u) main run ends (STOP present: $([ -f STOP ] && echo yes || echo no))" >> main.out.txt
