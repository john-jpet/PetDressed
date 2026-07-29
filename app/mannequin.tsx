/**
 * Depicts an outfit on an abstract mannequin, driven by stored garment
 * attributes rather than photographs.
 *
 * The figure is deliberately a schematic: no gender, no body type, no size.
 * The tech spec lists body-shape judgements as a non-goal, and a flat
 * geometric form keeps this a diagram of clothes rather than a depiction of a
 * person. The brutalist styling helps — nobody mistakes it for a portrait.
 *
 * Everything is inline SVG with no DOM dependency, so it ports to
 * react-native-svg largely unchanged.
 */
"use client";

import { useId } from "react";
import type { Color } from "@shared/types";
import { assignSlots, paintOrder, type Slot } from "@shared/outfit-slots";

/** Anything the mannequin needs to draw a garment. */
export interface MannequinGarment {
  garment_id: string;
  category: string;
  display_name: string;
  colors: Color[];
  pattern: string | null;
}

/** Garment shapes, sharing the 100x200 grid the base figure is drawn on. */
const GARMENT_SHAPES: Record<Slot, string> = {
  torso: "M30 43 L41 39 L50 47 L59 39 L70 43 L79 57 L70 62 L69 103 L31 103 L30 62 L21 57 Z",
  legs: "M33 101 H67 L65 183 H52 L50 128 L48 183 H35 Z",
  full: "M31 43 L42 39 L50 47 L58 39 L69 43 L67 99 L76 152 L24 152 L33 99 Z",
  outer:
    "M27 41 L40 37 L50 49 L60 37 L73 41 L83 59 L74 64 L73 122 L27 122 L26 64 L17 59 Z M50 49 V122",
  feet: "M35 179 H49 L51 194 H32 Z M51 179 H65 L68 194 H49 Z",
  held: "M73 106 H91 V130 H73 Z M78 106 V100 A7 7 0 0 1 92 100 V106",
};

/** The bare figure, drawn once beneath any clothing. */
const FIGURE = [
  "M50 10 A14 14 0 1 1 50 38 A14 14 0 1 1 50 10 Z",
  "M45 36 H55 V45 H45 Z",
  "M32 44 H68 L66 105 H34 Z",
  "M32 45 L23 47 L19 105 L27 106 Z",
  "M68 45 L77 47 L81 105 L73 106 Z",
  "M34 105 H66 L64 119 H36 Z",
  "M37 119 H48 L47 185 H38 Z",
  "M52 119 H63 L62 185 H53 Z",
];

/** Patterns worth distinguishing at this size; everything else reads as solid. */
const PATTERN_SHAPES: Record<string, string> = {
  striped: "M0 0 L0 8",
  checked: "M0 0 H8 M0 0 V8",
  graphic: "M2 2 h2 v2 h-2 Z",
  floral: "M2 2 h2 v2 h-2 Z",
  abstract: "M2 2 h2 v2 h-2 Z",
  textured: "M2 2 h2 v2 h-2 Z",
};

const FALLBACK_FILL = "#9a9a92";

/**
 * Very light garments need a heavier outline to stay legible against the
 * paper background. `lab[0]` is CIELAB lightness, which the palette already
 * stores, so this is a measurement rather than a guess about the hex.
 */
function outlineWidth(color: Color | undefined): number {
  return color && color.lab[0] > 82 ? 4 : 2.5;
}

export function Mannequin({
  garments,
  className,
}: {
  garments: MannequinGarment[];
  className?: string;
}) {
  // Pattern ids must be unique per instance or several mannequins on one page
  // resolve each other's fills.
  const scope = useId().replace(/:/g, "");
  const worn = assignSlots(garments);
  const order = paintOrder(worn);

  const label = order.length
    ? `Outfit: ${order.map((slot) => worn.get(slot)!.display_name).join(", ")}`
    : "Mannequin with no garments assigned";

  return (
    <svg
      className={className}
      viewBox="0 0 100 200"
      role="img"
      aria-label={label}
      focusable="false"
    >
      <defs>
        {order.map((slot) => {
          const garment = worn.get(slot)!;
          const shape = PATTERN_SHAPES[garment.pattern ?? ""];
          if (!shape) return null;
          return (
            <pattern
              key={slot}
              id={`pat-${scope}-${slot}`}
              width="8"
              height="8"
              patternUnits="userSpaceOnUse"
              patternTransform={garment.pattern === "striped" ? "rotate(35)" : undefined}
            >
              <path
                d={shape}
                fill={garment.pattern === "striped" || garment.pattern === "checked" ? "none" : "#0a0a0a"}
                stroke={
                  garment.pattern === "striped" || garment.pattern === "checked"
                    ? "#0a0a0a"
                    : "none"
                }
                strokeWidth="1.6"
                opacity="0.32"
              />
            </pattern>
          );
        })}
      </defs>

      {/* Bare figure, always drawn so empty slots read as unclothed rather than missing. */}
      <g fill="#dedad0" stroke="#0a0a0a" strokeWidth="2.5" strokeLinejoin="miter">
        {FIGURE.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>

      {order.map((slot) => {
        const garment = worn.get(slot)!;
        const dominant = garment.colors[0];
        const patterned = Boolean(PATTERN_SHAPES[garment.pattern ?? ""]);
        return (
          <g key={slot}>
            <path
              d={GARMENT_SHAPES[slot]}
              fill={dominant?.hex ?? FALLBACK_FILL}
              stroke="#0a0a0a"
              strokeWidth={outlineWidth(dominant)}
              strokeLinejoin="miter"
            />
            {patterned && (
              <path d={GARMENT_SHAPES[slot]} fill={`url(#pat-${scope}-${slot})`} stroke="none" />
            )}
          </g>
        );
      })}
    </svg>
  );
}
