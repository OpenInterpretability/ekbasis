"""Internal leak check: FX's evaluation splits against FX's own train/val (same normalized floor; same action lines;
ShIO commands shared between ext_shio_cmds and ext_shio_eval)."""
import gzip, hashlib, json, re, collections
D = "/root/decis/mission/FX/data"
def norm(t): return re.sub(r"\s+", " ", t).strip().lower()
def h(t): return hashlib.md5(norm(t).encode()).hexdigest()
def acts(r):
    st = r.get("struct") or {}
    for k in ("cmds", "stmts", "actions"):
        v = st.get(k)
        if isinstance(v, list) and v:
            return json.dumps(v)
    if isinstance(st.get("action"), str):
        return st["action"]
    return None
tr_fl, tr_act = set(), set()
shio_tr = set()
for sp in ("train", "val"):
    for line in gzip.open(f"{D}/fx_{sp}.jsonl.gz", "rt"):
        r = json.loads(line)
        tr_fl.add(h(r["floor"]))
        a = acts(r)
        if a: tr_act.add((r["world"], a))
        if r["fx_family"] == "ext_shio_cmds" and a: shio_tr.add(a)
out = {}
for sp in ("eval_family", "eval_app"):
    c = collections.Counter(); n = collections.Counter(); ca = collections.Counter(); ex = {}
    for line in gzip.open(f"{D}/fx_{sp}.jsonl.gz", "rt"):
        r = json.loads(line)
        f = r["fx_family"]; n[f] += 1
        if h(r["floor"]) in tr_fl: c[f] += 1
        a = acts(r)
        if a and (r["world"], a) in tr_act:
            ca[f] += 1; ex.setdefault(f, a[:120])
    out[sp] = {"rows": dict(n), "same_floor_in_train": dict(c), "same_action_in_train": dict(ca), "examples": ex}
print(json.dumps(out, indent=1))
