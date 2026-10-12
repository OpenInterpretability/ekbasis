import type { Ekbasis } from "./client.js";
import { worldState, type Question } from "./prompts.js";

export const LOOK_BELOW = 0.9;
export const HARM_AT = 0.5;

export interface PrefixCheck { step: number; pYes: Record<string, number>; confidence: number }
export interface PlanCheck {
  /** Every prefix forecast harmless with confidence >= lookBelow: run the whole plan. */
  ok: boolean;
  /** How many leading actions are predicted safe to run now. */
  safe: number;
  reason: "flagged" | "unsure" | null;
  step: number | null;
  flags: string[];
  prefixes: PrefixCheck[];
  requests: number;
}

export interface PlanOptions { lookBelow?: number; harmAt?: number; maxSteps?: number; notes?: string[]; parallel?: number }

/** Forecast every prefix of the plan from `state`; stop at the first one flagged or uncertain (ekbasis.check_plan). */
export async function checkPlan(client: Ekbasis, rules: string, state: string, actions: string[],
                                harm: Record<string, Question>, o: PlanOptions = {}): Promise<PlanCheck> {
  const lookBelow = o.lookBelow ?? LOOK_BELOW, harmAt = o.harmAt ?? HARM_AT, width = Math.max(1, o.parallel ?? 4);
  for (const [k, q] of Object.entries(harm)) {
    if (q.type !== "noul") throw new Error(`harm question ${k} must be a yes/no question (yesNo) whose yes is the harm`);
  }
  const pc: PlanCheck = { ok: false, safe: 0, reason: null, step: null, flags: [], prefixes: [], requests: 0 };
  if (!actions.length) return { ...pc, ok: true };
  const n = o.maxSteps ? Math.min(actions.length, o.maxSteps) : actions.length;
  for (let start = 1; start <= n; start += width) {
    const wave = Array.from({ length: Math.min(width, n - start + 1) }, (_, j) => start + j);
    const answers = await Promise.all(wave.map((i) => client.ask(worldState(rules, state, actions.slice(0, i), o.notes), harm)));
    pc.requests += wave.length;
    for (let j = 0; j < wave.length; j++) {
      const p: Record<string, number> = {};
      for (const [k, a] of Object.entries(answers[j])) p[k] = a.pYes ?? 0;
      const conf = Math.min(...Object.values(p).map((x) => Math.max(x, 1 - x)));
      pc.prefixes.push({ step: wave[j], pYes: p, confidence: Math.round(conf * 1e4) / 1e4 });
      const flags = Object.keys(p).filter((k) => p[k] >= harmAt);
      if (flags.length || conf < lookBelow) {
        return { ...pc, safe: wave[j] - 1, step: wave[j], reason: flags.length ? "flagged" : "unsure", flags };
      }
    }
  }
  const ok = n === actions.length;
  return { ...pc, ok, safe: n, step: ok ? null : n + 1, reason: ok ? null : "unsure" };
}

export interface PlanRun { done: number; stopped: PlanCheck | null; checks: PlanCheck[]; looks: number }

/** Check, run the safe prefix, read the real state, check the rest; stop before a step still flagged (ekbasis.run_plan). */
export async function runPlan(client: Ekbasis, rules: string, actions: string[], harm: Record<string, Question>,
                              observe: () => Promise<string> | string, execute: (a: string[]) => Promise<void> | void,
                              o: PlanOptions = {}): Promise<PlanRun> {
  const out: PlanRun = { done: 0, stopped: null, checks: [], looks: 0 };
  while (out.done < actions.length) {
    const state = await observe();
    out.looks += 1;
    const pc = await checkPlan(client, rules, state, actions.slice(out.done), harm, o);
    out.checks.push(pc);
    if (pc.ok) { await execute(actions.slice(out.done)); out.done = actions.length; break; }
    if (pc.safe) { await execute(actions.slice(out.done, out.done + pc.safe)); out.done += pc.safe; continue; }
    out.stopped = pc;
    break;
  }
  return out;
}
