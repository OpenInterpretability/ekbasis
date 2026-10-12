# The API scorecard

`scorecard.py` measures what a user of an Ekbasis endpoint gets, the same way every time, so every change to the model,
the server, the gateway or the client is compared with the runs before it (`history.jsonl`, one line per run).

```
python3 scorecard/scorecard.py fetch                       # fixed items from the published sets (fixed seeds)
python3 scorecard/scorecard.py run --tag after-change      # hosted API by default; --url for another endpoint
python3 scorecard/scorecard.py run --engine subq --no-chains   # the same items on another decision API
python3 scorecard/scorecard.py report                      # every run side by side (markdown)
```

| Measured | How |
|---|---|
| Quality per suite | accuracy, confident errors (wrong at ≥ 0.9) per 100, Brier score, ECE |
| Time | client-side p50 / p90 / p99, and the server's own split (`server-timing`: auth, queue, model) |
| Cost | input tokens per check (usage or `X-Ekbasis-Metered-Tokens`) and US$ per 1,000 checks at `--price` |
| Reliability | requests that failed after retries |
| Chains | `simulate` with `observe` on two small worlds: exact final states, looks per 100 actions, seconds per action |

Suites: `git3_known`, `git3_held` (the release's git sets, real git), `guard_held` (the larger guard set, held-out
command types), `worlds` (world families never trained), `intent` (agent steps from the published-attack replay), and
the chains. None of their items is in the training data. Rule of use: a change ships when the scorecard shows no
quality loss beyond noise and the time, cost or quality it targets moved the way it was meant to.
