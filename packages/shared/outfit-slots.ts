/**
 * Which part of a figure each garment covers, and what wins when garments
 * overlap.
 *
 * Platform-agnostic on purpose: the rules are the same whether an outfit is
 * drawn with SVG on the web or react-native-svg on a device, and they must
 * agree with the solver rather than each renderer inventing its own.
 */

/** A region of the figure a garment can occupy. */
export type Slot = "torso" | "legs" | "full" | "outer" | "feet" | "held";

const SLOT_BY_CATEGORY: Record<string, Slot> = {
  top: "torso",
  bottom: "legs",
  one_piece: "full",
  outerwear: "outer",
  shoes: "feet",
  accessory: "held",
};

/**
 * Paint order, back to front. Outerwear covers what it is worn over, and a
 * held item sits in front of everything.
 */
export const PAINT_ORDER: readonly Slot[] = [
  "full",
  "torso",
  "legs",
  "outer",
  "feet",
  "held",
];

/** The minimum a renderer needs to place a garment. */
export interface SlottedGarment {
  category: string;
}

/**
 * Maps an API category onto a slot, or null when it is not wearable.
 *
 * Uses an own-property check rather than a plain lookup: `"constructor"` and
 * `"toString"` resolve to inherited functions, which are truthy and would slip
 * past a `?? null` fallback.
 */
export function slotForCategory(category: string): Slot | null {
  return Object.hasOwn(SLOT_BY_CATEGORY, category) ? SLOT_BY_CATEGORY[category] : null;
}

/**
 * Resolves which garments are actually drawn.
 *
 * A one-piece covers torso and legs, so drawing it alongside a top or bottom
 * would stack garments on top of each other. The planner already treats these
 * as mutually exclusive; this keeps the drawing agreeing with the solver
 * instead of inventing a second rule. Within a slot the first garment wins,
 * so the result does not depend on response ordering luck.
 */
export function assignSlots<T extends SlottedGarment>(garments: readonly T[]): Map<Slot, T> {
  const assigned = new Map<Slot, T>();
  for (const garment of garments) {
    const slot = slotForCategory(garment.category);
    if (slot && !assigned.has(slot)) assigned.set(slot, garment);
  }
  if (assigned.has("full")) {
    assigned.delete("torso");
    assigned.delete("legs");
  }
  return assigned;
}

/** Occupied slots in paint order, back to front. */
export function paintOrder<T extends SlottedGarment>(assigned: Map<Slot, T>): Slot[] {
  return PAINT_ORDER.filter((slot) => assigned.has(slot));
}
