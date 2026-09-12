import test from "node:test";
import assert from "node:assert/strict";
import { reconcilePreviews } from "../src/video/film-previews.ts";
const scene = (takes) => ({ index: 4, selected: "original", takes });
test("new completed retakes become the preview without changing the accepted film take", () => {
  const old = scene([
    { id: "original", state: "ready" },
    { id: "repair", state: "running" },
  ]);
  const before = reconcilePreviews([old], {});
  assert.equal(before[4].takeId, "original");
  const after = reconcilePreviews(
    [scene([...old.takes.slice(0, 1), { id: "repair", state: "ready" }])],
    before,
  );
  assert.equal(after[4].takeId, "repair");
  assert.equal(old.selected, "original");
});
test("explicit older preview survives polling, scene navigation, and serialized reload until a new take finishes", () => {
  const scenes = [
    scene([
      { id: "original", state: "ready" },
      { id: "repair", state: "ready" },
    ]),
  ];
  let saved = reconcilePreviews(scenes, {});
  assert.equal(saved[4].takeId, "repair");
  saved[4].takeId = "original";
  assert.equal(
    reconcilePreviews(scenes, JSON.parse(JSON.stringify(saved)))[4].takeId,
    "original",
  );
  scenes[0].takes.push({ id: "third", state: "failed" });
  assert.equal(reconcilePreviews(scenes, saved)[4].takeId, "original");
  scenes[0].takes[2].state = "ready";
  assert.equal(reconcilePreviews(scenes, saved)[4].takeId, "third");
});
