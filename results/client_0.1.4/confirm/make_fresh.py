"""WS-U confirmatory test: copies of the capability generators and runners with a seed switch (environment variables
whose defaults are the dev values), so the same code makes the dev items with the defaults and fresh items with new
seeds. Every patch is an exact replacement that must match once. No model call.
python3 make_fresh.py <dest>   (dest/<suite>/ gets the patched files; dest/client -> the client 0.1.0 the suites ran)"""
import os
import shutil
import sys

CAP = "/root/decis/capability"
FILES = {
    "rules_stress": ["make_items.py", "make_addendum.py", "rs_world.py", "run_rs.py", "names.txt"],
    "sql_wild": ["sql_wild.py", "run_sql.py"],
    "shell_wild": ["shell_wild.py"],
    "git_wild": ["git_wild.py"],
    "accumulation": ["accum.py", "run_accum.py", "names.txt"],
}
PATCHES = {
    ("rules_stress", "make_items.py"): [
        ("SEED = 20261005\n", 'SEED = int(os.environ.get("FRESH_SEED", 20261005))\n')],
    ("sql_wild", "sql_wild.py"): [
        ("N_PAIRS = 5\n", 'N_PAIRS = int(os.environ.get("N_PAIRS", 5))\nSEED_OFF = int(os.environ.get("SEED_OFF", 0))\n'
                          'SEED_TRIES = int(os.environ.get("SEED_TRIES", 200))\n'),
        ("made, seed = 0, 1000 * ti\n", "made, seed = 0, 1000 * ti + SEED_OFF\n"),
        ("while made < N_PAIRS and seed < 1000 * ti + 200:", "while made < N_PAIRS and seed < 1000 * ti + SEED_OFF + SEED_TRIES:")],
    ("sql_wild", "run_sql.py"): [
        ('todo = [i for i in items if i["id"] not in done]',
         'todo = [i for i in items if i["id"] not in done and not (os.environ.get("SKIP_BLIND") and i["variant"] == "blind")]')],
    ("shell_wild", "shell_wild.py"): [
        ("SEED = 2026105\n", 'SEED = int(os.environ.get("FRESH_SEED", 2026105))\n'),
        ("n_inst = 2 if n_var >= 3 else 3\n", 'n_inst = (2 if n_var >= 3 else 3) * int(os.environ.get("INST_MULT", 1))\n'),
        ("for i in range(n_inst):", 'for i in range(int(os.environ.get("I_OFF", 0)), int(os.environ.get("I_OFF", 0)) + n_inst):'),
        ("with cf.ThreadPoolExecutor(24) as ex,", 'with cf.ThreadPoolExecutor(int(os.environ.get("INFLIGHT", 24))) as ex,')],
    ("git_wild", "git_wild.py"): [
        ('API = os.environ.get("EKBASIS_URL", "http://127.0.0.1:8542")\n',
         'API = os.environ.get("EKBASIS_URL", "http://127.0.0.1:8542")\nSALT = os.environ.get("GW_SALT", "git_wild")\n'
         'REP_OFF = int(os.environ.get("REP_OFF", 0))\nREP_MULT = int(os.environ.get("REP_MULT", 1))\n'),
        ('for rep in range(reps or t["reps"]):', 'for rep in range(REP_OFF, REP_OFF + (reps or t["reps"]) * REP_MULT):'),
        ('prng = random.Random(f"git_wild:{name}:{rep}")', 'prng = random.Random(f"{SALT}:{name}:{rep}")'),
        ('b = Builder(picks, random.Random(f"git_wild:{name}:{rep}:{v}"))',
         'b = Builder(picks, random.Random(f"{SALT}:{name}:{rep}:{v}"))')],
    ("accumulation", "accum.py"): [
        ("SEED = 20261005\n", 'SEED = int(os.environ.get("FRESH_SEED", 20261005))\n'),
        ("PER_CELL = 3\n", 'PER_CELL = int(os.environ.get("PER_CELL", 3))\n')],
}


def main():
    dest = sys.argv[1]
    os.makedirs(dest, exist_ok=True)
    if not os.path.exists(os.path.join(dest, "client")):
        os.symlink(os.path.join(CAP, "client"), os.path.join(dest, "client"))
    for suite, files in FILES.items():
        os.makedirs(os.path.join(dest, suite), exist_ok=True)
        for fn in files:
            src = open(os.path.join(CAP, suite, fn), encoding="utf-8").read()
            for old, new in PATCHES.get((suite, fn), []):
                assert src.count(old) == 1, (suite, fn, old, src.count(old))
                src = src.replace(old, new)
            if PATCHES.get((suite, fn)):
                assert "import os" in src, (suite, fn)
            open(os.path.join(dest, suite, fn), "w", encoding="utf-8").write(src)
    shutil.copytree(os.path.join(CAP, "git_wild", "home"), os.path.join(dest, "git_wild", "home"), dirs_exist_ok=True)
    print("patched copies in", dest)


if __name__ == "__main__":
    main()
