import sys
lat, out = sys.argv[1], sys.argv[2]
src = open("/root/diag1.py").read().replace("for L in [16, 32, 48, 63]:", "for L in [32, 48]:").replace(
    'json.dump(out, open("diag1_out.json", "w"), indent=1)', f'json.dump(out, open("{out}", "w"), indent=1)')
sys.argv = ["diag1", lat, "/root/data.jsonl"]
print("== M4", lat, flush=True)
exec(compile(src, "diag1", "exec"))
