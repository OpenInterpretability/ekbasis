"""LATENT: trajectories from the training world simulators (conseq/envs.py), 10 steps each, the true state text at
every step and one question with its gold answer per state. Seeds fixed per split."""
import json, random, sys
sys.path.insert(0, "/Volumes/SSD Major/news/decision_model/conseq")
from envs import TRAIN_WORLDS, HELDOUT_WORLDS, make_trajectory, STATE_Q

STEPS = 10
PLAN = {"train": (101, 300), "val": (202, 60), "test": (303, 120)}          # worlds the predictor trains on
PLAN_HELD = {"readout": (101, 200), "test": (303, 120)}                       # worlds it never sees
out = open("/Volumes/SSD Major/news/decision_model/mission/LATENT/data.jsonl", "w")

def options(q):
    if q["type"] == "noul":
        return ["yes", "no"]
    return list(q["options"]) if "options" in q else list(q["criteria"])

def gold_label(q, gold):
    return ("yes" if gold else "no") if q["type"] == "noul" else str(gold)

n = 0
for group, worlds, plan in (("trainworld", TRAIN_WORLDS, PLAN), ("heldout", HELDOUT_WORLDS, PLAN_HELD)):
    for w in worlds:
        for split, (seed, count) in plan.items():
            rng = random.Random(seed * 1000 + hash(w.name) % 997)
            for i in range(count):
                t = make_trajectory(w, STEPS, rng.choice(STATE_Q[w.name]), rng)
                qs = [{"t": q["t"], "qtype": q["qtype"], "question": q["question"]["instructions"],
                       "options": options(q["question"]), "gold": gold_label(q["question"], q["gold"]),
                       "qobj": q["question"]} for q in t["questions"]]
                for q in qs:
                    assert q["gold"] in q["options"], (w.name, q)
                out.write(json.dumps({"id": f"{w.name}-{split}-{i}", "group": group, "world": w.name, "split": split,
                                      "rules": t["rules"], "states": t["states"], "actions": t["actions"], "questions": qs,
                                      "floor_note": w.floor_note(), "ceiling_note": w.ceiling_note()}) + "\n")
                n += 1
print("trajectories:", n)
