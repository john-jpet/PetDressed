/**
 * Platform-agnostic PetDressed API client.
 *
 * Uses only the global `fetch`, so the same module runs in the browser, in a
 * Cloudflare Worker, and in React Native. Authentication is injected as a token
 * provider rather than imported, because each platform stores its session
 * differently — Supabase's browser client on web, secure storage on mobile.
 *
 * Nothing here may import from React, Next.js, or React Native.
 */
import type {
  GarmentCard,
  GarmentStatus,
  InProgressGarment,
  MetadataConfirmPayload,
  MetadataResult,
  OutfitPlan,
  PlanLocation,
  SegmentationResult,
  UploadSession,
  UserSettings,
  WardrobePage,
} from "./types";

/** A non-2xx response. `status` is 0 when the request never reached the API. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Resolves the current access token, or `null` when signed out. */
export type TokenProvider = () => Promise<string | null> | string | null;

export interface ClientOptions {
  baseUrl: string;
  getToken: TokenProvider;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Sends the request without an Authorization header. */
  anonymous?: boolean;
}

export class PetDressedClient {
  private readonly baseUrl: string;
  private readonly getToken: TokenProvider;

  constructor(options: ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.getToken = options.getToken;
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = "GET", body, anonymous = false } = options;
    const headers: Record<string, string> = {};

    if (!anonymous) {
      const token = await this.getToken();
      if (!token) throw new ApiError("Not signed in.", 401);
      headers.Authorization = `Bearer ${token}`;
    }
    if (body !== undefined) headers["Content-Type"] = "application/json";

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError("Could not reach the PetDressed service.", 0);
    }

    if (!response.ok) throw new ApiError(await describeFailure(response), response.status);
    if (response.status === 204) return undefined as T;

    const text = await response.text();
    if (!text) return undefined as T;
    return JSON.parse(text) as T;
  }

  // --- Uploads -------------------------------------------------------------

  createUploadSession(input: {
    filename: string;
    content_type: string;
    file_size_bytes: number;
  }): Promise<UploadSession> {
    return this.request("/api/v1/garments/uploads", { method: "POST", body: input });
  }

  /**
   * Uploads the raw bytes straight to object storage using the presigned form.
   * Deliberately unauthenticated — the presigned fields carry the grant, and
   * sending a bearer token to the storage host would leak it.
   */
  async uploadToStorage(session: UploadSession, file: Blob, filename: string): Promise<void> {
    const form = new FormData();
    for (const [key, value] of Object.entries(session.upload_fields)) {
      form.append(key, value);
    }
    form.append("file", file, filename);

    let response: Response;
    try {
      response = await fetch(session.upload_url, { method: "POST", body: form });
    } catch {
      throw new ApiError("The image upload did not finish.", 0);
    }
    if (!response.ok) throw new ApiError("The image upload did not finish.", response.status);
  }

  completeUpload(garmentId: string, objectKey: string): Promise<void> {
    return this.request(`/api/v1/garments/${garmentId}/uploads/complete`, {
      method: "POST",
      body: { object_key: objectKey },
    });
  }

  inProgressGarment(): Promise<InProgressGarment | null> {
    return this.request("/api/v1/garments/in-progress");
  }

  garmentStatus(garmentId: string): Promise<GarmentStatus> {
    return this.request(`/api/v1/garments/${garmentId}/status`);
  }

  // --- Segmentation --------------------------------------------------------

  segmentation(garmentId: string): Promise<SegmentationResult> {
    return this.request(`/api/v1/garments/${garmentId}/segmentation`);
  }

  retrySegmentation(garmentId: string, corrections: unknown): Promise<void> {
    return this.request(`/api/v1/garments/${garmentId}/segmentation/retry`, {
      method: "POST",
      body: corrections,
    });
  }

  acceptSegmentation(garmentId: string): Promise<void> {
    return this.request(`/api/v1/garments/${garmentId}/segmentation/accept`, { method: "POST" });
  }

  // --- Metadata ------------------------------------------------------------

  metadata(garmentId: string): Promise<MetadataResult> {
    return this.request(`/api/v1/garments/${garmentId}/metadata`);
  }

  confirmMetadata(garmentId: string, payload: MetadataConfirmPayload): Promise<GarmentCard> {
    return this.request(`/api/v1/garments/${garmentId}/metadata/confirm`, {
      method: "POST",
      body: payload,
    });
  }

  // --- Wardrobe ------------------------------------------------------------

  wardrobe(filters: { season?: string } = {}): Promise<WardrobePage> {
    const query = filters.season && filters.season !== "all" ? `?season=${filters.season}` : "";
    return this.request(`/api/v1/garments${query}`);
  }

  updateGarment(garmentId: string, changes: { availability?: string }): Promise<GarmentCard> {
    return this.request(`/api/v1/garments/${garmentId}`, { method: "PATCH", body: changes });
  }

  markWorn(garmentId: string): Promise<GarmentCard> {
    return this.request(`/api/v1/garments/${garmentId}/worn`, { method: "POST" });
  }

  deleteGarment(garmentId: string): Promise<void> {
    return this.request(`/api/v1/garments/${garmentId}`, { method: "DELETE" });
  }

  // --- Planning ------------------------------------------------------------

  generatePlan(input: {
    start_date: string;
    days: number;
    location: PlanLocation;
  }): Promise<OutfitPlan> {
    return this.request("/api/v1/plans/generate", {
      method: "POST",
      body: {
        ...input,
        daily_requirements: [],
        locked_items: [],
        excluded_items: [],
      },
    });
  }

  lockDay(planId: string, date: string): Promise<OutfitPlan> {
    return this.request(`/api/v1/plans/${planId}/days/${date}/lock`, { method: "POST" });
  }

  regenerateDay(planId: string, date: string): Promise<OutfitPlan> {
    return this.request(`/api/v1/plans/${planId}/days/${date}/regenerate`, {
      method: "POST",
      body: { preserve_garment_ids: [], exclude_previous_selection: true },
    });
  }

  replaceGarment(
    planId: string,
    date: string,
    garmentId: string,
    replacementCategory: string,
  ): Promise<OutfitPlan> {
    return this.request(`/api/v1/plans/${planId}/days/${date}/replace`, {
      method: "POST",
      body: { garment_id: garmentId, replacement_category: replacementCategory },
    });
  }

  // --- Settings ------------------------------------------------------------

  settings(): Promise<UserSettings> {
    return this.request("/api/v1/settings");
  }

  saveSettings(value: UserSettings): Promise<UserSettings> {
    return this.request("/api/v1/settings", { method: "PUT", body: value });
  }
}

/** Pulls the most specific message the API offered, falling back to the status. */
async function describeFailure(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  } catch {
    // Non-JSON error bodies fall through to the generic message.
  }
  return `Request failed with status ${response.status}.`;
}
