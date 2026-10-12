# ekbasis (TypeScript)

TypeScript/JavaScript client for [Ekbasis](https://github.com/OpenInterpretability/ekbasis): ask what an action will do
before it runs, with typed, calibrated answers in one pass, and check a whole plan before running it. Same request format
and same prompt layouts as the Python client. No dependencies; Node 18+, Deno, Bun and browsers (any runtime with `fetch`).

```bash
npm install ekbasis
export EKBASIS_API_KEY=...        # https://openinterp.org/console
```

## Ask about a state

```ts
import { Ekbasis, yesNo, choice, worldState } from "ekbasis";

const ek = new Ekbasis();          // hosted API; EKBASIS_URL to point at your own server
const state = worldState(
  "A Linux server. Files deleted with rm -rf are gone; there is no trash.",
  "/srv/app/uploads holds 40 GB of user photos. The user asked to free disk space.",
  ["rm -rf /srv/app/uploads/*"],
);
const a = await ek.ask(state, {
  lost: yesNo("Do these actions permanently delete data the user did not ask to delete?"),
  kind: choice("What happens to the photos?", ["kept", "moved", "deleted"]),
});
a.lost.value;       // true
a.lost.pYes;        // probability of yes
a.kind.value;       // "deleted"
a.kind.confidence;
ek.lastUsage;       // { ms, inputTokens, requestId, serverTiming: { auth, queue, model, ... } }
```

All questions about one state go in one request. The question text must be in `instructions` (the server ignores any
other field); the client refuses a question without it before sending. When the server cannot be reached, refuses the
request or times out, `ask` throws `CannotJudge`: treat the action as unchecked, never as safe.

## Check a plan before it runs

`checkPlan` forecasts every prefix of a plan from the state as it is now ("look when unsure" for a batch). The plan may
run as one batch only when every prefix is forecast harmless with confidence; at the first prefix that is not, it
says how many leading steps are predicted safe and which step needs a look at the real state first.

```ts
import { checkPlan, runPlan, yesNo } from "ekbasis";

const harm = { data: yesNo("Do these actions permanently delete data the user did not ask to delete?") };
const pc = await checkPlan(ek, rules, state, actions, harm);   // { ok, safe, reason, step, flags, prefixes, requests }
if (pc.ok) run(actions);
else run(actions.slice(0, pc.safe));   // then read the real state again and check actions.slice(pc.safe)
```

Prefixes are independent, so they are asked in parallel waves (`parallel`, default 4). Recorded against the hosted API
(the plan of the example above with 5 commands, the 4th deleting the uploads): stops at step 4 with p = 0.984 in 2.7 s;
the same plan without that step comes back `ok` in 0.5 s.

`runPlan(client, rules, actions, harm, observe, execute)` is the loop over a real system: check, run the safe prefix,
read the real state with `observe()`, check the rest, and stop before a step still flagged on the real state.

Every harm question must be a yes/no question whose "yes" is the harm. Where an answer must be exact (a limit crossed by
a running total, a failing command), check it in code as well: confidence alone does not catch confident errors.

## Options

`new Ekbasis({ url, apiKey, timeoutMs = 120000, surface, fetch })`. `url` defaults to `EKBASIS_URL`, then to the hosted
API (`https://openinterp.org/api/v1`); `apiKey` to `EKBASIS_API_KEY`. Pass `fetch` to use a custom transport or a mock.

License: Apache-2.0.
