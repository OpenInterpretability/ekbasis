"""Write apps/.env with fresh random test credentials for the local app stack (every service is bound to 127.0.0.1, and
the mail server has no route out). The values are never printed. Refuses to overwrite an existing .env unless --force.
    python3 gen_credentials.py [--force]"""
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")


def password():
    # letters and digits from a random token, with a fixed prefix and suffix so every password has upper and lower case,
    # a digit and a symbol (the same shape as the studies' credentials)
    return "Ra" + secrets.token_urlsafe(18).replace("-", "x").replace("_", "y") + "9!"


def main():
    if os.path.exists(ENV) and "--force" not in sys.argv[1:]:
        sys.exit(f"{ENV} exists; pass --force to replace it (the running apps keep the old admin passwords)")
    values = {"GITEA_ADMIN_USER": "raadmin", "GITEA_ADMIN_PASS": password(), "NC_ADMIN_USER": "raadmin",
              "NC_ADMIN_PASS": password(), "MAIL_ADMIN_PASS": password(), "USER_PASS": password()}
    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("".join(f"{k}={v}\n" for k, v in values.items()))
    os.chmod(ENV, 0o600)
    print(f"wrote {ENV} (mode 600)")


if __name__ == "__main__":
    main()
