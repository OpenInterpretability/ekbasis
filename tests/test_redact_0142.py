"""0.1.42: credentials typed on a command line do not leave the machine (the state the client sends) nor land in the
hook and monitor logs (ekbasis.redact). Every pattern; no false redaction of paths, hashes, branch names and sums in
common commands; the line keeps its shell structure, so the guards read it the same way. Offline; the keys below are
made up."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import monitor_hook as MH
from ekbasis import shell as S
from ekbasis.client import Ekbasis
from ekbasis.redact import redact, redact_line

FAKE = "Zq7RkT2mW9xLp4Vb8NcY3HsJd6Fg5Ae1"   # 32 characters, made up
AWS = "AKIA" + "ZQ7RKT2MW9XLP4VB"            # (built in pieces: no credential-shaped literal in the source)
JWT = "eyJ" + "hbGciOiJIUzI1NiJ9." + "eyJ" + "zdWIiOiJ0ZXN0In0." + FAKE

# (line, the secret that must be gone, what must be there instead)
CASES = [
    (f"printf '%s' 'vck_{FAKE}' > ~/.config/vercel/key", f"vck_{FAKE}", "'vck_REDACTED_1' > ~/.config/vercel/key"),
    (f"export ANTHROPIC_API_KEY=sk-ant-api03-{FAKE}", FAKE, "sk-ant-REDACTED_1"),
    (f"OPENAI_API_KEY=sk-proj-{FAKE} python3 run.py", FAKE, "sk-proj-REDACTED_1"),
    (f"curl -u sk_live_{FAKE}: https://api.example.invalid", FAKE, "sk_live_REDACTED_1"),
    (f"huggingface-cli login --token hf_{FAKE}", FAKE, "hf_REDACTED_1"),
    (f"git clone https://ghp_{FAKE}@github.com/org/repo.git", FAKE, "ghp_REDACTED_1@github.com"),
    (f"gh auth login --with-token <<< github_pat_11ABCDE_{FAKE}", FAKE, "github_pat_REDACTED_1"),
    (f"curl -d token=xoxb-1234-{FAKE} https://slack.example.invalid", FAKE, "xoxb-REDACTED_1"),
    ("aws configure set aws_access_key_id " + AWS, AWS, "AKIAREDACTED_1"),
    (f"git push https://oauth2:glpat-{FAKE}@gitlab.example.invalid/x.git", FAKE, "glpat-REDACTED_1"),
    (f"npm config set //registry.npmjs.org/:_authToken npm_{FAKE}abcd", FAKE, "npm_REDACTED_1"),
    (f"twine upload -p pypi-AgEIcHlwaS5vcmc{FAKE} dist/*", FAKE, "pypi-AgEREDACTED_1"),
    (f"curl 'https://maps.example.invalid?key=AIzaSy{FAKE}abc'", FAKE, "AIzaREDACTED_1"),
    (f"curl -H 'Authorization: Bearer {JWT}' x", JWT, "Bearer REDACTED_1"),
    (f'curl -H "Authorization: Bearer {FAKE}" https://x.example.invalid', FAKE, '"Authorization: Bearer REDACTED_1"'),
    ('curl -H "Authorization: Basic dXNlcjpwYXNzd29yZA==" https://x', "dXNlcjpwYXNzd29yZA==", "Basic REDACTED_1"),
    (f"curl -H 'X-Api-Key: {FAKE}' https://x", FAKE, "'X-Api-Key: REDACTED_1'"),
    ("curl -H 'Cookie: session=abc123def; csrftoken=x9y8z7' https://x", "abc123def", "'Cookie: REDACTED_1'"),
    ("git remote set-url origin https://caio:hunter2pass@github.com/org/repo.git", "hunter2pass",
     "https://caio:REDACTED_1@github.com/org/repo.git"),
    ("psql postgres://app:S3cr3tPw@localhost:5432/db -c 'select 1'", "S3cr3tPw", "postgres://app:REDACTED_1@localhost"),
    ("mysql -u root --password=Pa55word db < dump.sql", "Pa55word", "--password=REDACTED_1 db < dump.sql"),
    (f"tool --api-key {FAKE} --out result.json", FAKE, "--api-key REDACTED_1 --out result.json"),
    (f'export GITHUB_TOKEN="{FAKE}"; gh pr list', FAKE, 'GITHUB_TOKEN="REDACTED_1"; gh pr list'),
    ("DB_PASSWORD=correct-horse-battery npm run migrate", "correct-horse-battery", "DB_PASSWORD=REDACTED_1 npm run"),
    (f'curl -d \'{{"api_key": "{FAKE}", "name": "x"}}\' https://x', FAKE, '"api_key": "REDACTED_1"'),
    (f"cat > key.pem <<'EOF'\n-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmU\n{FAKE}\n"
     "-----END OPENSSH PRIVATE KEY-----\nEOF\nchmod 600 key.pem", FAKE,
     "-----BEGIN OPENSSH PRIVATE KEY-----\nREDACTED_1\n-----END OPENSSH PRIVATE KEY-----"),
    (f"echo 'QmFzZTY0{FAKE}' | base64 -d > secret.bin", FAKE, "echo 'REDACTED_1' | base64 -d > secret.bin"),
]

# common commands that must not change: paths, file names, git refs, hashes, sums, UUIDs, variables, short values
UNCHANGED = [
    "git log --oneline -3 3f786850e387550fdab836ed7e6dc881de23001b",
    "git checkout -b feature/auth-token-refresh && git log --author=caio --oneline",
    "echo e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  results.json | shasum -a 256 -c",
    "cd /private/tmp/claude-501/-Volumes-SSD-Major-cbmachine/e5f74f7b-1878-42c4-b742-a5a481ca6f4e/scratchpad && ls",
    "docker pull python@sha256:3f786850e387550fdab836ed7e6dc881de23001b3f786850e387550fdab836ed",
    "GIT_AUTHOR_NAME=Dev GIT_AUTHOR_EMAIL=dev@example.invalid git commit -m 'auth: refresh tokens'",
    'curl -H "Authorization: Bearer $(cat ~/.config/ekbasis/ops_read_secret)" https://openinterp.org/api/ops',
    'export HF_TOKEN=$(cat ~/.cache/huggingface/token); curl -H "Authorization: Bearer $HF_TOKEN" https://x',
    "HF_HUB_DISABLE_IMPLICIT_TOKEN=1 PREVIEW_SWITCH_TOKEN=0 python3 -c 'print(1)'",
    "python3 run.py --max_tokens 4096 --tokenizer Qwen/Qwen3-8B --input_tokens_per_check 484",
    "TOKEN_FILE=/run/secrets/api_token ./deploy.sh",
    "git@github.com:OpenInterpretability/ekbasis.git",
    "rsync -a results_skopos/ /Volumes/SSD\\ Major/backup/results_skopos/",
    "ls ~/.local/share/ekbasis-hook/venv/lib/python3.9/site-packages/ekbasis",
    "python3 -c \"import x; print(x.TestAVeryLongFunctionNameNumber12AndMore34)\"",
    "git rev-parse HEAD:results_skopos/runs  # a001e2f703a92c33f9b44b29e5c8706b966547c1",
]


def shape(line):
    """What the guards read from a line: commands, operators, word counts, redirections, quoting."""
    return [(c.joined_by, len(c.words), [r.op for r in c.redirects], [w.quoted for w in c.words])
            for c in S.parse(line).commands]


class TestRedact(unittest.TestCase):
    def test_every_pattern(self):
        for line, secret, want in CASES:
            out, n = redact(line)
            self.assertNotIn(secret, out, line)
            self.assertIn(want, out, line)
            self.assertGreaterEqual(n, 1, line)

    def test_no_false_redaction(self):
        for line in UNCHANGED:
            self.assertEqual(redact(line), (line, 0), line)

    def test_structure_is_kept(self):
        for line, _, _ in CASES:
            self.assertEqual(shape(redact_line(line)), shape(line), line)

    def test_same_value_same_placeholder(self):
        out, n = redact(f"export API_TOKEN={FAKE}; curl -H 'X-Api-Key: {FAKE}' -H 'X-Auth-Token: other-{FAKE}x' x")
        self.assertEqual(n, 2)
        self.assertEqual(out.count("REDACTED_1"), 2)
        self.assertIn("REDACTED_2", out)

    def test_switch_off(self):
        with mock.patch.dict(os.environ, {"EKBASIS_REDACT": "0"}):
            self.assertEqual(redact(CASES[0][0]), (CASES[0][0], 0))


class TestWhatLeaves(unittest.TestCase):
    def test_the_client_sends_the_redacted_state(self):
        sent = {}

        def fake_call(path, body=None):
            sent.update(body)
            return {"answers": {"q": {"value": "no", "confidence": 0.9, "probabilities": {"yes": 0.1, "no": 0.9},
                                      "p_yes": 0.1}}}
        c = Ekbasis(url="http://127.0.0.1:9")
        with mock.patch.object(c, "_call", fake_call):
            c.ask(f"Commands:\n1. export GITHUB_TOKEN=ghp_{FAKE}\n2. rm -rf build",
                  {"q": {"type": "noul", "instructions": "Is anything lost?"}})
        self.assertNotIn(FAKE, json.dumps(sent))
        self.assertIn("ghp_REDACTED_1", sent["state"])
        self.assertIn("rm -rf build", sent["state"])

    def test_hook_log_and_messages(self):
        d = tempfile.mkdtemp()
        log = os.path.join(d, "hook_log.jsonl")
        line = f"export HF_TOKEN=hf_{FAKE}; git $SUB main"   # cannot be judged: no model needed
        data = json.dumps({"tool_name": "Bash", "tool_input": {"command": line}, "cwd": d, "session_id": "s"})
        env = {"EKBASIS_GUARD_MODE": "log", "EKBASIS_HOOK_LOG": log}
        with mock.patch.dict(os.environ, env), mock.patch.object(sys, "stdin", io.StringIO(data)), \
                redirect_stdout(io.StringIO()), mock.patch.object(sys, "stderr", io.StringIO()) as err:
            H.main()
        text = open(log).read()
        self.assertNotIn(FAKE, text + err.getvalue())
        rec = json.loads(text.splitlines()[-1])
        self.assertEqual((rec["command"], rec["redacted"]), ("export HF_TOKEN=hf_REDACTED_1; git $SUB main", 1))
        out = io.StringIO()
        data = json.dumps({"tool_name": "Bash", "tool_input": {"command": line + " # "}, "cwd": d, "session_id": "s"})
        with mock.patch.object(sys, "stdin", io.StringIO(data)), redirect_stdout(out):
            for k in ("EKBASIS_GUARD_MODE", "EKBASIS_FAIL_OPEN"):
                os.environ.pop(k, None)
            H.main()
        self.assertNotIn(FAKE, out.getvalue())

    def test_monitor_log(self):
        d = tempfile.mkdtemp()
        log = os.path.join(d, "monitor_log.jsonl")
        with mock.patch.dict(os.environ, {"EKBASIS_MONITOR_LOG": log}):
            MH._log({"t": 1.0, "tool": "Bash", "call": f"Bash: curl -H 'Authorization: Bearer {FAKE}' x"})
        self.assertNotIn(FAKE, open(log).read())
        json.loads(open(log).read())   # still JSON


if __name__ == "__main__":
    unittest.main()
