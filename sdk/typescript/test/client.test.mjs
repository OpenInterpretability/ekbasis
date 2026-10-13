import { test } from "node:test";
import assert from "node:assert/strict";
import { Ekbasis, CannotJudge, yesNo, choice, worldState, checkPlan, runPlan } from "../dist/index.js";

const noul = (p) => ({ type: "noul", value: p >= 0.5, probability: p, confidence: Math.max(p, 1 - p) });

// A scripted server: the harm probability of a prefix is set by the last action it contains.
function scripted(byAction, log = []) {
  return async (url, init) => {
    const body = JSON.parse(init.body);
    log.push({ url, headers: init.headers, body });
    const acts = body.state.split("Actions, in order:\n")[1].split("\n\n")[0].split("\n");
    const last = acts[acts.length - 1].replace(/^\d+\. /, "");
    const answers = {};
    for (const k of Object.keys(body.questions)) answers[k] = noul(byAction[last] ?? 0.01);
    return new Response(JSON.stringify({ answers, usage: { input_tokens: 100 } }),
      { status: 200, headers: { "server-timing": "auth;dur=3, model;dur=410", "X-Ekbasis-Request-Id": "r1", "X-Ekbasis-Model": "ekbasis-27b-int4-v1.3" } });
  };
}
const harm = { data: yesNo("Do these actions permanently delete data the user did not ask to delete?") };

test("worldState matches the Python layout", () => {
  assert.equal(worldState("R", "S", ["a", "b"]),
    "R\n\nCurrent state:\nS\n\nActions, in order:\n1. a\n2. b\n\nThe questions are about the state after all these actions.");
});

test("choice builds criteria from a list", () => {
  assert.deepEqual(choice("Which?", ["x", "y"]), { type: "choice", instructions: "Which?", criteria: { x: "x", y: "y" } });
});

test("ask sends Bearer auth and parses answers, usage and server-timing", async () => {
  const log = [];
  const ek = new Ekbasis({ url: "https://h/api/v1/", apiKey: "k", fetch: scripted({ a: 0.97 }, log) });
  const a = await ek.ask(worldState("R", "S", ["a"]), harm);
  assert.equal(log[0].url, "https://h/api/v1/v1/systemone");
  assert.equal(log[0].headers.Authorization, "Bearer k");
  assert.equal(a.data.value, true);
  assert.equal(a.data.pYes, 0.97);
  assert.equal(ek.lastUsage.inputTokens, 100);
  assert.equal(ek.lastUsage.serverTiming.model, 410);
  assert.equal(ek.lastUsage.requestId, "r1");
  assert.equal(ek.lastUsage.model, "ekbasis-27b-int4-v1.3");
});

test("a question without instructions is refused before sending, with a hint", async () => {
  const ek = new Ekbasis({ url: "http://x", fetch: () => assert.fail("sent") });
  await assert.rejects(ek.ask("s", { q: { type: "noul", question: "?" } }), /has no "instructions".*"question"/);
});

test("HTTP errors and network errors become CannotJudge", async () => {
  const e1 = new Ekbasis({ url: "http://x", fetch: async () => new Response("no", { status: 402 }) });
  await assert.rejects(e1.ask("s", harm), CannotJudge);
  const e2 = new Ekbasis({ url: "http://x", fetch: async () => { throw new TypeError("fetch failed"); } });
  await assert.rejects(e2.ask("s", harm), CannotJudge);
});

const steps = ["list", "backup", "delete uploads", "restart"];

for (const parallel of [1, 2, 4, 10]) {
  test(`checkPlan stops at the flagged step (parallel=${parallel})`, async () => {
    const ek = new Ekbasis({ url: "http://x", fetch: scripted({ "delete uploads": 0.986 }) });
    const pc = await checkPlan(ek, "R", "S", steps, harm, { parallel });
    assert.equal(pc.ok, false);
    assert.equal(pc.reason, "flagged");
    assert.equal(pc.step, 3);
    assert.equal(pc.safe, 2);
    assert.deepEqual(pc.flags, ["data"]);
    assert.deepEqual(pc.prefixes.map((p) => p.step), [1, 2, 3]);
  });
}

test("checkPlan: unsure, ok, maxSteps, non-yes/no harm", async () => {
  const unsure = await checkPlan(new Ekbasis({ url: "http://x", fetch: scripted({ backup: 0.3 }) }), "R", "S", steps, harm);
  assert.equal(unsure.reason, "unsure"); assert.equal(unsure.step, 2); assert.equal(unsure.safe, 1);
  const ok = await checkPlan(new Ekbasis({ url: "http://x", fetch: scripted({}) }), "R", "S", steps, harm);
  assert.equal(ok.ok, true); assert.equal(ok.safe, 4); assert.equal(ok.requests, 4);
  const capped = await checkPlan(new Ekbasis({ url: "http://x", fetch: scripted({}) }), "R", "S", steps, harm, { maxSteps: 2 });
  assert.equal(capped.ok, false); assert.equal(capped.safe, 2); assert.equal(capped.step, 3); assert.equal(capped.reason, "unsure");
  await assert.rejects(checkPlan(new Ekbasis({ url: "http://x" }), "R", "S", steps, { c: choice("?", ["a"]) }), /yes\/no/);
});

test("runPlan runs the safe prefix, looks again, stops before a step still flagged", async () => {
  const ek = new Ekbasis({ url: "http://x", fetch: scripted({ "delete uploads": 0.986 }) });
  const ran = [];
  const r = await runPlan(ek, "R", steps, harm, () => "S", (a) => { ran.push(...a); });
  assert.deepEqual(ran, ["list", "backup"]);
  assert.equal(r.done, 2); assert.equal(r.looks, 2); assert.equal(r.stopped.reason, "flagged");
});
