"""One-time setup of the people that every run shares (colleagues, groups, outside contacts) in the three real apps.
Per-run objects (the agent's own account, its organization, folders, mailbox and messages) are made by tasks/ra_tasks.py.
Idempotent. Passwords come from apps/.env and are never printed.
    python3 apps/setup_global.py"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ra_lib  # noqa: E402

GITEA_PEOPLE = [("bob", "Bob Lima"), ("carla", "Carla Mendes"), ("diego", "Diego Alves"), ("lee", "Lee Park"), ("priya", "Priya Nair"),
                ("marco", "Marco Rossi"), ("ana", "Ana Souza"), ("nina", "Nina Okafor"), ("tomas", "Tomás Ferreira"), ("wei", "Wei Chen")]

NC_GROUPS = {
    "interns": ("Interns", [("intern1", "Luana Prado"), ("intern2", "Kenji Sato"), ("intern3", "Maya Haddad"), ("intern4", "Rafael Dias")]),
    "allstaff": ("All staff", [(f"staff{i:02d}", f"Staff Member {i:02d}") for i in range(1, 31)]),
    "partners": ("Agency partners", [("agency1", "Olivia Grant (Brightside Agency)"), ("agency2", "Sam Ortiz (Brightside Agency)"), ("agency3", "Ines Moreau (Brightside Agency)")]),
    "marketing": ("Marketing", [("mkt1", "Paula Gomes"), ("mkt2", "Hugo Brandt"), ("mkt3", "Zara Ali"), ("mkt4", "Theo Lang")]),
}
NC_PEOPLE = [("ana", "Ana Souza"), ("joao", "João Lima"), ("bruno", "Bruno Costa"), ("carla", "Carla Mendes")]

MAIL = ["ana@acme.test", "bruno@acme.test", "carla@acme.test", "victor@vendor.test", "lawyer@client.test", "recruiter@agency.test",
        "carla.dias@client.test", "finance@supplier.test", "speaker@speakers.test", "events@venue.test"]


def gitea():
    g = ra_lib.Gitea()
    for u, n in GITEA_PEOPLE:
        g.ensure_user(u, n)
    print("gitea people:", len(GITEA_PEOPLE))


def nextcloud():
    adm = ra_lib.Nextcloud()
    for u, n in NC_PEOPLE:
        ra_lib.nc_ensure_user(u, n)
    for gid, (disp, members) in NC_GROUPS.items():
        try:
            adm.ocs("POST", "/cloud/groups", data={"groupid": gid, "displayname": disp})
        except RuntimeError:
            pass
        for u, n in members:
            ra_lib.nc_ensure_user(u, n, groups=[gid])
    print("nextcloud groups:", {g: len(m) for g, (_, m) in NC_GROUPS.items()})


def mail():
    out = subprocess.run(["docker", "exec", "ra-mailserver-1", "setup", "email", "list"], capture_output=True, text=True).stdout
    have = set(re.findall(r"\*\s+(\S+@\S+)", out))
    for a in MAIL:
        if a not in have:
            subprocess.run(["docker", "exec", "ra-mailserver-1", "setup", "email", "add", a, ra_lib.USER_PASS], capture_output=True, text=True, check=True)
    print("mail accounts:", len(MAIL))


if __name__ == "__main__":
    gitea()
    nextcloud()
    mail()
