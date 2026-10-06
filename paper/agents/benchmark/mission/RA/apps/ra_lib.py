"""WS-RA helpers: admin clients for the real apps (Gitea REST, Nextcloud OCS/WebDAV/occ) with the secrets read from
apps/.env (never printed). Used by the seeders, the judges and the spec server; nothing here is shown to the agent."""
import json
import os
import subprocess
import urllib.parse
import warnings

warnings.filterwarnings("ignore")
import requests  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = {}
for line in open(os.path.join(HERE, ".env")):
    if "=" in line:
        k, v = line.rstrip("\n").split("=", 1)
        ENV[k] = v

GITEA = "http://127.0.0.1:3330"
NC = "http://127.0.0.1:8481"
USER_PASS = ENV["USER_PASS"]


# ---------------------------------------------------------------- Gitea
class Gitea:
    def __init__(self, sudo=None):
        self.s = requests.Session()
        self.s.auth = (ENV["GITEA_ADMIN_USER"], ENV["GITEA_ADMIN_PASS"])
        self.sudo = sudo

    def _h(self, sudo):
        who = sudo if sudo is not None else self.sudo
        return {"Sudo": who} if who else {}

    def req(self, method, path, sudo=None, ok=(200, 201, 204), **kw):
        r = self.s.request(method, GITEA + "/api/v1" + path, headers=self._h(sudo), timeout=30, **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"gitea {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None

    def get(self, path, sudo=None, **kw):
        return self.req("GET", path, sudo=sudo, **kw)

    def ensure_user(self, username, full_name, email=None):
        r = self.s.get(f"{GITEA}/api/v1/users/{username}", timeout=30)
        if r.status_code == 200:
            return r.json()
        return self.req("POST", "/admin/users", sudo="", json={
            "username": username, "full_name": full_name, "email": email or f"{username}@acme.test",
            "password": USER_PASS, "must_change_password": False, "send_notify": False})


# ---------------------------------------------------------------- Nextcloud
class Nextcloud:
    def __init__(self, user=None, password=None):
        self.user = user or ENV["NC_ADMIN_USER"]
        self.s = requests.Session()
        self.s.auth = (self.user, password or (ENV["NC_ADMIN_PASS"] if user is None else USER_PASS))
        self.s.headers.update({"OCS-APIRequest": "true", "Accept": "application/json"})

    def ocs(self, method, path, ok=(200,), **kw):
        r = self.s.request(method, NC + "/ocs/v2.php" + path, timeout=60, **kw)
        try:
            j = r.json()
        except ValueError:
            raise RuntimeError(f"nextcloud {method} {path} -> {r.status_code}: {r.text[:300]}")
        code = j.get("ocs", {}).get("meta", {}).get("statuscode")
        if r.status_code not in ok and code not in (100, 200):
            raise RuntimeError(f"nextcloud {method} {path} -> {r.status_code}/{code}: {json.dumps(j)[:300]}")
        return j["ocs"].get("data")

    def dav(self, method, path, ok=(200, 201, 204, 207), **kw):
        url = f"{NC}/remote.php/dav/files/{urllib.parse.quote(self.user)}/{urllib.parse.quote(path.lstrip('/'))}"
        r = self.s.request(method, url, timeout=60, **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"nextcloud dav {method} {path} -> {r.status_code}: {r.text[:200]}")
        return r

    def mkdir(self, path):
        return self.dav("MKCOL", path, ok=(201, 405))

    def put(self, path, data):
        return self.dav("PUT", path, data=data.encode() if isinstance(data, str) else data)

    def exists(self, path):
        return self.dav("PROPFIND", path, ok=(207, 404), headers={"Depth": "0"}).status_code == 207

    def listdir(self, path):
        r = self.dav("PROPFIND", path, ok=(207, 404), headers={"Depth": "1"})
        if r.status_code == 404:
            return None
        import re
        hrefs = re.findall(r"<d:href>([^<]+)</d:href>", r.text)
        base = urllib.parse.quote(f"/remote.php/dav/files/{self.user}/{path.strip('/')}")
        out = []
        for h in hrefs[1:]:
            out.append(urllib.parse.unquote(h.rstrip("/").split("/")[-1]))
        return out


def occ(*args, check=True):
    p = subprocess.run(["docker", "exec", "-u", "www-data", "ra-nextcloud-1", "php", "occ", *args], capture_output=True, text=True, timeout=300)
    if check and p.returncode != 0:
        raise RuntimeError(f"occ {' '.join(args[:3])} -> {p.returncode}: {(p.stderr or p.stdout)[-300:]}")
    return p.stdout


def nc_ensure_user(uid, display, groups=()):
    nc = Nextcloud()
    try:
        nc.ocs("GET", f"/cloud/users/{uid}")
        exists = True
    except RuntimeError:
        exists = False
    if not exists:
        nc.ocs("POST", "/cloud/users", data={"userid": uid, "password": USER_PASS, "displayName": display, "email": f"{uid}@acme.test"})
    for g in groups:
        nc.ocs("POST", f"/cloud/users/{uid}/groups", data={"groupid": g})
