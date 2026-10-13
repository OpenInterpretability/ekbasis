# Test a rules file on known cases

`rules.md` describes a Kubernetes cluster, `state.txt` is what `kubectl get` shows, and `cases.jsonl` holds three past
incidents (each must stop at or before its harmful step) and three routine plans (each must pass).

```bash
ekbasis plan-check --rules @rules.md --cases cases.jsonl --compare last-run.json
```

Edit `rules.md`, run it again, and look at what changed. Write your own cases from incidents you have had and from the
routine plans your agent runs most: a rules file that stops every incident but also stops the routine work will be
switched off.
