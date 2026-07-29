import assert from "node:assert/strict";
import test from "node:test";

import { assignSlots, paintOrder, slotForCategory } from "../../../packages/shared/outfit-slots.ts";

const g = (category: string, name = category) => ({ category, display_name: name });

test("maps every planner category onto a slot", () => {
  assert.equal(slotForCategory("top"), "torso");
  assert.equal(slotForCategory("bottom"), "legs");
  assert.equal(slotForCategory("one_piece"), "full");
  assert.equal(slotForCategory("outerwear"), "outer");
  assert.equal(slotForCategory("shoes"), "feet");
  assert.equal(slotForCategory("accessory"), "held");
});

test("ignores categories it cannot place", () => {
  assert.equal(slotForCategory("hat"), null);
  assert.equal(slotForCategory(""), null);
  // Guard against inherited Object properties resolving as slots.
  assert.equal(slotForCategory("constructor"), null);
  assert.equal(slotForCategory("toString"), null);
});

test("a one-piece suppresses the garments it would cover", () => {
  // The solver treats these as mutually exclusive; drawing all three would
  // stack a dress, a shirt, and trousers on top of each other.
  const worn = assignSlots([g("top"), g("bottom"), g("one_piece")]);
  assert.ok(worn.has("full"));
  assert.equal(worn.has("torso"), false);
  assert.equal(worn.has("legs"), false);
});

test("a one-piece leaves shoes and accessories alone", () => {
  const worn = assignSlots([g("one_piece"), g("shoes"), g("accessory")]);
  assert.deepEqual([...worn.keys()].sort(), ["feet", "full", "held"]);
});

test("the first garment in a slot wins", () => {
  // Two tops is not expected, but the outcome must not depend on ordering luck.
  const worn = assignSlots([g("top", "first"), g("top", "second")]);
  assert.equal(worn.get("torso")?.display_name, "first");
});

test("unplaceable garments do not displace real ones", () => {
  const worn = assignSlots([g("hat"), g("top", "shirt")]);
  assert.equal(worn.size, 1);
  assert.equal(worn.get("torso")?.display_name, "shirt");
});

test("paints back to front so outerwear covers what it is worn over", () => {
  const worn = assignSlots([g("shoes"), g("outerwear"), g("top"), g("bottom")]);
  assert.deepEqual(paintOrder(worn), ["torso", "legs", "outer", "feet"]);
});

test("an empty outfit yields nothing to paint", () => {
  assert.deepEqual(paintOrder(assignSlots([])), []);
});
