# Pre-registration documents (scrubbed copies)

Each study's plan, its addenda and its freeze files, as written before the runs they govern. Only machine paths
were replaced, by the placeholders below; nothing else was changed. `python3 verify_prereg.py` undoes the
substitutions and checks every SHA-256 recorded at a freeze. Addenda were appended to the plans, so an earlier
frozen version is a byte prefix of the published document; the check covers those too.

## Substitutions

| original | placeholder | occurrences |
|---|---|---|
| `/private/tmp/ekb_rt_94332945/` | `<LOCAL_TMP>/` | 2 |
| `/private/tmp/claude-501` | `<LOCAL_CLAUDE_TMP>` | 1 |
| `/root/decis/` | `<SERVER_WORKDIR>/` | 2 |
| `/root/vllm_new_env` | `<SERVER_VENV>` | 1 |
| `/dev/shm/conseq/` | `<SERVER_SHM>/` | 2 |

## Documents

| file | frozen SHA-256 (event; what it covers) | SHA-256 of the original | SHA-256 of this copy |
|---|---|---|---|
| `demo_apps_SPEC.md` | `7674f5c5302f9392…` plan, written before any measurement; its first 7389 bytes<br>`e018063c23e23e01…` with addenda A (before any control run) to C (before any run in tau-bench retail); its first 14726 bytes<br>`88988a92d23b6959…` with addendum D (before any Haiku run); its first 17159 bytes<br>`be07f1cc33c8f542…` with addendum D.1 (cost; before any Haiku study run); its first 18645 bytes<br>`5215a26dedcb2e05…` with addendum D.2 (thinking off; before any new run); its first 19689 bytes<br>`ac87dbb55d8073bb…` with the D.2 note (the control found, before the study runs); the whole document | `ac87dbb55d8073bb…` | `ac87dbb55d8073bb…` |
| `lookahead_SPEC.md` | none recorded | `e8553c8b717b0468…` | `e8553c8b717b0468…` |
| `terminal_SPEC.md` | `3aa101e92f8b68fa…` plan, frozen 2026-10-05T17:48:47Z before the first study pair; its first 18363 bytes | `9c5c35c9771fd12c…` | `c7d81013a87875b7…` |
| `terminal_SPEC_ADDENDUM_013.md` | `41385b3e8d754854…` addendum, frozen 2026-10-06T11:48:40Z before the first paid session; the whole document | `41385b3e8d754854…` | `04dec93913780a10…` |
| `real_apps_SPEC.md` | `c73625be3f8a16c1…` freeze 2: plan and verified tasks, 2026-10-06T12:49:33Z, before the first agent run; its first 11377 bytes<br>`fe86b581977a8ae3…` with addendum B, 2026-10-06T12:54:28Z; its first 12805 bytes<br>`9c789c0574777166…` with addendum C, 2026-10-06T13:07:44Z; its first 14751 bytes<br>`934e8fbe19b3b854…` with addendum D, 2026-10-06T13:10:10Z; its first 15466 bytes<br>`1682d40f2e0ed449…` with addendum E, 2026-10-06T13:28:36Z; its first 16863 bytes<br>`7e703187dc4f71ce…` with addendum F, 2026-10-06T14:19:34Z; its first 17967 bytes<br>`f12e9dc7d2a32e93…` with addendum G, 2026-10-06T14:45:16Z; its first 20099 bytes<br>`f07f48f4f516431e…` with addendum H, 2026-10-06T14:59:14Z; the whole document | `f07f48f4f516431e…` | `f07f48f4f516431e…` |
| `real_apps_followup_SPEC.md` | `3e2d8995b22474a4…` plan, adapter, conditions and analysis, frozen 2026-10-06T17:19:36Z before any task existed; its first 10794 bytes<br>`50bba2f65d2ad3f1…` with freeze 2 (the tasks verified on the real apps), 2026-10-06T17:34:39Z, before any agent run; its first 11796 bytes<br>`08c23c586a00574a…` with addendum A (the pilot's adapter fix), before the first study run; its first 13011 bytes<br>`d788740db38b8cc0…` with addendum B (the spending cap removed, no design change), before the remaining runs; its first 13837 bytes<br>`b2f431626382177d…` with addendum C (mail runs re-judged with normalised bodies, exploratory; release hygiene), after all runs; the whole document | `b2f431626382177d…` | `b2f431626382177d…` |
| `agentworld_SPEC.md` | `0c83f226f9ca62a7…` plan, frozen 2026-10-06T14:57:14Z before any AgentWorld forward pass; the whole document | `0c83f226f9ca62a7…` | `96d0f1bc524cf273…` |
| `agentworld_ADDENDUM_1.md` | `3231803a3d64f711…` addendum 1, after the freeze, before any AgentWorld forward pass; the whole document | `3231803a3d64f711…` | `3231803a3d64f711…` |
| `agentworld_ADDENDUM_2.md` | `c44c2938ab4772de…` addendum 2, about 15:38 UTC, a bug fix after 16 rows of mode (a); the whole document | `c44c2938ab4772de…` | `c44c2938ab4772de…` |
| `agentworld_ADDENDUM_3.md` | `28bd60dd965646f7…` addendum 3, about 16:00 UTC, after mode (a), before any mode (b) forward pass; the whole document | `28bd60dd965646f7…` | `edef1797e5c0a96f…` |
| `agentworld_ADDENDUM_4.md` | `d1dfd270803e9b85…` addendum 4, about 16:15 UTC, before any mode (b) forward pass; the whole document | `d1dfd270803e9b85…` | `76cd2bce4fc8c60d…` |

Notes:

- `demo_apps_SPEC.md`: Dates are in the addenda headings (5 October 2026); the freeze file records hashes without times. Addendum B's task files, judge and apps were hashed with it (freeze/demo_apps_SPEC.sha256).
- `lookahead_SPEC.md`: Written on 5 October 2026 before any agent run, but no hash of the plan itself was recorded: only its tasks and code were hashed (freeze/lookahead_FROZEN_LA.sha256, _LA_v2, _ST).
- `terminal_SPEC.md`: The exploratory extension (E1, E2) at the end was appended after the primary run and before running it, without a new hash.
- `real_apps_SPEC.md`: Freeze 1 (2026-10-06T12:29:54Z) hashed the adapters, rules and questions before any task existed; the plan's hashes from freeze 2 on are listed (times in freeze/real_apps_FROZEN.sha256).
- `real_apps_followup_SPEC.md`: The freeze file records the hashes of addenda A, B and C without a time. Addendum A: the freeze file was last written at 2026-10-06T17:42:50Z and the first study run started at 17:43:09Z (run log, not published). Addendum B was written when the cap was removed, about 2026-10-06T21:00Z, before the remaining runs, after the Haiku results were known. Addendum C was written after all runs, about 2026-10-06T22:00Z.

## Freeze files

The hash lists written at each freeze (tasks, code and plans), in `freeze/`. They name files of the studies'
working folders that are not all published; they record what was fixed and when.

| file | SHA-256 of the original | SHA-256 of this copy |
|---|---|---|
| `freeze/demo_apps_SPEC.sha256` | `0c6be8f7208ca1a8…` | `0c6be8f7208ca1a8…` |
| `freeze/lookahead_FROZEN_LA.sha256` | `f300eba6e4fb0c01…` | `f300eba6e4fb0c01…` |
| `freeze/lookahead_FROZEN_LA_v2.sha256` | `1aef8c0507ad0ba4…` | `1aef8c0507ad0ba4…` |
| `freeze/lookahead_FROZEN_ST.sha256` | `5f2607ed5be6480a…` | `5f2607ed5be6480a…` |
| `freeze/terminal_FROZEN.sha256` | `7dd3ce82a80d019e…` | `7dd3ce82a80d019e…` |
| `freeze/terminal_FROZEN_013.sha256` | `5a8f10547f77184a…` | `5a8f10547f77184a…` |
| `freeze/real_apps_FROZEN.sha256` | `8083d8566c44c4aa…` | `8083d8566c44c4aa…` |
| `freeze/real_apps_followup_FROZEN.sha256` | `db6736e06a6714fe…` | `db6736e06a6714fe…` |
| `freeze/agentworld_FROZEN.sha256` | `f298134ddd51622b…` | `b131e6e491fae996…` |
| `freeze/agentworld_ADDENDUM_1.sha256` | `e70f6b6846bfb5a7…` | `e70f6b6846bfb5a7…` |
| `freeze/agentworld_ADDENDUM_2.sha256` | `2e089fc4158681c4…` | `2e089fc4158681c4…` |
| `freeze/agentworld_ADDENDUM_3.sha256` | `4a5598d5a840227f…` | `4a5598d5a840227f…` |
| `freeze/agentworld_ADDENDUM_4.sha256` | `503e05514c7228a4…` | `503e05514c7228a4…` |

Full hashes are in `MANIFEST.json`.
