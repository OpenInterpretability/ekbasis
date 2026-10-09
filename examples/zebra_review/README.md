# Ekbasis reviews an animation state machine (outside its training domains)

An experiment proposed by the project owner: build the best possible animated SVG of a running zebra,
using the Ekbasis foresee API at every step to improve quality. The model was **never trained on SVG,
animation, or anything like it** — its domains are app consequences (banking, git, shell, SQL, …).

**Result: it cannot compose art (it drew nothing), but it audited consequences usefully — repeatedly,
outside its training distribution.** Six foresee calls, ~490 ms each, every one useful:

| step | asked | answer | confidence |
|---|---|---|---|
| 1 | "if I shorten the gait cycle to 0.30s and raise the bob, what breaks?" | **"the hooves slide because the world scroll speed no longer matches the gait"** — the real foot-sliding artifact | 0.82 |
| 2 | "do the layers tile seamlessly?" / "do the dust puffs align?" | none / yes | 0.99 / 0.94 |
| 2 | "do the hooves still slide?" | honestly uncertain (router would escalate; resolved by measurement) | **0.48** |
| 3 | "what ground speed does 2 body lengths per stride need?" | **"600 px per 0.55s = 1090 px/s"** — the arithmetic, correct | 0.98 |
| 3 | "what appears if the ground is sped to that?" | "the grass tufts strobe and the legs look slow relative to the world" | 0.57 |
| 4 | anatomy check with real equine gait rules | the design had **only one suspension phase (the real gallop has two)** and the missing **neck pump** was the top realism gain | 0.69 / **0.95** |
| 4 | final | "two suspensions, pumping neck, correct order" (0.84); "it is done" (0.86) | |

**The pattern**: state the real domain knowledge in the rules (the gallop phases, the ground speed), state
the current design as the state, and the model verifies the **consistency of phases, rates and states** —
the same skill it uses on app state machines. It never draws; it reviews.

Files: `zebra.svg` (the final artifact), `calls.jsonl` (the six foresee calls as sent).
