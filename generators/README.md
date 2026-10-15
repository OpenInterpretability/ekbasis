# Generators (as run)

The code that computed the answers in the training rows and evaluation sets of the
[Ekbasis-Skopos-27B](https://huggingface.co/caiovicentino1/Ekbasis-Skopos-27B) lineage: simulators of written-rule
worlds, and programs that set up a state, execute shell commands, git, SQLite, PostgreSQL or Python on it, and record
what happened. The data cards say every answer was computed, not written; these files are how. They are snapshots of
the files that ran, not a library: no file was cleaned up or refactored, and the paths inside are those of the machines
they ran on (`/root/decis/...`, `/dev/shm/...`, `/root/v50p/...`). The only changes are the ones listed under
[Provenance](#provenance). The rows themselves are in
[ekbasis-skopos-data](https://huggingface.co/datasets/caiovicentino1/ekbasis-skopos-data).

## Security

These programs execute the commands they generate, on purpose: the answer to each question is what the command did.
Shell commands delete, move and overwrite files; git rewrites repositories; SQL drops tables. The executors run them in
throwaway directories, as the unprivileged user `nobody` where the script says so (some must start as root to drop to
it), with time and resource limits, and the shell family refuses commands that leave the working directory. That is a
precaution, not a sandbox. **Run them only in a disposable container or virtual machine** with no credentials, no
access to a network you care about, and nothing mounted that you would mind losing.

```
docker run --rm -it --network none -v "$PWD/generators:/gen:ro" -v "$PWD/out:/out" python:3.12 bash
apt-get update && apt-get install -y git      # and postgresql-16 for fx_pg.py; download_ext.py needs the network
pip install numpy pyarrow scipy pillow huggingface_hub
export PYTHONPATH=/gen/conseq:/gen/factory     # or /gen/fx for FX's copies of the factory modules
cd /gen/factory && python3 run_family.py gitfam 100000 20 /out/git.jsonl 4
```

Each script's docstring gives its command line. Seeds are written in the scripts (or in the command lines recorded
below), so a run reproduces the same items given the same tool versions: execution truth depends on the installed git,
coreutils, SQLite and PostgreSQL.

## What produced what

**Training kinds** (the trainer's pools; `training/skopos/README.md` gives each stage's rows):

| Kind | Where it came from | Files |
|---|---|---|
| floor, floor3, read | worlds with written rules and an exact simulator (factory 1; factory 3, whose rules are themselves sampled) | `conseq/envs.py`, `conseq/worldgen.py`, `conseq/worldgen3.py`; driven by `conseq/gen_factory.py`, `conseq/gen_factory3.py`, `conseq/gen_m3only.py` |
| multi | several questions on one state | `conseq/gen_multi.py` |
| floorG, floorG2, floorG3 | git v1–v3, every command executed in a throwaway repository | `conseq/gitbox.py`, `gitbox2.py`, `gitbox3.py`; `conseq/gen_git.py`, `gen_git2.py`, `gen_git3.py` |
| floorC | items mined inside V42's own chains (Ekbasis-27B's r4a; v49f read them again); the answers are the simulator's | `conseq/long_chain3.py` (the chains), `conseq/run_ideas_mine_r4.sh` (the selection, inline) |
| floorGV | V44's git items: ignored files overwritten, sparse checkout, `--abort` after a resolution | `conseq/v44/gen_v44_git.py`; prepared by `prep_v45_v49/prepare_data.py` |
| floorRXsh, floorRXgit, floorRXsql | F's executed factory: shell, git and SQLite scenarios, each with a flip twin | `factory/` (`run_family.py`, `shell.py`, `gitfam.py`, `sqlfam.py`, `common.py`, `pack.py`, `quality.py`); the shell rows re-rendered in the shell guard's layout by `prep_v45_v49/rerender_shell.py`; `prep_v45_v49/prepare_data.py` |
| floorGA | guard-style git items ("will work be lost?", "will it fail?"), fresh seeds | `prep_v45_v49/gen_anchor.py` (seeds 4,610,000+) and `prep_v45_v49/gen_softanchor.py` (4,810,000+), both through `conseq/gen_git3.py`; `prep_v45_v49/prepare_v46.py`, `prep_v45_v49/make_v49_data.py` |
| floorFX | the FX factory: 39 families of shell, git, SQLite, PostgreSQL, Python and side effects; 2,000 rows converted from swe-rebench-v2-CodeWorldModeling and 600 from ShIO-bash-26.1 | `fx/` (below); sampled by `prep_v45_v49/make_v49_data.py` |
| floorPL | synthetic worlds, 4–16 actions | `v50/build_data.py` |
| floorPLG | real git sequences of 4–16 commands, executed | `v50/gen_git_train.py` (seeds 9,000+) |
| floorRX | the factory regenerated with fresh seeds (100,000+) and executed | `v50/gen_factory.sh` (`factory/`) |
| replay | not generated here: Eikos training items, as published in ekbasis-data | |

**FX's families** (`fx/`): core shell, git, SQLite and Python families with F's generators and new seeds (`shell.py`,
`gitfam.py`, `sqlfam.py`, `pyfam.py`, listed in `fx_registry.py`); new families `fx_shell_new.py` (sh_status_pipes,
sh_glob_brace, sh_find_select, sh_write_modes, sh_archive2), `fx_git_new.py` (git_worktree, git_reflog_gc),
`fx_sql_new.py` (sql_collation_affinity, sql_views_check_generated), `fx_pg.py` (pg_conflict_sequences,
pg_types_strict; a private PostgreSQL 16 cluster on a Unix socket), `fx_py_new.py` (py_files_io, py_iter_lazy),
`fx_side.py` (se_shell, se_sql, se_git: side effects beyond what a request asked); the external conversions
`fx_ext_cwm.py` and `fx_ext_shio.py`, fed by `download_ext.py`. `fx_run.py` runs a family (`run_core.sh`,
`run_jobs.sh`, `run_plus.sh`, `run_se.sh`, `plan_jobs.py` are the runs), `fx_pack.py` packs, `fx_firewall.py` drops
every row that repeats or nearly repeats an evaluation item. Every family held out for evaluation is in the same files
(`fx_registry.HELD_OUT_FAMILIES`).

**Evaluation sets** read in [RELEASE_EVAL_SKOPOS.md](../RELEASE_EVAL_SKOPOS.md):

| Set | Files |
|---|---|
| git v3 known / held-out command types | `conseq/gen_git3.py`, `conseq/gitbox3.py` |
| the larger guard set (known, held) | `conseq/gen_guard_big.py` |
| never-trained and trained world families (`multi_test_*`), `ftest_family`, `m3val` | `conseq/gen_multi.py`, `conseq/gen_factory.py`, `conseq/gen_m3only.py` |
| `ftest_fresh` (5,385 fresh never-trained-family items) | `v50/gen_ftest_fresh.py` |
| `fac_val` (factory scenarios, seeds 200,000+) | `v50/run_r2.sh` (its first lines: `run_family.py` per family, then an inline firewall and pack.py's option shuffle) |
| `git_long` (real git sequences of 5, 8, 12 commands) and its validation twin `git_long_val` | `v50/gen_git_long.py`, `v50/gen_git_val.py` |
| `fhorizon` (1–20 actions) | `v50/build_data.py` (the recipe of `conseq/gen_horizon.py`) |
| `sess_val` (factory scenarios as an agent's terminal session) | `v50/gen_session.py`: `python3 gen_session.py data/fac_val.jsonl data/sess_val.jsonl floorSX` |
| `latent_test` | `v50/latent_gen_data.py` (the trajectories; their conversion to the trainer's format was not saved) |
| the neutral suite (AgentWorldBench turns) | `v50/build_awb_neutral.py` (needs a download of Qwen/AgentWorldBench; only ids and our labels are published) |
| the image check (400 fresh items) | `v50/image_served.py` (draws the states and scores a served model) |
| the calibration items | `v50/build_calib_items.py` |
| T3c, the 16 real-repository scenarios | `../results_skopos/scripts/git_battery3.py` |
| the 15,008 confident-errors items | Ekbasis-27B's set, published in ekbasis-data |

**Data preparation and audits** (`prep_v45_v49/`): `audit_overlap.py` (the rules: identical prompt, word 8-gram near
duplicate with Jaccard ≥ 0.5, equal sequence of 2+ actions) and `audit_v48.py` (those rules on new training files
against every evaluation file; v49f's FX rows and v49_anchor2 went through it).

## Not included

- `fx_apps.py` (the self-hosted apps Vikunja and Memos) and its app containers: every Vikunja family was dropped by the
  firewall before v49f, and Memos was an evaluation readout outside this release. `fx_side.py` imports it only for
  se_vikunja.
- `fx_ext_webworld.py`: WebWorld was excluded from training (our data rule).
- F's GUI family (`gui.mjs`), quarantined and never trained; factory 2 (`worldgen2.py`), not in any lineage file.
- The files that only assembled Ekbasis-27B's earlier stage files from these rows (mixing and balancing, 2–3 October);
  their rows are in ekbasis-data with each row's generator in `source`.
- Two steps that were not saved as scripts: the conversion of `latent_test` to the trainer's format, and the overlap
  audit behind `results_skopos/overlap_audit_r4.json` (the redone audit of the whole lineage replaces it).

## Provenance

`provenance.json` holds, for every file, the sha256 of the copy that ran, the sha256 here, and where the copy comes
from. "Mirror" files ran on the 4-GPU training machine (early October 2026), which no longer exists; these are the
copies that machine was run from, kept on our workstation, and cannot be compared with it any more. Files that also ran
on the one-GPU research machine (mid-October) are compared with that machine's backed-up copies.

<!-- provenance:start -->
| File | sha256 of the copy that ran | sha256 here | Changed for publication | Research machine's copy |
|---|---|---|---|---|
| `conseq/envs.py` | `7a3b8b1cdbef5bf4…` | the same | nothing | identical |
| `conseq/gen_factory.py` | `211feeaff102410b…` | the same | nothing | — |
| `conseq/gen_factory3.py` | `a6198f9f36dc374d…` | the same | nothing | — |
| `conseq/gen_git.py` | `3c4af6125a69cd81…` | the same | nothing | — |
| `conseq/gen_git2.py` | `e917a2c409930ed3…` | the same | nothing | — |
| `conseq/gen_git3.py` | `b140610c34f5fb93…` | the same | nothing | — |
| `conseq/gen_guard_big.py` | `9078cd7e4a2a92e2…` | the same | nothing | — |
| `conseq/gen_horizon.py` | `dc95dfcc4e452553…` | the same | nothing | — |
| `conseq/gen_m3only.py` | `2c48be70798d9883…` | the same | nothing | — |
| `conseq/gen_multi.py` | `58da9cd331efc0e5…` | the same | nothing | — |
| `conseq/gitbox.py` | `7f3fb81517988740…` | the same | nothing | identical |
| `conseq/gitbox2.py` | `38cf9cda620acd02…` | the same | nothing | identical |
| `conseq/gitbox3.py` | `a9532bb091f70773…` | the same | nothing | identical |
| `conseq/long_chain3.py` | `364455a1a429698a…` | the same | nothing | — |
| `conseq/run_ideas_mine_r4.sh` | `dac6b0abe115634e…` | the same | nothing | — |
| `conseq/v44/gen_v44_git.py` | `2c0212e359bbad9f…` | the same | nothing | — |
| `conseq/worldgen.py` | `3edbba376d2d868d…` | the same | nothing | identical |
| `conseq/worldgen3.py` | `d43ccdb0bf06e25a…` | the same | nothing | — |
| `factory/common.py` | `b12a5f7d525d620a…` | the same | nothing | identical |
| `factory/gitfam.py` | `fdf6de2c7cffbd58…` | the same | nothing | identical |
| `factory/overlap.py` | `3e83f4eeb7299983…` | the same | nothing | identical |
| `factory/overlap_c012.py` | `f412c9408767bcd6…` | the same | nothing | identical |
| `factory/pack.py` | `33a15964ed64c998…` | the same | nothing | identical |
| `factory/pyfam.py` | `4575299601586248…` | the same | nothing | identical |
| `factory/quality.py` | `475d26737668a63b…` | the same | nothing | identical |
| `factory/run_family.py` | `b0d6e162bd62fe3f…` | the same | nothing | identical |
| `factory/shell.py` | `b540fa84b3ae100a…` | the same | nothing | identical |
| `factory/sqlfam.py` | `42af09f4672ab696…` | the same | nothing | identical |
| `fx/common.py` | `e01e67f6f8ecf636…` | the same | nothing | — |
| `fx/download_ext.py` | `d7c9ef656baafe13…` | the same | nothing | — |
| `fx/fx_ext_cwm.py` | `89f6b4f91c00acbd…` | the same | nothing | — |
| `fx/fx_ext_shio.py` | `2aeec8fc4f5878b5…` | the same | nothing | — |
| `fx/fx_firewall.py` | `95773ba29053970f…` | the same | nothing | — |
| `fx/fx_git_new.py` | `e4b2b26c77b1d700…` | the same | nothing | — |
| `fx/fx_internal_leak.py` | `683abaae27eb1193…` | the same | nothing | — |
| `fx/fx_new_registry.py` | `5af42160e4c5ad6c…` | the same | nothing | — |
| `fx/fx_pack.py` | `ee709c72d03e8239…` | the same | nothing | — |
| `fx/fx_pg.py` | `e0b7bb17d56458e3…` | the same | nothing | — |
| `fx/fx_py_new.py` | `693f9e873301856b…` | the same | nothing | — |
| `fx/fx_registry.py` | `101932c7baf9c502…` | the same | nothing | — |
| `fx/fx_report.py` | `361c52aefa972071…` | the same | nothing | — |
| `fx/fx_run.py` | `369e8f3ca5177702…` | the same | nothing | — |
| `fx/fx_shell_new.py` | `8ddb6ad8dde6fc03…` | the same | nothing | — |
| `fx/fx_side.py` | `b126cbcbafb7e847…` | the same | nothing | — |
| `fx/fx_sql_new.py` | `2dd11494851ce0e3…` | the same | nothing | — |
| `fx/gitfam.py` | `95a2f111ed60fbc5…` | the same | nothing | — |
| `fx/overlap.py` | `3e83f4eeb7299983…` | the same | nothing | — |
| `fx/pack.py` | `33a15964ed64c998…` | the same | nothing | — |
| `fx/plan_jobs.py` | `a184e125a648de7b…` | the same | nothing | — |
| `fx/pyfam.py` | `1bf2f2c900f788c1…` | the same | nothing | — |
| `fx/quality.py` | `475d26737668a63b…` | the same | nothing | — |
| `fx/run_core.sh` | `3e5960cae2be10c5…` | the same | nothing | — |
| `fx/run_family.py` | `b0d6e162bd62fe3f…` | the same | nothing | — |
| `fx/run_jobs.sh` | `707408f60db29dc7…` | the same | nothing | — |
| `fx/run_plus.sh` | `025a8266e32e6656…` | the same | nothing | — |
| `fx/run_se.sh` | `65561718a6483e1c…` | the same | nothing | — |
| `fx/shell.py` | `e3c168bdcbd5c930…` | the same | nothing | — |
| `fx/sqlfam.py` | `7006e4dd89a61b21…` | the same | nothing | — |
| `prep_v45_v49/audit_overlap.py` | `f027d16049a01712…` | the same | nothing | — |
| `prep_v45_v49/audit_v48.py` | `17227cb83aa0fd24…` | the same | nothing | — |
| `prep_v45_v49/gen_anchor.py` | `dc7e332dc946a665…` | the same | nothing | — |
| `prep_v45_v49/gen_softanchor.py` | `c2a590102af61b94…` | the same | nothing | — |
| `prep_v45_v49/make_v49_data.py` | `69f28cf9c5a15697…` | the same | nothing | — |
| `prep_v45_v49/prepare_data.py` | `5a01f39e41887f1f…` | the same | nothing | — |
| `prep_v45_v49/prepare_v46.py` | `0cc95ed3adfdec21…` | the same | nothing | — |
| `prep_v45_v49/rerender_shell.py` | `b1519518013d041b…` | the same | nothing | — |
| `v50/build_awb_neutral.py` | `9fcdf592d9a56045…` | the same | nothing | — |
| `v50/build_calib_items.py` | `14f1c9bddbef34e1…` | the same | nothing | identical |
| `v50/build_data.py` | `09153023002b61e0…` | the same | nothing | — |
| `v50/gen_factory.sh` | `c0fe02d9f0d2ed18…` | the same | nothing | identical |
| `v50/gen_ftest_fresh.py` | `cdec8cf19636720a…` | the same | nothing | identical |
| `v50/gen_git_long.py` | `b084582640ac0a87…` | the same | nothing | — |
| `v50/gen_git_train.py` | `4f4135fb13e93c8c…` | the same | nothing | identical |
| `v50/gen_git_val.py` | `6d42b38cfeda06e6…` | the same | nothing | identical |
| `v50/gen_session.py` | `29512207b2a425d2…` | the same | nothing | identical |
| `v50/image_served.py` | `87b26338a1fad9e8…` | the same | nothing | identical |
| `v50/latent_gen_data.py` | `a167cf7d12b2b30e…` | the same | nothing | — |
| `v50/run_r2.sh` | `516793f0d244dc4f…` | the same | nothing | identical |
<!-- provenance:end -->
