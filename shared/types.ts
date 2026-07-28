/**
 * API contract types shared by every PetDressed client.
 *
 * These mirror the Pydantic models in `backend/app/schemas.py`. Keep the two in
 * sync: a field that exists here but not there resolves to `undefined` at
 * runtime, which type checking cannot catch on its own.
 *
 * Nothing in this module may import from React, Next.js, or React Native — the
 * mobile client consumes it unchanged.
 */

/** `ColorResponse` — a single extracted palette entry. */
export interface Color {
  hex: string;
  lab: [number, number, number];
  proportion: number;
}

/** `BoundingBox` — pixel coordinates in the source image's natural space. */
export interface BoundingBox {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

/** `PointPrompt` — a single segmentation hint. */
export interface PointPrompt {
  x: number;
  y: number;
}

/** `BrushStroke` — a freehand segmentation correction. */
export interface BrushStroke {
  x: number;
  y: number;
  radius: number;
  value: 0 | 1;
}

/** `PredictionAlternative` — a runner-up classification. */
export interface PredictionAlternative {
  value: string;
  confidence: number;
}

export type GarmentCategory =
  | "top"
  | "bottom"
  | "one_piece"
  | "outerwear"
  | "shoes"
  | "accessory";

export type Availability = "available" | "laundry" | "unavailable" | "packed";

export type Season = "spring" | "summer" | "fall" | "winter";

export type SeasonScores = Record<Season, number>;

/** `UploadSessionResponse` — presigned direct-to-storage upload credentials. */
export interface UploadSession {
  garment_id: string;
  upload_url: string;
  object_key: string;
  expires_at: string;
  upload_method: "POST";
  upload_fields: Record<string, string>;
}

/** `GarmentStatusResponse` — pipeline progress for a single garment. */
export interface GarmentStatus {
  processing_status: string;
  progress: number;
  stage: string;
  error: string | null;
}

/** `InProgressGarmentResponse` — resumes an interrupted upload on sign-in. */
export interface InProgressGarment {
  garment_id: string;
  processing_status: string;
}

/**
 * `SegmentationResultResponse`.
 *
 * Note `review_status`, which the backend sends and earlier client code
 * omitted. The inference-diagnostic fields (`degraded`, `inference_backend`,
 * `inference_warning`) belong to the *metadata* response, not this one.
 */
export interface SegmentationResult {
  garment_id: string;
  processed_url: string;
  preview_url: string;
  mask_url: string;
  mask_area_ratio: number;
  bbox: BoundingBox;
  confidence: number;
  review_status: "pending" | "accepted" | "correction_required";
  model_name: string;
  model_version: string;
}

/** `MetadataReviewResponse` — model suggestions awaiting user confirmation. */
export interface MetadataResult {
  garment_id: string;
  display_name: string | null;
  predicted_category: string;
  category_confidence: number;
  category_alternatives: PredictionAlternative[];
  subcategory: string | null;
  formality: number;
  warmth: number;
  breathability: number;
  water_resistance: number;
  pattern: string;
  colors: Color[];
  seasons: SeasonScores;
  processed_url: string;
  inference_backend: string;
  degraded: boolean;
  inference_warning: string | null;
}

/** `MetadataConfirmRequest`. */
export interface MetadataConfirmPayload {
  display_name: string;
  category: string;
  subcategory: string | null;
  formality: number;
  warmth: number;
  breathability: number;
  water_resistance: number;
  pattern: string;
  planner_enabled: boolean;
  seasons: SeasonScores;
}

/** `GarmentCardResponse` — a wardrobe tile. */
export interface GarmentCard {
  garment_id: string;
  display_name: string;
  category: string;
  subcategory: string | null;
  availability: string;
  planner_enabled: boolean;
  wear_count: number;
  last_worn_at: string | null;
  colors: Color[];
  image_url: string;
  similarity?: number | null;
}

/** `WardrobeResponse` — a paginated wardrobe page. */
export interface WardrobePage {
  items: GarmentCard[];
  page: number;
  page_size: number;
  total: number;
}

/** `ScoreBreakdownResponse` — why the solver chose an outfit. */
export interface ScoreBreakdown {
  weather: number;
  compatibility: number;
  rotation: number;
  preference: number;
  event: number;
  total: number;
}

/** `PlanGarmentResponse` — one piece within a planned outfit. */
export interface PlanGarment {
  garment_id: string;
  category: string;
  display_name: string;
  image_url: string;
}

/** `PlannedDayResponse` — a single day of the plan. */
export interface PlannedOutfit {
  date: string;
  garments: PlanGarment[];
  score: ScoreBreakdown;
  explanations: string[];
  provisional_weather: boolean;
  weather: Record<string, number | string | boolean>;
  is_locked: boolean;
}

/** `PlanResponse` — a solved multi-day plan. */
export interface OutfitPlan {
  plan_id: string;
  status: string;
  solve_time_ms: number;
  relaxed_constraints: string[];
  days: PlannedOutfit[];
}

/** `UserSettingsResponse`. */
export interface UserSettings {
  city: string | null;
  latitude: number | null;
  longitude: number | null;
  timezone: string;
  active_start_hour: number;
  active_end_hour: number;
  repetition_tolerance: number;
  preferred_formality: number;
  accessory_usage: boolean;
  weather_strictness: number;
}

/** `PlanRequest.location`. */
export interface PlanLocation {
  latitude: number;
  longitude: number;
  timezone: string;
}
