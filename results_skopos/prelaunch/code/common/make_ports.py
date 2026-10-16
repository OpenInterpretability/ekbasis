"""Builds every ported script of the pre-launch battery from the as-run original in _orig/, by the exact replacements
listed here (each must match exactly once, or nothing is written), and writes <Pn>/CHANGES.diff (diff -u against the
original). The changes are paths/URLs and saving per-item outputs, plus the few listed where the original read a file
that only existed on the old rig. Re-run after editing this list: python3 common/make_ports.py"""
import difflib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = 'os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))'

PORTS = {
    # P1: the 240 git questions (and ftest_family, which the same script answers first)
    "P1/release_eval_extra.py": ("release_eval_extra.py", [
        ('sys.path.insert(0, "/root/decis/conseq")\n',
         f'LIB = {LIB}  # PORT: the rig folder /root/decis/conseq -> lib/ (identical copies)\n'
         'DATA = os.environ.get("DATA", "/root/prelaunch_data")  # PORT: the rig folder /dev/shm/conseq -> $DATA\n'
         'sys.path.insert(0, LIB)  # PORT\n'),
        ('import git_llm_large as G\n',
         'import git_llm_large as G\nG.D = Path(DATA)  # PORT: pick() reads $DATA/fac/<split>.jsonl (it read /dev/shm/conseq/fac)\n'),
        ('src = open("/root/decis/conseq/release_eval.py").read()', 'src = open(os.path.join(LIB, "release_eval.py")).read()  # PORT'),
        ('open("/dev/shm/conseq/fac/ftest_family.jsonl")', 'open(f"{DATA}/fac/ftest_family.jsonl")'),
        ('open("/dev/shm/conseq/fac/gold0_ftest_family.jsonl")', 'open(f"{DATA}/fac/gold0_ftest_family.jsonl")'),
    ]),
    # P3: long chains (run as long_chain2.py on the rig; = conseq/long_chain.py on the Mac)
    "P3/long_chain2.py": ("long_chain2.py", [
        ('sys.path.insert(0, "/root/decis/conseq")', f'sys.path.insert(0, {LIB})  # PORT'),
        ('return {"fam": fam, "len": length, "mode": mode,',
         'return {"fam": fam, "len": length, "i": i, "mode": mode,'),  # the chain's seed index, to pair chains
        ('json.dump(res, open("/dev/shm/conseq/long_chain.json", "w"))',
         'json.dump(res, open(os.environ["OUT_JSON"], "w"))  # PORT: it wrote /dev/shm/conseq/long_chain.json'),
    ]),
    # P4: predict, observe, correct
    "P4/long_chain3.py": ("long_chain3.py", [
        ('sys.path.insert(0, "/root/decis/conseq")', f'sys.path.insert(0, {LIB})  # PORT'),
    ]),
    # P5: speed (and P8's timing, which is short_eval_release.py time)
    "P5/speed_bench.py": ("speed_bench.py", [
        ('sys.path.insert(0, "/root/decis/conseq")', f'sys.path.insert(0, {LIB})  # PORT'),
        ('sys.path.insert(0, "/root/decis/serve_v13/eikos")',
         'sys.path.insert(0, os.environ["MODEL_DIR"])  # PORT: decision_core.py of the served model folder (it was serve 1.3\'s)'),
    ]),
    # P6: Portuguese
    "P6/pt_eval_api.py": ("pt_eval_api.py", [
        ('import importlib.util\n',
         f'import importlib.util\nLIB = {LIB}  # PORT\nsys.path.insert(0, LIB)  # PORT: envs/worldgen for pt_eval.py\'s items\n'),
        ('spec_from_file_location("pt", "/root/decis/conseq/pt_eval.py")', 'spec_from_file_location("pt", os.path.join(LIB, "pt_eval.py"))'),
        ('src = open("/root/decis/conseq/pt_eval.py").read()', 'src = open(os.path.join(LIB, "pt_eval.py")).read()'),
        ('print("world      n chg | English  Portuguese   (questions the actions change)")\n',
         'with open(os.environ["OUT_JSONL"], "w") as f:  # PORT: per-item outputs (the release run kept none)\n'
         '    for k, it in enumerate(items):\n'
         '        f.write(json.dumps({"k": k, "fam": it["fam"], "changed": it["changed"], "en_ok": en[k], "pt_ok": pt[k]}) + "\\n")\n'
         'print("world      n chg | English  Portuguese   (questions the actions change)")\n'),
    ]),
    # P7: chains that start from an image
    "P7/image_chain.py": ("image_chain.py", [
        ('sys.path.insert(0, "/root/decis/conseq")', f'sys.path.insert(0, {LIB})  # PORT'),
        ('json.dump(res, open("/dev/shm/conseq/image_chain.json", "w"))',
         'json.dump(res, open(os.environ["OUT_JSON"], "w"))  # PORT: it wrote /dev/shm/conseq/image_chain.json (item i = position i)'),
    ]),
    # P8: short checks, two wordings
    "P8/short_eval_release.py": ("short_eval_release.py", [
        ('sys.path.insert(0, "/root/decis/conseq")', f'sys.path.insert(0, {LIB})  # PORT'),
        ('saved = json.load(open("/dev/shm/conseq/short_eval.json"))',
         'saved = json.load(open(os.environ["SAVED_JSON"]))  # PORT: the rig-only /dev/shm/conseq/short_eval.json, rebuilt by make_saved.py'),
        ('("Qwen3.8-27B at once", nothink), ',
         ''),
        ('("Qwen3.8-27B thinking", think))}',
         '("Qwen3.8-27B thinking", think))}  # PORT: no at-once row (its per-item answers were rig-only)'),
    ]),
    # P9: planning by search, no LLM (PyTorch)
    "P9/search_eval.py": ("search_eval.py", [
        ('sys.path.insert(0, "/root/decis/serve_v13/eikos")',
         'sys.path.insert(0, os.environ["MODEL"])  # PORT: decision_core.py of the model folder (it was serve 1.3\'s)'),
        ('sys.path.insert(0, "/root/decis/conseq")', f'sys.path.insert(0, {LIB})  # PORT'),
        ('set_peft_model_state_dict(model, load_file(f"{E(\'ADAPTER\')}/adapter_model.safetensors"))',
         'if E("ADAPTER"):  # PORT: with ONLY=base the adapter is switched off (disable_adapter) and never used; the rig loaded\n'
         '    set_peft_model_state_dict(model, load_file(f"{E(\'ADAPTER\')}/adapter_model.safetensors"))  # V42\'s, rig-only'),
    ]),
    # P10: real use on real repositories (Mac)
    "P10/realuse_guard.py": ("realuse/realuse_guard.py", [
        ('T = "<mac-scratch>/realuse2"',
         'T = os.environ["WORK"]  # PORT: scratch copies and per-run files (it was the realuse2 folder)\n'
         'BASE = os.environ.get("BASE", "<mac-scratch>/realuse2")  # PORT: the 4 Oct base copies\n'
         'OUTD = os.environ["OUT"]  # PORT: truth / predictions\n'
         'VENV = os.environ.get("CLIENT_VENV", "<mac-scratch>/venv_launch")  # PORT: the client that ran'),
        ('    dst = f"{T}/base_{name}"\n    if not os.path.isdir(dst):\n',
         '    dst = f"{BASE}/base_{name}"\n    if not os.path.isdir(dst):  # PORT: never rebuild from the live repositories (another state)\n'
         '        raise SystemExit(f"missing base copy {dst}: the 4 Oct repository state is gone, P10 cannot run as published")\n'
         '    if False:\n'),
        ('[f"{T}/../venv_launch/bin/python", "-c", code]', '[f"{VENV}/bin/python", "-c", code]'),
        ('[f"{T}/../venv_launch/bin/ekbasis-claude-hook"]', '[f"{VENV}/bin/ekbasis-claude-hook"]'),
        ('json.dump(res, open(f"{T}/truth.json", "w"), indent=1)', 'json.dump(res, open(f"{OUTD}/truth.json", "w"), indent=1)'),
        ('json.dump(res, open(f"{T}/pred_{name}.json", "w"), indent=1)', 'json.dump(res, open(f"{OUTD}/pred_{name}.json", "w"), indent=1)'),
    ]),
    # P11: GPU sizes (mem_ceiling_test.sh of the rig)
    "P11/mem_ceiling_test.sh": ("mem_ceiling_test.sh", [
        ('Q=/dev/shm/conseq/quant; L=$Q/memtest_$N.log; G=GPU-be21ff88-2a1c-9085-b58e-7d0d5981637a',
         'Q=$OUTROOT/P11; L=$Q/memtest_$N.log; G=$GPU  # PORT: output folder and GPU of this machine'),
        ('cd /root/decis/release_final/models/Eikos-27B\n', 'cd $M  # PORT: the build\'s own folder (its serve_vllm.sh is byte-identical to Ekbasis-27B\'s)\n'),
        ('exec env PATH=/root/vllm_new_env/bin:$PATH MAX_NUM_SEQS=$S CUDA_VISIBLE_DEVICES=$G VLLM_CACHE_ROOT=$Q/vllm_cache bash /root/decis/release_final/models/Eikos-27B/serve_vllm.sh $M 30150 $F',
         'exec env MAX_NUM_SEQS=$S CUDA_VISIBLE_DEVICES=$G VLLM_CACHE_ROOT=$Q/vllm_cache bash $M/serve_vllm.sh $M 30150 $F'),
        ('  cd /root/decis/ekbasis_dev/eikos\n', '  cd $M  # PORT: the build\'s own serve.py (the rig used serve 1.3 from its dev folder)\n'),
        ('exec env CUDA_VISIBLE_DEVICES= /opt/sglang/bin/python serve.py', 'exec env CUDA_VISIBLE_DEVICES= $PY serve.py'),
        ('  /opt/sglang/bin/python - "$REF" <<"PY"', '  $PY - "$REF" "$Q/answers_$N.jsonl" <<"PY"'),
        ('rows = [json.loads(l) for l in open("/dev/shm/conseq/fac/git3_test_held.jsonl")][:60]',
         'import os\nrows = [json.loads(l) for l in open(os.environ["DATA"] + "/fac/git3_test_held.jsonl")][:60]  # PORT\nout = open(sys.argv[2], "w")  # PORT: per-item answers'),
        ('for r, x in zip(rows, ref):\n', 'for k, (r, x) in enumerate(zip(rows, ref)):  # PORT: k for the per-item file\n'),
        ('    same += pred == x["pred"]\n',
         '    same += pred == x["pred"]\n    out.write(json.dumps({"k": k, "pred": pred, "full_memory": x["pred"]}) + "\\n")  # PORT\n'),
    ]),
}


def build(target, src, reps):
    text = (ROOT / "_orig" / src).read_text()
    new = text
    for old, rep in reps:
        n = new.count(old)
        if n != 1:
            sys.exit(f"{target}: {n} matches for {old[:70]!r}")
        new = new.replace(old, rep)
    head = (f"PRELAUNCH PORT ({target.split('/')[0]}) of _orig/{src}: every changed line is marked PORT; "
            f"the full diff is CHANGES.diff in this folder.")
    if src.endswith(".py"):
        new = f"# {head}\n" + new
    else:
        first, rest = new.split("\n", 1)
        new = f"{first}\n# {head}\n{rest}"
    out = ROOT / target
    out.write_text(new)
    if src.endswith(".sh"):
        out.chmod(0o755)
    diff = difflib.unified_diff(text.splitlines(True), new.splitlines(True), f"_orig/{src}", target)
    (out.parent / "CHANGES.diff").open("a" if (out.parent / ".diffs_started").exists() else "w").writelines(diff)
    (out.parent / ".diffs_started").touch()
    print("ported", target)


if __name__ == "__main__":
    for p in {t.split("/")[0] for t in PORTS}:
        (ROOT / p / ".diffs_started").unlink(missing_ok=True)
    for t, (s, r) in PORTS.items():
        build(t, s, r)
    for p in {t.split("/")[0] for t in PORTS}:
        (ROOT / p / ".diffs_started").unlink(missing_ok=True)
