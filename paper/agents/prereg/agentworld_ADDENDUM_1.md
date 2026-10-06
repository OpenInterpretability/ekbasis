# Addendum 1 (2026-10-06, after the freeze, before any AgentWorld forward pass)

Bug fix in `ek_reverse.py` only: the Ekbasis server returns yes/no answers as `{"type": "noul", "probability": p_yes}`
(the way `ekbasis.client.Answer.from_api` reads them), not as a `probabilities` dict. The first fidelity run therefore
read every yes/no answer as missing (A_accumulation: 9 of 10 "not rebuilt") and stopped on an empty list. The fix parses
yes/no answers like the client and keeps "could not rebuild the request" separate from the answer. The reverse run
(R items, all multiple-choice) was not affected and is kept. No change to items, metrics, samples or the decision rule.
The fidelity check is run again with the fixed script.
