"""The 'docs' condition: the same frozen rules Ekbasis reads (adapters/spec_server.py RULES), given to the agent itself in
its system prompt, with their sources.    python3 app_docs.py <gitea|nextcloud|mail>"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "adapters"))
from spec_server import RULES  # noqa: E402

NAMES = {"gitea": "Gitea", "nextcloud": "Nextcloud Files", "mail": "the webmail (Roundcube) and mail server"}
app = sys.argv[1]
print(f"The documentation of {NAMES[app]} says:")
for rule, src in RULES[app]:
    print(f"- {rule} (Source: {src})")
