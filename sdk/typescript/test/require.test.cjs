// CommonJS consumers: require("ekbasis") must load the same API as the ESM build.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

test("require() loads the CommonJS build", () => {
  const pkg = require(path.join(__dirname, "..", "package.json"));
  const m = require(path.join(__dirname, "..", pkg.exports["."].require));
  for (const k of ["Ekbasis", "checkPlan", "runPlan", "harms", "HARMS", "yesNo", "worldState", "CannotJudge"]) {
    assert.ok(k in m, `missing ${k}`);
  }
  assert.equal(m.VERSION, pkg.version);
  assert.ok(m.worldState("R", "S", ["a"]).startsWith("R\n\nCurrent state:\nS"));
});
