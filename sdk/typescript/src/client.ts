import type { Question } from "./prompts.js";

export const VERSION = "0.1.0";
const QUESTION_TYPES = ["noul", "choice", "score"];

export class EkbasisError extends Error {}
/** The server could not be reached, refused the request or did not answer in time: treat the action as unchecked. */
export class CannotJudge extends EkbasisError {}

export interface Answer {
  value: boolean | string | number;
  confidence: number;
  probabilities: Record<string, number>;
  /** yes/no questions: the probability of yes. */
  pYes?: number;
}

export interface Usage { inputTokens?: number; requestId?: string; ms: number; serverTiming?: Record<string, number> }

export interface EkbasisOptions { url?: string; apiKey?: string; timeoutMs?: number; surface?: string; fetch?: typeof fetch }

function env(name: string): string | undefined {
  const p = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
  return p?.env?.[name];
}

/** Refuse a malformed question before sending it: the server reads only `instructions`. */
export function checkQuestions(questions: Record<string, Question>): void {
  const names = Object.keys(questions ?? {});
  if (!names.length) throw new Error('questions must be a non-empty object: {name: {type: "noul", instructions: "...?"}}');
  for (const name of names) {
    const q = questions[name] as Record<string, unknown>;
    if (!q || typeof q !== "object") throw new Error(`question ${name} must be an object with "type" and "instructions"`);
    if (!QUESTION_TYPES.includes(String(q.type))) throw new Error(`question ${name}: type must be one of ${QUESTION_TYPES.join(", ")}`);
    if (typeof q.instructions !== "string" || !q.instructions.trim()) {
      const hint = ["question", "prompt", "text", "query"].find((k) => k in q);
      throw new Error(`question ${name} has no "instructions"` +
        (hint ? ` (it has "${hint}": the server ignores that field; put the question in "instructions")` : ""));
    }
  }
}

export function readAnswer(a: Record<string, unknown>): Answer {
  if (a.type === "noul" || a.type === "boolean") {
    const p = Number(a.probability);
    return { value: Boolean(a.value), confidence: Number(a.confidence), probabilities: { yes: p, no: 1 - p }, pYes: p };
  }
  const probs = (a.probabilities ?? {}) as Record<string, number>;
  return { value: (a.choice ?? a.score) as string | number, confidence: Number(a.confidence), probabilities: { ...probs } };
}

/** const ek = new Ekbasis(); await ek.ask(state, {name: question}) -> {name: Answer}. */
export class Ekbasis {
  readonly url: string;
  private readonly apiKey?: string;
  private readonly timeoutMs: number;
  private readonly surface?: string;
  private readonly fetcher: typeof fetch;
  lastUsage?: Usage;

  constructor(o: EkbasisOptions = {}) {
    this.url = (o.url ?? env("EKBASIS_URL") ?? "https://openinterp.org/api/v1").replace(/\/+$/, "");
    this.apiKey = o.apiKey ?? env("EKBASIS_API_KEY");
    this.timeoutMs = o.timeoutMs ?? 120_000;
    this.surface = o.surface ?? env("EKBASIS_SURFACE");
    this.fetcher = o.fetch ?? fetch;
  }

  private async call(path: string, body?: unknown): Promise<Record<string, unknown>> {
    const headers: Record<string, string> = { "Content-Type": "application/json", "User-Agent": `ekbasis-js/${VERSION}` };
    if (this.apiKey) headers.Authorization = `Bearer ${this.apiKey}`;
    if (this.surface) headers["X-Ekbasis-Surface"] = this.surface;
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), this.timeoutMs);
    const t0 = Date.now();
    try {
      const r = await this.fetcher(`${this.url}${path}`, {
        method: body === undefined ? "GET" : "POST", headers, signal: ctl.signal,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await r.text();
      if (!r.ok) throw new CannotJudge(`HTTP ${r.status} from ${this.url}${path}: ${text.slice(0, 400)}`);
      const d = JSON.parse(text) as Record<string, unknown>;
      const timing: Record<string, number> = {};
      for (const part of (r.headers.get("server-timing") ?? "").split(",")) {
        const bits = part.split(";").map((b) => b.trim());
        const dur = bits.find((b) => b.startsWith("dur="));
        if (bits[0] && dur) timing[bits[0]] = Number(dur.slice(4));
      }
      const usage = (d.usage ?? {}) as { input_tokens?: number };
      const metered = r.headers.get("X-Ekbasis-Metered-Tokens");
      this.lastUsage = { ms: Date.now() - t0, serverTiming: timing, requestId: r.headers.get("X-Ekbasis-Request-Id") ?? undefined,
                         inputTokens: usage.input_tokens ?? (metered ? Number(metered) : undefined) };
      return d;
    } catch (e) {
      if (e instanceof CannotJudge) throw e;
      const why = (e as Error).name === "AbortError" ? `did not answer within ${this.timeoutMs / 1000} s` : `(${(e as Error).message})`;
      throw new CannotJudge(`no usable answer from the Ekbasis server at ${this.url} ${why}`);
    } finally {
      clearTimeout(timer);
    }
  }

  async health(): Promise<Record<string, unknown>> {
    return this.call("/health");
  }

  /** Every question about the same state, answered in one request. */
  async ask(state: string, questions: Record<string, Question>, opts: { readOnce?: boolean; images?: string[] } = {}):
      Promise<Record<string, Answer>> {
    checkQuestions(questions);
    const body: Record<string, unknown> = { state, questions };
    if (opts.readOnce) body.read_once = true;
    if (opts.images?.length) body.images = opts.images;
    const d = await this.call("/v1/systemone", body);
    const out: Record<string, Answer> = {};
    for (const [k, v] of Object.entries((d.answers ?? {}) as Record<string, Record<string, unknown>>)) out[k] = readAnswer(v);
    return out;
  }
}
