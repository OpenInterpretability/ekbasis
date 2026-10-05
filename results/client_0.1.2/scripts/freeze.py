"""Freeze the candidate client after the dev runs: writes client_012/FROZEN.sha256 (the sha256 of every module of the
package and the time). The confirmation generator and runs refuse to start without it or if the code changed.
python3 eval/freeze.py"""
import datetime

from common import FROZEN, freeze_lines

with open(FROZEN, "w") as f:
    f.write(f"# frozen {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}\n")
    f.write("\n".join(freeze_lines()) + "\n")
print(open(FROZEN).read())
