/**
 * Flat garment silhouettes drawn as inline SVG.
 *
 * Thick square-capped strokes on a 100x100 grid, matching the 3px borders the
 * rest of the interface uses. Everything paints with `currentColor` so a single
 * set works on paper, on ink, and on acid backgrounds.
 *
 * Inline rather than asset files: the app is edge-deployed behind a strict
 * CSP, and these need to render before any network request settles.
 */

export type GarmentIconName =
  | "top"
  | "bottom"
  | "one_piece"
  | "outerwear"
  | "shoes"
  | "accessory";

/** Maps an API category to an icon, falling back to a generic top. */
export function iconForCategory(category: string): GarmentIconName {
  return category in PATHS ? (category as GarmentIconName) : "top";
}

const PATHS: Record<GarmentIconName, string> = {
  // T-shirt: shoulder line, sleeves, straight body.
  top: "M20 20 L38 12 L50 21 L62 12 L80 20 L88 42 L74 48 L74 88 L26 88 L26 48 L12 42 Z",
  // Trousers: waistband above two legs. The gap has to clear roughly twice the
  // stroke width or the legs close up at small sizes.
  bottom: "M26 12 H74 L79 88 H61 L50 44 L39 88 H21 Z",
  // Dress: fitted shoulders flaring to a hem.
  one_piece: "M34 14 L44 12 L50 19 L56 12 L66 14 L62 38 L80 88 L20 88 L38 38 Z",
  // Jacket: same shell as a top, plus lapels and a centre seam.
  outerwear:
    "M20 20 L38 12 L50 24 L62 12 L80 20 L88 44 L76 50 L76 88 L24 88 L24 50 L12 44 Z M50 24 L50 88",
  // Boot: shaft dropping into a sole.
  shoes: "M24 22 H44 L46 52 L76 64 L84 78 V88 H24 Z",
  // Tote: rectangular body with a handle.
  accessory: "M28 38 H72 V88 H28 Z M40 38 V28 A10 10 0 0 1 60 28 V38",
};

const LABELS: Record<GarmentIconName, string> = {
  top: "Top",
  bottom: "Bottom",
  one_piece: "One piece",
  outerwear: "Outerwear",
  shoes: "Shoes",
  accessory: "Accessory",
};

interface GarmentIconProps {
  name: GarmentIconName;
  className?: string;
  /** Announce the icon instead of hiding it. Omit for decorative use. */
  labelled?: boolean;
}

export function GarmentIcon({ name, className, labelled = false }: GarmentIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 100 100"
      fill="none"
      stroke="currentColor"
      strokeWidth={7}
      strokeLinecap="square"
      strokeLinejoin="miter"
      role={labelled ? "img" : undefined}
      aria-label={labelled ? LABELS[name] : undefined}
      aria-hidden={labelled ? undefined : true}
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

/**
 * A garment on a hanger, used where the app is waiting for a photo. The hanger
 * hook and the shirt are separate paths so CSS can swing only the garment.
 */
export function HangingGarment({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 100 100"
      fill="none"
      stroke="currentColor"
      strokeWidth={6}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M50 8 A7 7 0 1 1 50 22 V30" />
      <path d="M50 30 L18 54 H82 Z" />
      <path d="M28 54 L24 92 H76 L72 54" />
    </svg>
  );
}

/**
 * Decorative rail of garments. `count` repeats the cycle; each item is offset
 * by CSS so the row reads as clothes hanging at slightly different heights.
 */
export function ClothingRail({ className, count = 6 }: { className?: string; count?: number }) {
  const cycle: GarmentIconName[] = [
    "top",
    "bottom",
    "outerwear",
    "one_piece",
    "shoes",
    "accessory",
  ];
  return (
    <div className={className} aria-hidden="true">
      <span className="rail-bar" />
      <div className="rail-items">
        {Array.from({ length: count }, (_, index) => (
          <GarmentIcon key={index} name={cycle[index % cycle.length]} className="rail-item" />
        ))}
      </div>
    </div>
  );
}
