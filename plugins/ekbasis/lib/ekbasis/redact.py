"""Credentials out of what leaves this machine (0.1.42): every state the client sends (ask), the hook logs, the monitor
log and the hooks' messages go through redact_line().

The guards never send a file's content (the shell guard sends names, sizes, ages and short keyed fingerprints), but
the command line itself is part of the state, and a secret typed on it (`printf '%s' 'vck_...' > f`, `export
TOKEN=...`, `curl -H "Authorization: Bearer ..."`, `git remote set-url origin https://user:token@...`, `--password=...`)
would otherwise reach the server and the local logs as typed. redact_line() replaces such values with a placeholder
made only of letters, digits and underscores (`REDACTED_1`, `vck_REDACTED_2`): the same value gets the same
placeholder, and quotes, spaces, redirections and paths stay where they are, so the line reads the same to the guards.

What it replaces, in this order:
- the body of a PEM private key (`-----BEGIN ... PRIVATE KEY-----` ... `-----END ...`);
- tokens with a known prefix: sk-ant-, sk-/sk-proj-, sk_live_/sk_test_/rk_live_, vck_, hf_, ghp_/gho_/ghs_/ghu_/ghr_,
  github_pat_, xoxa-/xoxb-/xoxp-/xoxr-, AKIA/ASIA (AWS key ids), glpat-, npm_, pypi-AgE, AIza (Google), JWTs (eyJ...
  with two dots);
- the value of an Authorization, Proxy-Authorization, X-Api-Key, Api-Key or X-Auth-Token header (the scheme, Bearer
  or Basic, stays), and of a Cookie header;
- the password in a URL (`scheme://user:PASSWORD@host`);
- the value of --password, --passwd, --token, --api-key, --apikey, --secret, --client-secret, --access-token,
  --auth-token (`--token=X` or `--token X`);
- the value of an assignment or a JSON/YAML key whose name contains token (not tokens or tokenizer), secret, passw,
  api_key/apikey, auth (not author), credential or private_key (`GITHUB_TOKEN=...`, `"api_key": "..."`), when the value
  has 8 or more characters and is not a number, true/false/none/null or a path;
- as a last resort, a word of 32 or more letters, digits, `_`, `-`, `+`, `=` with upper and lower case letters, at least
  two digits and high entropy (base64-like keys without a known prefix).
A value that is a variable or a substitution (`$TOKEN`, `$(cat key)`) is not a secret on the line and stays. Paths,
file names, git refs and hashes stay: hexadecimal strings (commit ids, sha256 sums), words with `/` or `.`, and UUIDs
are never taken for keys.

Limits: a secret without a known prefix that is short, all one case, or hexadecimal, and is not the value of one of
the names, headers or options above, is not recognized. Redaction is a safety net, not a reason to type secrets on a
command line. EKBASIS_REDACT=0 turns it off (for example with your own server)."""
from __future__ import annotations

import math
import os
import re

_WORD = r"[A-Za-z0-9_\-]"
PREFIXED = [
    ("sk-ant", re.compile(r"(?<![A-Za-z0-9_-])(sk-ant-)[A-Za-z0-9_\-]{20,}")),
    ("sk", re.compile(r"(?<![A-Za-z0-9_-])(sk-(?:proj-|svcacct-|admin-)?)[A-Za-z0-9_\-]{20,}")),
    ("stripe", re.compile(r"(?<![A-Za-z0-9_-])((?:sk|rk|pk)_(?:live|test)_)[A-Za-z0-9]{16,}")),
    ("vck", re.compile(r"(?<![A-Za-z0-9_-])(vck_)[A-Za-z0-9]{20,}")),
    ("hf", re.compile(r"(?<![A-Za-z0-9_-])(hf_)[A-Za-z0-9]{20,}")),
    ("github", re.compile(r"(?<![A-Za-z0-9_-])(gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}")),
    ("slack", re.compile(r"(?<![A-Za-z0-9_-])(xox[abpr]-)[A-Za-z0-9\-]{10,}")),
    ("aws", re.compile(r"(?<![A-Za-z0-9])((?:AKIA|ASIA))[A-Z0-9]{16}(?![A-Za-z0-9])")),
    ("gitlab", re.compile(r"(?<![A-Za-z0-9_-])(glpat-)[A-Za-z0-9_\-]{20,}")),
    ("npm", re.compile(r"(?<![A-Za-z0-9_-])(npm_)[A-Za-z0-9]{30,}")),
    ("pypi", re.compile(r"(?<![A-Za-z0-9_-])(pypi-AgE)[A-Za-z0-9_\-]{20,}")),
    ("google", re.compile(r"(?<![A-Za-z0-9_-])(AIza)[A-Za-z0-9_\-]{30,}")),
    ("jwt", re.compile(r"(?<![A-Za-z0-9_-])()eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
]
PEM = re.compile(r"(-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----)(.*?)(-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S)
HEADER = re.compile(r"(?i)\b(authorization|proxy-authorization|x-api-key|api-key|x-auth-token)(\s*:\s*)"
                    r"((?:bearer|basic|token|bot)\s+)?([^\s\"']+)")
COOKIE = re.compile(r"(?i)\b((?:set-)?cookie\s*:\s*)([^\"'\n]+)")
URL_PASS = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://[^/\s:@'\"]+:)([^@/\s'\"$`]+)(@)")
OPTION = re.compile(r"(?i)(--(?:password|passwd|token|api-key|apikey|api_key|secret|client-secret|access-token|"
                    r"auth-token)(?:=|\s+))(['\"]?)([^\s'\"$`][^\s'\"]*)")
NAMED = r"[A-Za-z0-9_\-]*(?:token(?!s|iz)|secret|passw|api_?key(?!s)|apikey|auth(?!or)|credential|private_?key)[A-Za-z0-9_\-]*"
ASSIGN = re.compile(r"(?i)(?<![A-Za-z0-9_\-])(" + NAMED + r")(=)(['\"]?)([^\s'\"$`;&|<>()][^\s'\";&|<>()]*)")
JSON_KEY = re.compile(r"(?i)([\"']" + NAMED + r"[\"']\s*:\s*)([\"'])([^\"'$`\s]+)([\"'])")
YAML_KEY = re.compile(r"(?im)^(\s*" + NAMED + r"\s*:\s+)([^\s\"'$`#][^\s#]*)$")
LONG = re.compile(r"(?<![A-Za-z0-9_\-+/.])([A-Za-z0-9][A-Za-z0-9_\-+]{30,}[A-Za-z0-9_\-+=]*)(?![A-Za-z0-9_\-+=/.])")
HEX = re.compile(r"[0-9a-fA-F_\-]+")


def _entropy(s: str) -> float:
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in (s.count(x) for x in set(s)))


def _looks_random(w: str) -> bool:
    return (not HEX.fullmatch(w) and any(c.isupper() for c in w) and any(c.islower() for c in w)
            and sum(c.isdigit() for c in w) >= 2 and _entropy(w) >= 4.0)


def redact(text: str) -> tuple[str, int]:
    """(text with credential-looking values replaced, how many distinct values were replaced). Placeholders keep a
    known prefix (vck_REDACTED_1) and are made of [A-Za-z0-9_] only."""
    if not text or os.environ.get("EKBASIS_REDACT") == "0":
        return text, 0
    seen: dict = {}

    def ph(value: str, prefix: str = "") -> str:
        if value not in seen:
            seen[value] = len(seen) + 1
        return f"{prefix}REDACTED_{seen[value]}"

    def skip(v: str) -> bool:
        return not v or v.startswith(("$", "`")) or "REDACTED_" in v

    def skip_named(v: str) -> bool:
        """A value by name only: not a flag, a number, a word like true, or a path (TOKEN_FILE=/run/secrets/t)."""
        return (skip(v) or len(v) < 8 or v.lower() in ("true", "false", "none", "null") or v.replace(".", "").isdigit()
                or v.startswith(("/", "./", "../", "~")))

    text = PEM.sub(lambda m: m.group(1) + ("\n" if m.group(2).startswith("\n") else "") + ph(m.group(2).strip())
                   + ("\n" if m.group(2).endswith("\n") else "") + m.group(3), text)
    for _, rx in PREFIXED:
        text = rx.sub(lambda m: m.group(1) + ph(m.group(0)[len(m.group(1)):] if m.group(1) else m.group(0)), text)
    text = HEADER.sub(lambda m: m.group(1) + m.group(2) + (m.group(3) or "")
                      + (m.group(4) if skip(m.group(4)) else ph(m.group(4))), text)
    text = COOKIE.sub(lambda m: m.group(1) + (m.group(2) if skip(m.group(2).strip()) else ph(m.group(2).strip())
                                              + m.group(2)[len(m.group(2).rstrip()):]), text)
    text = URL_PASS.sub(lambda m: m.group(1) + (m.group(2) if skip(m.group(2)) else ph(m.group(2))) + m.group(3), text)
    text = OPTION.sub(lambda m: m.group(1) + m.group(2) + (m.group(3) if skip(m.group(3)) else ph(m.group(3))), text)
    text = ASSIGN.sub(lambda m: m.group(1) + m.group(2) + m.group(3)
                      + (m.group(4) if skip_named(m.group(4)) else ph(m.group(4))), text)
    text = JSON_KEY.sub(lambda m: m.group(1) + m.group(2) + (m.group(3) if skip_named(m.group(3)) else ph(m.group(3)))
                        + m.group(4), text)
    text = YAML_KEY.sub(lambda m: m.group(1) + (m.group(2) if skip_named(m.group(2)) else ph(m.group(2))), text)
    text = LONG.sub(lambda m: ph(m.group(1)) if _looks_random(m.group(1)) and "REDACTED_" not in m.group(1)
                    else m.group(1), text)
    return text, len(seen)


def redact_line(text: str) -> str:
    """The text with credential-looking values replaced (see redact())."""
    return redact(text)[0]
