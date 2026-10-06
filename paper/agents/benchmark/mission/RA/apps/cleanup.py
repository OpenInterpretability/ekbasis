"""Remove per-run objects (and the early smoke-test accounts) from the real apps, so runs never see each other's
organizations, users or groups. Used after every judged run (run_study_ra.py) and once by hand for leftovers.
    python3 apps/cleanup.py leftovers        # everything made by smoke tests, verification and the pilot
    python3 apps/cleanup.py run <run_ctx.json>"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ra_lib  # noqa: E402

KEEP_GITEA = {"raadmin", "bob", "carla", "diego", "lee", "priya", "marco", "ana", "nina", "tomas", "wei"}


def gitea_drop_org(org):
    G = ra_lib.Gitea()
    try:
        for r in G.get(f"/orgs/{org}/repos?limit=100", sudo=""):
            G.req("DELETE", f"/repos/{org}/{r['name']}", sudo="", ok=(204, 404))
        G.req("DELETE", f"/orgs/{org}", sudo="", ok=(204, 404))
    except RuntimeError as e:
        print("gitea org", org, str(e)[:120])


def gitea_drop_user(u):
    G = ra_lib.Gitea()
    try:
        for r in G.get(f"/users/{u}/repos?limit=100", sudo=""):
            G.req("DELETE", f"/repos/{u}/{r['name']}", sudo="", ok=(204, 404))
        G.req("DELETE", f"/admin/users/{u}?purge=true", sudo="", ok=(204, 404))
    except RuntimeError as e:
        print("gitea user", u, str(e)[:120])


def nc_drop_user(uid):
    try:
        ra_lib.Nextcloud().ocs("DELETE", f"/cloud/users/{uid}", ok=(200, 404))
    except RuntimeError as e:
        print("nc user", uid, str(e)[:120])


def mail_drop(addr):
    subprocess.run(["docker", "exec", "ra-mailserver-1", "setup", "email", "del", "-y", addr], capture_output=True, text=True)


def run(ctx):
    rid, app = ctx["run_id"], ctx["app"]
    if app == "gitea":
        gitea_drop_org(f"acme-{rid}")
        gitea_drop_user(f"dana-{rid}")
    elif app == "nextcloud":
        nc_drop_user(f"dana-{rid}")
        if ctx.get("owner"):
            nc_drop_user(ctx["owner"])
    elif app == "mail":
        mail_drop(f"dana-{rid}@acme.test")
    for f in (ctx.get("storage_state"),):
        if f and os.path.exists(f):
            os.remove(f)


def leftovers():
    G = ra_lib.Gitea()
    orgs = G.get("/admin/orgs?limit=200", sudo="")
    for o in orgs:
        gitea_drop_org(o["username"])
    for u in G.get("/admin/users?limit=500", sudo=""):
        if u["login"] not in KEEP_GITEA:
            gitea_drop_user(u["login"])
    nc = ra_lib.Nextcloud()
    users = nc.ocs("GET", "/cloud/users", params={"limit": 1000})["users"]
    for u in users:
        if re.match(r"^(dana-|o[vp]|odbg|vmarta|vjoao|vana)", u):
            nc_drop_user(u)
    try:
        nc.ocs("DELETE", "/cloud/groups/vstaff", ok=(200, 404))
    except RuntimeError:
        pass
    out = subprocess.run(["docker", "exec", "ra-mailserver-1", "setup", "email", "list"], capture_output=True, text=True).stdout
    for a in re.findall(r"\*\s+(\S+@\S+)", out):
        if a.startswith("dana-") or a in ("vdana@acme.test", "vana@acme.test", "vext@vendor.test"):
            mail_drop(a)
    subprocess.run(["docker", "exec", "ra-mailserver-1", "setup", "alias", "del", "vteam@acme.test", "vana@acme.test,vext@vendor.test"], capture_output=True, text=True)
    print("left: gitea orgs", len(G.get("/admin/orgs?limit=200", sudo="")), "gitea users", len(G.get("/admin/users?limit=500", sudo="")),
          "nc users", len(nc.ocs("GET", "/cloud/users", params={"limit": 1000})["users"]))


if __name__ == "__main__":
    if sys.argv[1] == "leftovers":
        leftovers()
    else:
        run(json.load(open(sys.argv[2])))
