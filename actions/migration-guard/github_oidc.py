"""Print this workflow's GitHub Actions OIDC token for the hosted Ekbasis API (the free tier for public repositories).

    python github_oidc.py --api-url https://openinterp.org/api/v1

Used by the migration guard Action when `api-key` is empty. The workflow must grant `permissions: id-token: write`;
GitHub then sets ACTIONS_ID_TOKEN_REQUEST_URL and ACTIONS_ID_TOKEN_REQUEST_TOKEN. The token is requested for the
audience "openinterp.org" and only when `--api-url` is the hosted API, so it is never sent to another server.
Exit 0 with the token on stdout; otherwise exit 1 with the reason on stderr (the token is never printed there).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

AUDIENCE = "openinterp.org"
HOSTED = {"openinterp.org", "www.openinterp.org"}


def hosted(api_url: str) -> bool:
    u = urllib.parse.urlparse(api_url)
    return u.scheme == "https" and (u.hostname or "").lower() in HOSTED


def request_token(env: dict | None = None, timeout: float = 10.0) -> str:
    env = os.environ if env is None else env
    url = env.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    bearer = env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url or not bearer:
        raise RuntimeError("no OIDC token available: add `permissions: id-token: write` to the workflow "
                           "(pull requests from forks never get one)")
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}audience={urllib.parse.quote(AUDIENCE)}",
                                 headers={"Authorization": f"bearer {bearer}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            value = json.loads(r.read()).get("value")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub refused the OIDC token request: HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(f"could not request the OIDC token: {type(e).__name__}") from None
    if not isinstance(value, str) or value.count(".") != 2:
        raise RuntimeError("GitHub returned no OIDC token")
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api-url", required=True)
    a = ap.parse_args(argv)
    if not hosted(a.api_url):
        print(f"not requesting an OIDC token: {a.api_url} is not the hosted API (https://openinterp.org); "
              "set api-key for your own server", file=sys.stderr)
        return 1
    try:
        token = request_token()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.write(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
