"""One-time, idempotent setup of the shared people RA2's tasks need, in the same apps as RA (through their APIs / the mail
server's own CLI). Adds; never removes or changes RA's people. Secrets from RA's apps/.env, never printed.
    python3 tasks/setup_global_ra2.py"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RA = os.path.abspath(os.path.join(HERE, "..", "..", "RA"))
sys.path.insert(0, os.path.join(RA, "apps"))
import ra_lib  # noqa: E402

GITEA = [("sofia", "Sofia Lopes"), ("pat", "Pat Kim"), ("treyes", "Tom Reyes")]
MAIL = ["buyer@globex.test", "planner@events.test", "paulo@client.test", "rep@reseller.test", "agent@outsourced.test", "alice@globex.test",
        "bob@initech.test", "carol@umbrella.test", "ops@acme-retail.test", "it@northwind.test", "admin@contoso.test"]
ALIASES = {"sales-team@acme.test": "ana@acme.test,bruno@acme.test,rep@reseller.test",
           "support@acme.test": "carla@acme.test,agent@outsourced.test",
           "devs@acme.test": "ana@acme.test,bruno@acme.test,carla@acme.test"}
D = "ra-mailserver-1"
g = ra_lib.Gitea()
for u, n in GITEA:
    g.ensure_user(u, n)
print("gitea users ok:", [u for u, _ in GITEA])
have = set(re.findall(r"\*\s+(\S+@\S+)", subprocess.run(["docker", "exec", D, "setup", "email", "list"], capture_output=True, text=True).stdout))
for a in MAIL:
    if a not in have:
        subprocess.run(["docker", "exec", D, "setup", "email", "add", a, ra_lib.USER_PASS], capture_output=True, text=True, check=True)
print("mail accounts ok:", len(MAIL))
al = subprocess.run(["docker", "exec", D, "setup", "alias", "list"], capture_output=True, text=True).stdout
for a, tgt in ALIASES.items():
    if a not in al:
        subprocess.run(["docker", "exec", D, "setup", "alias", "add", a, tgt], capture_output=True, text=True, check=True)
print("aliases now:\n" + subprocess.run(["docker", "exec", D, "setup", "alias", "list"], capture_output=True, text=True).stdout)
