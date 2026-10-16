"""HTTP client for a served Ekbasis (the System One API: POST /v1/systemone). Standard library only.

Endpoint: EKBASIS_URL (default http://127.0.0.1:8000, the address serve.py listens on by default). An optional
EKBASIS_API_KEY is sent as a bearer token, for deployments behind a gateway.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


from ._version import __version__
from .redact import redact, redact_line


class EkbasisError(RuntimeError):
    pass


USER_AGENT = f"ekbasis/{__version__} (+https://github.com/OpenInterpretability/ekbasis)"

# Feedback verdicts accepted by the hosted API (POST {EKBASIS_URL}/feedback).
VERDICTS = ("correct", "wrong", "prevented_harm", "false_alarm")


def _cache_dir() -> Path:
    return Path(os.environ.get("EKBASIS_CACHE_DIR") or Path.home() / ".cache" / "ekbasis")


def last_request_id() -> str | None:
    """The request id of the last answer this machine received from the hosted API, if any (for `feedback --last`)."""
    try:
        return json.loads((_cache_dir() / "last_request_id").read_text())["id"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


UPDATE_NOTICE_EVERY = 86400   # seconds: tell the user about a newer client at most once a day


def _version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return None


def _maybe_notice_update(latest) -> None:
    """0.1.36: the hosted API sends the latest published client version (X-Ekbasis-Latest-Python). When it is newer than
    this one, say so on stderr, at most once a day (never on stdout, which tools parse). EKBASIS_NO_UPDATE_CHECK=1 turns
    it off. Any failure here is ignored: the notice must never get in the way of an answer."""
    try:
        if not latest or os.environ.get("EKBASIS_NO_UPDATE_CHECK") == "1":
            return
        new, cur = _version_tuple(latest), _version_tuple(__version__)
        if not new or not cur or new <= cur:
            return
        stamp = os.path.join(os.path.expanduser("~"), ".cache", "ekbasis", "update-notice")
        try:
            if time.time() - os.path.getmtime(stamp) < UPDATE_NOTICE_EVERY:
                return
        except OSError:
            pass
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        with open(stamp, "w") as f:
            f.write(str(latest))
        sys.stderr.write(f"ekbasis {latest} is available (you have {__version__}): pip install -U ekbasis "
                         f"(set EKBASIS_NO_UPDATE_CHECK=1 to hide this)\n")
    except Exception:  # noqa: BLE001
        pass


def _remember_request_id(rid: str) -> None:
    """Best effort: keep only the id and the time, never the question or the answer."""
    try:
        d = _cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        f = d / "last_request_id"
        f.write_text(json.dumps({"id": rid, "t": int(time.time())}))
        f.chmod(0o600)
    except OSError:
        pass


def server_timing(header: str | None) -> dict:
    """A Server-Timing header as {name: milliseconds} ("queue;dur=12, model;dur=480" -> {"queue": 12.0, "model": 480.0})."""
    out = {}
    for part in (header or "").split(","):
        bits = [b.strip() for b in part.split(";")]
        dur = next((b[4:] for b in bits[1:] if b.startswith("dur=")), None)
        if bits[0] and dur is not None:
            try:
                out[bits[0]] = float(dur)
            except ValueError:
                pass
    return out


class FeedbackRejected(EkbasisError):
    """The server refused the feedback (unknown or someone else's request id, already sent, rate limit, no key)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class CannotJudge(EkbasisError):
    """The guard could not check: the server cannot be reached or did not answer in time, the folder or repository
    cannot be read, or the command line has parts it cannot evaluate. Treat it as risky (fail closed)."""


@dataclass
class Calibrated:
    """The same answer at the temperature the hosted API fit on held-out validation (0.1.41): read these probabilities
    as frequencies (of the answers it gives at 0.9, about 9 in 10 are right). Same chosen answer as the plain fields,
    which keep the model's raw probabilities; every threshold built into this client reads the raw ones, so nothing it
    decides changes. None when the server does not send it (self-hosted servers before this field)."""
    temperature: float
    confidence: float
    probabilities: dict = field(default_factory=dict)
    p_yes: float | None = None

    @classmethod
    def from_api(cls, c: dict | None, qtype: str | None) -> "Calibrated | None":
        if not isinstance(c, dict) or "confidence" not in c:
            return None
        if qtype in ("noul", "boolean"):
            p = float(c["probability"])
            return cls(temperature=float(c.get("temperature", 0)), confidence=float(c["confidence"]),
                       probabilities={"yes": p, "no": 1 - p}, p_yes=p)
        return cls(temperature=float(c.get("temperature", 0)), confidence=float(c["confidence"]),
                   probabilities=dict(c.get("probabilities") or {}))


@dataclass
class Answer:
    """One typed answer. value: True/False for yes/no questions, the chosen label for the others. p_yes: the probability
    of "yes" (yes/no questions). probabilities: every option's probability. confidence: the chosen answer's probability.
    These are the model's raw probabilities; calibrated (when the server sends it) holds the same answer's calibrated
    probabilities, the ones to show people or to set your own thresholds on."""
    value: object
    confidence: float
    probabilities: dict = field(default_factory=dict)
    p_yes: float | None = None
    calibrated: Calibrated | None = None

    @classmethod
    def from_api(cls, a: dict) -> "Answer":
        cal = Calibrated.from_api(a.get("calibrated"), a.get("type"))
        if a.get("type") in ("noul", "boolean"):
            p = float(a["probability"])
            return cls(value=bool(a["value"]), confidence=float(a["confidence"]), probabilities={"yes": p, "no": 1 - p}, p_yes=p,
                       calibrated=cal)
        value = a.get("choice", a.get("score"))
        return cls(value=value, confidence=float(a["confidence"]), probabilities=dict(a.get("probabilities") or {}),
                   calibrated=cal)


QUESTION_TYPES = ("noul", "choice", "score")


def _redact_questions(questions: dict) -> tuple[dict, dict]:
    """0.1.42: every string of the questions as sent (instructions, which recap() fills with the caller's rules, and the
    criteria's labels and descriptions, which callers such as the MCP tool write), credentials replaced (ekbasis.redact).
    Returns (the questions to send, {question: {label as sent: the caller's label}}) so that answers come back with the
    caller's labels. "type" is never touched."""
    out, labels = {}, {}
    for name, q in questions.items():
        sent = {}
        for k, v in q.items():
            if k == "type":
                sent[k] = v
            elif k == "criteria" and isinstance(v, dict):
                keys = [str(x) for x in v]
                red = redact("\n".join(keys))[0].split("\n")   # one pass: distinct values, distinct placeholders
                if len(red) != len(keys) or len(set(red)) != len(red):
                    red = [x if redact(x)[1] == 0 else f"REDACTED_LABEL_{i + 1}" for i, x in enumerate(keys)]
                sent[k] = {r: redact_line(d) if isinstance(d, str) else d for r, d in zip(red, v.values())}
                labels[name] = {r: orig for r, orig in zip(red, v) if r != str(orig)}
            elif isinstance(v, str):
                sent[k] = redact_line(v)
            elif isinstance(v, list):
                sent[k] = [redact_line(x) if isinstance(x, str) else x for x in v]
            else:
                sent[k] = v
        out[name] = sent
    return out, {n: m for n, m in labels.items() if m}


def _restore_labels(a: "Answer", m: dict) -> "Answer":
    """The answer with the caller's labels where a label was redacted before sending."""
    if not m:
        return a
    a.value = m.get(a.value, a.value) if isinstance(a.value, str) else a.value
    a.probabilities = {m.get(k, k): p for k, p in a.probabilities.items()}
    if a.calibrated is not None:
        a.calibrated.probabilities = {m.get(k, k): p for k, p in a.calibrated.probabilities.items()}
    return a


def _check_questions(questions) -> None:
    """Refuse a malformed question before sending it. The server reads the question from `instructions` and ignores any
    other field, so a question in `question` (or with no text) would get one same answer whatever it asked."""
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a non-empty dict: {name: {\"type\": \"noul\", \"instructions\": \"...?\"}}")
    for name, q in questions.items():
        if not isinstance(q, dict):
            raise ValueError(f"question {name!r} must be a dict with \"type\" and \"instructions\"")
        if q.get("type") not in QUESTION_TYPES:
            raise ValueError(f"question {name!r}: type must be one of {', '.join(QUESTION_TYPES)}, not {q.get('type')!r}")
        text = q.get("instructions")
        if not isinstance(text, str) or not text.strip():
            hint = next((k for k in ("question", "prompt", "text", "query") if k in q), None)
            raise ValueError(f"question {name!r} has no \"instructions\"" +
                             (f" (it has {hint!r}: the server ignores that field; put the question in \"instructions\")"
                              if hint else ""))


class Ekbasis:
    """client = Ekbasis(); client.ask(state, {"name": question, ...}) -> {"name": Answer, ...}"""

    def __init__(self, url: str | None = None, api_key: str | None = None, timeout: float = 120.0,
                 surface: str | None = None):
        self.url = (url or os.environ.get("EKBASIS_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("EKBASIS_API_KEY")
        self.timeout = timeout
        # Where the call comes from (git-check, claude-hook, mcp, ...): sent as X-Ekbasis-Surface, metadata only.
        self.surface = surface or os.environ.get("EKBASIS_SURFACE")
        # The hosted API returns an id with every answer (X-Ekbasis-Request-Id), used to send feedback on it.
        self.last_request_id: str | None = None
        self.last_usage: dict | None = None   # the token counts of the last answer, when the server sends them
        self.last_timing: dict = {}           # Server-Timing of the last answer, {name: ms} (hosted API: queue, model)
        self.last_status: int | None = None   # HTTP status of the last request

    def _call(self, path: str, body: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.surface:
            headers["X-Ekbasis-Surface"] = self.surface
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.url}{path}", data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read())
                if isinstance(out, dict) and isinstance(out.get("usage"), dict):
                    self.last_usage = out["usage"]
                self.last_status, self.last_timing = r.status, server_timing(r.headers.get("Server-Timing"))
                rid = r.headers.get("X-Ekbasis-Request-Id")
                if rid:
                    self.last_request_id = rid
                    _remember_request_id(rid)
                _maybe_notice_update(r.headers.get("X-Ekbasis-Latest-Python"))
                return out
        except urllib.error.HTTPError as e:
            self.last_status, self.last_timing = e.code, server_timing(e.headers.get("Server-Timing") if e.headers else None)
            raise CannotJudge(f"HTTP {e.code} from {self.url}{path}: {e.read().decode(errors='replace')[:400]}") from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise CannotJudge(f"the Ekbasis server at {self.url} did not answer within {self.timeout:g} s") from None
            raise CannotJudge(f"cannot reach the Ekbasis server at {self.url} ({e.reason}); start it with serve.py, "
                              f"or set EKBASIS_URL") from None
        except (socket.timeout, TimeoutError):
            raise CannotJudge(f"the Ekbasis server at {self.url} did not answer within {self.timeout:g} s") from None
        except (OSError, ValueError) as e:  # a dropped connection, or an answer that is not JSON
            raise CannotJudge(f"no usable answer from the Ekbasis server at {self.url} ({e})") from None

    def health(self) -> dict:
        return self._call("/health")

    def ask(self, state: str, questions: dict, read_once: bool = False, images=None) -> dict:
        """Every question about the same state, answered in one request (the server batches them; read_once=True reads
        the state once for all of them, on models trained for it). images: data URIs or base64 strings (vLLM backend)."""
        _check_questions(questions)
        sent, labels = _redact_questions(questions)   # 0.1.42: credentials typed in a line, rules or question stay here
        body = {"state": redact_line(state), "questions": sent}
        if read_once:
            body["read_once"] = True
        if images:
            body["images"] = list(images)
        d = self._call("/v1/systemone", body)
        return {k: _restore_labels(Answer.from_api(v), labels.get(k, {})) for k, v in d["answers"].items()}

    def feedback(self, verdict: str, request_id: str | None = None, note: str | None = None, retry_s: float = 2.0) -> dict:
        """Tell the hosted API how an answer turned out: "correct", "wrong", "prevented_harm" (it stopped a real
        mistake) or "false_alarm". request_id defaults to this client's last answer, then to this machine's last one.
        Free, one per request id, kept 30 days. Raises FeedbackRejected (with .status) or CannotJudge (unreachable)."""
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
        rid = request_id or self.last_request_id or last_request_id()
        if not rid:
            raise ValueError("no request id: pass one, or make a call to the hosted API first")
        body = {"request_id": rid, "verdict": verdict}
        if note:
            body["note"] = redact_line(str(note))[:500]
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for attempt in range(2):
            req = urllib.request.Request(f"{self.url}/feedback", data=json.dumps(body).encode(), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:300]
                try:
                    msg = json.loads(text).get("error") or text
                except ValueError:
                    msg = text
                # The id is registered just after the answer is sent: a feedback sent at once may arrive first.
                if e.code == 404 and attempt == 0 and retry_s > 0:
                    time.sleep(retry_s)
                    continue
                if e.code in (404, 405) and "/api/v1" not in self.url and "request id" not in str(msg):
                    msg = f"{msg} (feedback is a hosted-API feature: EKBASIS_URL=https://openinterp.org/api/v1)"
                raise FeedbackRejected(e.code, str(msg)) from None
            except urllib.error.URLError as e:
                raise CannotJudge(f"cannot reach {self.url} ({e.reason})") from None
            except (socket.timeout, TimeoutError):
                raise CannotJudge(f"{self.url} did not answer within {self.timeout:g} s") from None
        raise FeedbackRejected(404, "unknown request id")


# Since 0.1.8 the user-facing wording is "cannot foresee" (Ekbasis forecasts, it does not judge); the old name stays.
CannotForesee = CannotJudge
