# V43 round-2 winner in the look-when-unsure loop

Written on 2026-10-03 before any chain of this test ran (criteria fixed in advance).

## Question

Round 2's winner (`sw_r2err`, trained on its own mined errors) keeps far fewer confident errors on single questions.
Does that make the look-when-unsure loop cheaper or safer over long chains?

## Model

`sw_r2err/ckpt_300` fused into Eikos-27B (`merge_lora.py`), served like the release (vLLM 0.30, `serve.py`), three
replicas. First a fidelity check: 600 of the 15,008 confident-errors items through the API against the trainer's readout
of the same adapter (the same answer expected on at least 97% of them; otherwise the chains do not run).

## Chains

`long_chain3.py`, the same worlds, lengths, seeds and modes as the release model's saved runs: containers, lamps,
machines (4 chains per length) and card orderings (8 per length), 100 and 200 actions; never looking (with per-step
traces), chain confidence below 0.5, below 0.9, and below 0.9 with checks (the client's default).

## Measures, against the release model's saved chains (same seeds)

Whole state exact at the end; steps wrong along the way per 100 actions; looks per 100 actions; from the never-looking
traces, wrong steps per 100 and the share of them given a probability of 0.9 or more.

## The loop is better if

- with the chain rule alone (below 0.9, no checks), the steps wrong along the way per 100 actions, pooled over the four
  worlds, are lower than the release model's (0.73);
- with the default (below 0.9 with checks), every chain still ends exact, the steps wrong along the way are not higher,
  and the looks per 100 actions are not higher by more than 10%;
- in the never-looking traces of the trained worlds, a smaller share of the wrong steps comes with a probability of 0.9
  or more.
