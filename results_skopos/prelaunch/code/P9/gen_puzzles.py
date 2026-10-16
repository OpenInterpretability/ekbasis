"""P9: the puzzles of the planning-by-search evaluation, regenerated with the generating code itself: llm_agent_gen.py
(lib/, identical to the rig's) executed up to and including pickle.dump (no LLM call), with the settings of the runs that
made them on the rig: agent = N=30, HS=3,5 (run_agent_exp.sh line 11); agent_hard = N=30, HS=8,12 (run_agent_hard.sh
line 10). The rig's puzzles.pkl files were in /dev/shm and are gone; common/identity_offline.py checks the regenerated
ones against Ekbasis-27B's published question counts.   python3 gen_puzzles.py <out root>"""
import os
import sys

LIB = os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
sys.path.insert(0, LIB)
root = sys.argv[1]
src = open(os.path.join(LIB, "llm_agent_gen.py")).read()
src = src[:src.index("\n\ndef head(p):")]   # the puzzles, their pickle and the count line; nothing after
for d, hs in (("agent", "3,5"), ("agent_hard", "8,12")):
    os.environ["N"], os.environ["HS"] = "30", hs
    sys.argv = ["llm_agent_gen.py", os.path.join(root, d)]
    exec(compile(src, "llm_agent_gen.py", "exec"), {"__name__": "puzzles"})
