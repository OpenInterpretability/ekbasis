"""HTTP client for a served Ekbasis (the System One API: POST /v1/systemone). Standard library only.

Endpoint: EKBASIS_URL (default http://127.0.0.1:8000, the address serve.py listens on by default). An optional
EKBASIS_API_KEY is sent as a bearer token, for deployments behind a gateway.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field


from ._version import __version__


class EkbasisError(RuntimeError):
    pass


USER_AGENT = f"ekbasis/{__version__} (+https://github.com/OpenInterpretability/ekbasis)"


class CannotJudge(EkbasisError):
    """The guard could not check: the server cannot be reached or did not answer in time, the folder or repository
    cannot be read, or the command line has parts it cannot evaluate. Treat it as risky (fail closed)."""


@dataclass
class Answer:
    """One typed answer. value: True/False for yes/no questions, the chosen label for the others. p_yes: the probability
    of "yes" (yes/no questions). probabilities: every option's probability. confidence: the chosen answer's probability."""
    value: object
    confidence: float
    probabilities: dict = field(default_factory=dict)
    p_yes: float | None = None

    @classmethod
    def from_api(cls, a: dict) -> "Answer":
        if a.get("type") in ("noul", "boolean"):
            p = float(a["probability"])
            return cls(value=bool(a["value"]), confidence=float(a["confidence"]), probabilities={"yes": p, "no": 1 - p}, p_yes=p)
        value = a.get("choice", a.get("score"))
        return cls(value=value, confidence=float(a["confidence"]), probabilities=dict(a.get("probabilities") or {}))


class Ekbasis:
    """client = Ekbasis(); client.ask(state, {"name": question, ...}) -> {"name": Answer, ...}"""

    def __init__(self, url: str | None = None, api_key: str | None = None, timeout: float = 120.0):
        self.url = (url or os.environ.get("EKBASIS_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("EKBASIS_API_KEY")
        self.timeout = timeout

    def _call(self, path: str, body: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.url}{path}", data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
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
        body = {"state": state, "questions": questions}
        if read_once:
            body["read_once"] = True
        if images:
            body["images"] = list(images)
        d = self._call("/v1/systemone", body)
        return {k: Answer.from_api(v) for k, v in d["answers"].items()}


# Since 0.1.8 the user-facing wording is "cannot foresee" (Ekbasis forecasts, it does not judge); the old name stays.
CannotForesee = CannotJudge
