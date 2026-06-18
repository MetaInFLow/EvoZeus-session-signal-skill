import test from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  runFixedOfficialFactor,
  runOfficialFactorById
} from "../scripts/run-official-factor.mjs";

const fixtureRoot = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

test("runs the fixed official test factor from a pack", async () => {
  const result = await runFixedOfficialFactor({
    packRoot: join(fixtureRoot, "official-packs"),
    sessionPath: join(fixtureRoot, "sessions", "repeated-request.json")
  });

  assert.equal(result.factor_id, "fixed.repeated-request");
  assert.equal(result.pack_id, "evozeus-test-pack");
  assert.equal(result.status, "matched");
  assert.deepEqual(result.tags, ["loop:rerequest"]);
  assert.ok(result.evidence_refs.includes("event:user-2"));
});

test("runs a specified official factor by id from a pack", async () => {
  const result = await runOfficialFactorById("test.tool-failure", {
    packRoot: join(fixtureRoot, "official-packs"),
    sessionPath: join(fixtureRoot, "sessions", "tool-failure.json")
  });

  assert.equal(result.factor_id, "test.tool-failure");
  assert.equal(result.pack_id, "evozeus-test-pack");
  assert.equal(result.status, "matched");
  assert.deepEqual(result.tags, ["tool:error"]);
  assert.ok(result.evidence_refs.includes("event:tool-1"));
});

test("fails clearly when the specified official factor does not exist", async () => {
  await assert.rejects(
    () =>
      runOfficialFactorById("missing.factor", {
        packRoot: join(fixtureRoot, "official-packs"),
        sessionPath: join(fixtureRoot, "sessions", "tool-failure.json")
      }),
    /missing\.factor/
  );
});
