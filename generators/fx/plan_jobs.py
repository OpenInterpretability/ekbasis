"""Print the generation jobs (family part cap) for the families given on the command line, or for every registered
family when none is given. Caps per SPEC: core 5000 (+ val 250), FX-built 6000 (+ val 300), held-out 4000."""
import sys
sys.path.insert(0, "/root/decis/mission/FX/factory")
from fx_registry import CORE, split_of
from fx_new_registry import NEW
fams = sys.argv[1:] or (list(CORE) + list(NEW))
for f in fams:
    sp = split_of(f)
    app = f.startswith(("vk_", "mm_"))
    w = 16 if f.startswith("vk_") else (4 if app else 64)
    if sp.startswith("eval"):
        print(f, "eval", 2500 if f.startswith("vk_") else (3000 if f.startswith("mm_") else 4000), w)
    elif f in CORE:
        print(f, "train", 5000, w); print(f, "val", 250, w)
    else:
        print(f, "train", 4000 if app else 6000, w); print(f, "val", 200 if app else 300, w)
