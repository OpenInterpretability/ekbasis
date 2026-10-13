import { test } from "node:test";
import assert from "node:assert/strict";
import { checkQuestions } from "../dist/index.js";

test("every question shape the API accepts passes the client check", () => {
  checkQuestions({
    a: { type: "noul", instructions: "Lost?", criteria: { true: "lost", false: "kept" } },
    b: { type: "boolean", instructions: "Lost?" },
    c: { type: "choice", instructions: "Which?", options: ["x", "y"] },
    d: { type: "choice", instructions: "Which?", criteria: { x: "x", y: "y" } },
    e: { type: "score", instructions: "How many?", criteria: { 0: "none", 1: "one" } },
    f: { type: "score", instructions: "How many?", criteria: ["0", "1"] },
  });
  assert.throws(() => checkQuestions({ q: { type: "bogus", instructions: "?" } }), /type must be one of/);
});
