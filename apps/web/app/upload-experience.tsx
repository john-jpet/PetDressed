"use client";

import {
  ChangeEvent,
  DragEvent,
  FormEvent,
  PointerEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createClient } from "@supabase/supabase-js";
import Image from "next/image";
import type {
  GarmentCard,
  GarmentDetail,
  GarmentUpdatePayload,
  InProgressGarment,
  MetadataConfirmPayload,
  MetadataResult,
  OutfitPlan,
  SeasonScores,
  SegmentationResult,
} from "@shared/types";
import {
  ClothingRail,
  GarmentIcon,
  HangingGarment,
  iconForCategory,
} from "./garment-icons";
import { Mannequin } from "./mannequin";

type Tool = "keep" | "remove" | "box";
type View = "home" | "wardrobe" | "planner" | "add" | "settings" | "garment";
type FlowStage =
  | "idle"
  | "uploading"
  | "processing"
  | "segmentation-review"
  | "metadata-confirm"
  | "error";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:58000";

/** Segmentation at or above this confidence is accepted automatically; the
 * user only sees the mask editor when the model is genuinely unsure. */
const SEGMENTATION_AUTO_ACCEPT = 0.85;

const SEASONS = ["spring", "summer", "fall", "winter"] as const;

function getSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  return url && key ? createClient(url, key) : null;
}

export function UploadExperience() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");
  const [signedIn, setSignedIn] = useState(false);
  const [accessToken, setAccessToken] = useState("");
  const [authError, setAuthError] = useState("");
  const [notice, setNotice] = useState("");

  const [view, setView] = useState<View>("home");
  const [wardrobe, setWardrobe] = useState<GarmentCard[]>([]);
  const [wardrobeTotal, setWardrobeTotal] = useState(0);
  const [pendingDraft, setPendingDraft] = useState<InProgressGarment | null>(null);
  const [selectedGarmentId, setSelectedGarmentId] = useState("");

  const [plan, setPlan] = useState<OutfitPlan | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState("");

  const supabase = useMemo(() => getSupabase(), []);

  async function refreshWardrobe(token: string) {
    const response = await fetch(`${apiUrl}/api/v1/garments?sort=newest&page_size=8`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) return;
    const data = await response.json();
    setWardrobe(data.items);
    setWardrobeTotal(data.total);
  }

  async function refreshPendingDraft(token: string) {
    try {
      const response = await fetch(`${apiUrl}/api/v1/garments/in-progress`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const garment = await response.json();
        setPendingDraft(garment?.garment_id ? garment : null);
      }
    } catch {
      // Non-critical: the dashboard just won't offer to resume a draft.
    }
  }

  useEffect(() => {
    const client = supabase;
    if (!client) return;
    let active = true;
    const restoreSession = async () => {
      const { data } = await client.auth.getSession();
      if (!active || !data.session) return;
      const token = data.session.access_token;
      setAccessToken(token);
      setSignedIn(true);
      await Promise.all([refreshWardrobe(token), refreshPendingDraft(token)]);
    };
    restoreSession();
    const { data: listener } = client.auth.onAuthStateChange((_event, session) => {
      if (!active) return;
      setSignedIn(Boolean(session));
      setAccessToken(session?.access_token ?? "");
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, [supabase]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setAuthError("");
    setNotice("");
    if (!supabase) {
      setAuthError("Add your Supabase settings to .env.local to enable sign-in.");
      return;
    }
    const { error } =
      authMode === "signup"
        ? await supabase.auth.signUp({ email, password })
        : await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setAuthError(error.message);
      return;
    }
    const { data } = await supabase.auth.getSession();
    if (!data.session) {
      setNotice("Account created. Check your email to confirm it, then return here to sign in.");
      setAuthMode("signin");
      return;
    }
    const token = data.session.access_token;
    setAccessToken(token);
    setSignedIn(true);
    setView("home");
    await Promise.all([refreshWardrobe(token), refreshPendingDraft(token)]);
  }

  function navigate(next: View) {
    setView(next);
    if ((next === "home" || next === "wardrobe") && accessToken) {
      refreshWardrobe(accessToken);
    }
  }

  function openGarment(id: string) {
    setSelectedGarmentId(id);
    setView("garment");
  }

  async function discardPendingDraft() {
    if (!pendingDraft || !accessToken) return;
    try {
      await fetch(`${apiUrl}/api/v1/garments/${pendingDraft.garment_id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
    } catch {
      // Best effort — the draft will simply resurface next visit.
    }
    setPendingDraft(null);
  }

  async function generatePlan() {
    if (!accessToken) return;
    setPlanning(true);
    setPlanError("");
    try {
      const start = new Date();
      start.setDate(start.getDate() + 1);
      const settingsResponse = await fetch(`${apiUrl}/api/v1/settings`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const userSettings = settingsResponse.ok ? await settingsResponse.json() : null;
      const response = await fetch(`${apiUrl}/api/v1/plans/generate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          start_date: start.toISOString().slice(0, 10),
          days: 7,
          location: {
            latitude: userSettings?.latitude ?? 43.6532,
            longitude: userSettings?.longitude ?? -79.3832,
            timezone: userSettings?.timezone ?? "America/Toronto",
          },
          daily_requirements: [],
          locked_items: [],
          excluded_items: [],
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setPlanError(body?.detail?.message ?? body?.detail ?? "We couldn't build a complete week yet.");
        return;
      }
      setPlan(await response.json());
    } finally {
      setPlanning(false);
    }
  }

  if (!signedIn) {
    return (
      <AuthScreen
        email={email}
        password={password}
        authMode={authMode}
        error={authError}
        notice={notice}
        setEmail={setEmail}
        setPassword={setPassword}
        setAuthMode={setAuthMode}
        onSubmit={signIn}
      />
    );
  }

  if (view === "add") {
    return (
      <AddGarmentFlow
        token={accessToken}
        resumeGarmentId={pendingDraft?.garment_id}
        onExit={() => {
          setPendingDraft(null);
          navigate("home");
        }}
        onFinished={() => {
          setPendingDraft(null);
          navigate("wardrobe");
        }}
      />
    );
  }

  return (
    <>
      <AppNav active={view} onNavigate={navigate} onSettings={() => navigate("settings")} />
      {view === "wardrobe" && (
        <Wardrobe
          items={wardrobe}
          token={accessToken}
          onOpenDetail={openGarment}
        />
      )}
      {view === "planner" && (
        <PlannerHost
          plan={plan}
          planning={planning}
          planError={planError}
          token={accessToken}
          onGenerate={generatePlan}
        />
      )}
      {view === "settings" && <Settings token={accessToken} onBack={() => navigate("wardrobe")} />}
      {view === "garment" && (
        <GarmentDetailPage
          garmentId={selectedGarmentId}
          token={accessToken}
          onBack={() => navigate("wardrobe")}
          onRemoved={() => navigate("wardrobe")}
        />
      )}
      {view === "home" && (
        <Home
          wardrobeTotal={wardrobeTotal}
          recent={wardrobe}
          pendingDraft={pendingDraft}
          onResumeDraft={() => navigate("add")}
          onDiscardDraft={discardPendingDraft}
          onAdd={() => navigate("add")}
          onWardrobe={() => navigate("wardrobe")}
          onPlanner={() => navigate("planner")}
          onOpenGarment={openGarment}
        />
      )}
    </>
  );
}

/* --- Shared navigation ----------------------------------------------------- */

function AppNav({
  active,
  onNavigate,
  onSettings,
}: {
  active: View;
  onNavigate: (view: View) => void;
  onSettings: () => void;
}) {
  return (
    <nav className="nav" aria-label="Primary navigation">
      <button className="brand nav-link" onClick={() => onNavigate("home")} aria-label="PetDressed home">
        <span className="brand-mark" aria-hidden="true">P</span>
        <span>PetDressed</span>
      </button>
      <div className="nav-steps" aria-label="Sections">
        <button className={active === "home" ? "active" : ""} onClick={() => onNavigate("home")}>Home</button>
        <button className={active === "wardrobe" ? "active" : ""} onClick={() => onNavigate("wardrobe")}>Wardrobe</button>
        <button className={active === "planner" ? "active" : ""} onClick={() => onNavigate("planner")}>Planner</button>
        <button className={active === "add" ? "active" : ""} onClick={() => onNavigate("add")}>Add item</button>
      </div>
      <button className="round-button" aria-label="Open settings" onClick={onSettings}>⚙</button>
    </nav>
  );
}

/* --- Auth screen ------------------------------------------------------------ */

function AuthScreen({
  email,
  password,
  authMode,
  error,
  notice,
  setEmail,
  setPassword,
  setAuthMode,
  onSubmit,
}: {
  email: string;
  password: string;
  authMode: "signin" | "signup";
  error: string;
  notice: string;
  setEmail: (value: string) => void;
  setPassword: (value: string) => void;
  setAuthMode: (mode: "signin" | "signup") => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <main>
      <nav className="nav" aria-label="Primary navigation">
        <a className="brand" href="#" aria-label="PetDressed home">
          <span className="brand-mark" aria-hidden="true">P</span>
          <span>PetDressed</span>
        </a>
      </nav>

      <section className="hero">
        <ClothingRail className="hero-rail" />
        <div className="eyebrow"><span /> Welcome</div>
        <h1>Build your<br /><em>wardrobe.</em></h1>
        <p className="intro">
          One garment. One photo. Plain background. The machine cuts it out and
          guesses the details — you approve or override every single call.
        </p>

        <form className="auth-card" onSubmit={onSubmit}>
          <div>
            <span className="step-number">01</span>
            <h2>{authMode === "signin" ? "Access your wardrobe" : "Claim your wardrobe"}</h2>
            <p>Private by default — your photos never leave your account.</p>
          </div>
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <button className="primary" type="submit">{authMode === "signin" ? "Sign in" : "Create account"}</button>
          <button className="auth-switch" type="button" onClick={() => setAuthMode(authMode === "signin" ? "signup" : "signin")}>
            {authMode === "signin" ? "New here? Create account" : "Already have an account? Sign in"}
          </button>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        {notice && <p className="success" role="status">{notice}</p>}
      </section>

      <aside className="side-note" aria-label="Photography guidance">
        <span className="spark">✣</span>
        <p><strong>One piece at a time.</strong><br />Front-facing. Sharp. No exceptions.</p>
      </aside>
    </main>
  );
}

/* --- Home dashboard ---------------------------------------------------------- */

function Home({
  wardrobeTotal,
  recent,
  pendingDraft,
  onResumeDraft,
  onDiscardDraft,
  onAdd,
  onWardrobe,
  onPlanner,
  onOpenGarment,
}: {
  wardrobeTotal: number;
  recent: GarmentCard[];
  pendingDraft: InProgressGarment | null;
  onResumeDraft: () => void;
  onDiscardDraft: () => void;
  onAdd: () => void;
  onWardrobe: () => void;
  onPlanner: () => void;
  onOpenGarment: (id: string) => void;
}) {
  return (
    <main className="home-shell">
      <div className="home-greeting">
        <div className="eyebrow"><span /> Your wardrobe</div>
        <h1>Good to see<br /><em>you again.</em></h1>
        <p className="intro">Everything you own, one tap away.</p>
      </div>

      {pendingDraft && (
        <aside className="draft-banner">
          <div>
            <strong>You started adding a garment</strong>
            <span>Pick up where you left off, or discard it.</span>
          </div>
          <div className="draft-banner-actions">
            <button className="secondary" onClick={onDiscardDraft}>Discard</button>
            <button className="primary" onClick={onResumeDraft}>Resume</button>
          </div>
        </aside>
      )}

      <div className="quick-actions">
        <button className="quick-action" onClick={onAdd}>
          <span className="icon-badge" aria-hidden="true">+</span>
          <span>
            <strong>Add a garment</strong>
            <span>Snap a photo, we&rsquo;ll take it from there</span>
          </span>
        </button>
        <button className="quick-action" onClick={onWardrobe}>
          <span className="icon-badge" aria-hidden="true">▦</span>
          <span>
            <strong>View wardrobe</strong>
            <span>{wardrobeTotal} garment{wardrobeTotal === 1 ? "" : "s"} on file</span>
          </span>
        </button>
        <button className="quick-action" onClick={onPlanner}>
          <span className="icon-badge" aria-hidden="true">◷</span>
          <span>
            <strong>Plan the week</strong>
            <span>Weather-aware outfits, explained</span>
          </span>
        </button>
      </div>

      <div className="home-stats">
        <div className="home-stat">
          <strong>{wardrobeTotal}</strong>
          <span>Garments logged</span>
        </div>
        <div className="home-stat">
          <strong>{wardrobeTotal > 0 ? "Ready" : "Empty"}</strong>
          <span>Wardrobe status</span>
        </div>
      </div>

      {recent.length > 0 && (
        <div className="home-recent">
          <h2>Recently added</h2>
          <div className="recent-strip">
            {recent.map((item) => (
              <button key={item.garment_id} onClick={() => onOpenGarment(item.garment_id)} aria-label={`Open ${item.display_name}`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={item.original_url} alt={item.display_name} />
              </button>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}

/* --- Add-garment flow --------------------------------------------------------
 * A guided sequence that never traps the user: every step offers Cancel, and
 * cancelling with unsaved work prompts before discarding it server-side.
 * Segmentation is only shown for manual review when the model's confidence is
 * low; otherwise it's accepted automatically and the user never sees it. */

function AddGarmentFlow({
  token,
  resumeGarmentId,
  onExit,
  onFinished,
}: {
  token: string;
  resumeGarmentId?: string;
  onExit: () => void;
  onFinished: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<FlowStage>(resumeGarmentId ? "processing" : "idle");
  const [garmentId, setGarmentId] = useState(resumeGarmentId ?? "");
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [pollCycle, setPollCycle] = useState(0);
  const [segmentation, setSegmentation] = useState<SegmentationResult | null>(null);
  const [metadata, setMetadata] = useState<MetadataResult | null>(null);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);
  const dirty = Boolean(file || garmentId);

  function acceptFile(next: File | undefined) {
    setError("");
    if (!next) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(next.type)) {
      setError("Choose a JPEG, PNG, or WebP image.");
      return;
    }
    if (next.size > 15 * 1024 * 1024) {
      setError("That image is larger than 15 MB.");
      return;
    }
    setFile(next);
  }

  async function discardAndExit() {
    if (dirty && !window.confirm("Discard this garment and start over? This can't be undone.")) {
      return;
    }
    if (garmentId) {
      try {
        await fetch(`${apiUrl}/api/v1/garments/${garmentId}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {
        // Best effort — the draft will simply resurface as resumable.
      }
    }
    onExit();
  }

  async function upload() {
    if (!file) return;
    setStage("uploading");
    setError("");
    try {
      const sessionResponse = await fetch(`${apiUrl}/api/v1/garments/uploads`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          content_type: file.type,
          file_size_bytes: file.size,
        }),
      });
      if (!sessionResponse.ok) throw new Error("Could not prepare the upload.");
      const session = await sessionResponse.json();
      setGarmentId(session.garment_id);
      const form = new FormData();
      Object.entries(session.upload_fields as Record<string, string>).forEach(([key, value]) =>
        form.append(key, value),
      );
      form.append("file", file);
      const objectResponse = await fetch(session.upload_url, { method: "POST", body: form });
      if (!objectResponse.ok) throw new Error("The image upload did not finish.");
      const confirmResponse = await fetch(
        `${apiUrl}/api/v1/garments/${session.garment_id}/uploads/complete`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ object_key: session.object_key }),
        },
      );
      if (!confirmResponse.ok) throw new Error("Could not confirm the upload.");
      setStage("processing");
    } catch (caught) {
      setStage("error");
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    }
  }

  useEffect(() => {
    if (stage !== "processing" || !garmentId) return;
    const timer = window.setInterval(async () => {
      try {
        const statusResponse = await fetch(`${apiUrl}/api/v1/garments/${garmentId}/status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!statusResponse.ok) return;
        const current = await statusResponse.json();
        if (current.processing_status === "segmentation_review") {
          window.clearInterval(timer);
          const resultResponse = await fetch(
            `${apiUrl}/api/v1/garments/${garmentId}/segmentation`,
            { headers: { Authorization: `Bearer ${token}` } },
          );
          if (!resultResponse.ok) return;
          const result: SegmentationResult = await resultResponse.json();
          if (result.confidence >= SEGMENTATION_AUTO_ACCEPT) {
            const acceptResponse = await fetch(
              `${apiUrl}/api/v1/garments/${garmentId}/segmentation/accept`,
              { method: "POST", headers: { Authorization: `Bearer ${token}` } },
            );
            if (acceptResponse.ok) {
              setPollCycle((value) => value + 1);
            } else {
              setSegmentation(result);
              setStage("segmentation-review");
            }
          } else {
            setSegmentation(result);
            setStage("segmentation-review");
          }
        } else if (current.processing_status === "metadata_review") {
          window.clearInterval(timer);
          const resultResponse = await fetch(
            `${apiUrl}/api/v1/garments/${garmentId}/metadata`,
            { headers: { Authorization: `Bearer ${token}` } },
          );
          if (resultResponse.ok) {
            setMetadata(await resultResponse.json());
            setStage("metadata-confirm");
          }
        } else if (current.processing_status === "failed") {
          window.clearInterval(timer);
          setError(current.error ?? "Something went wrong while processing this garment.");
          setStage("error");
        }
      } catch {
        setError("Temporarily unable to reach the processing service. Retrying…");
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [garmentId, pollCycle, stage, token]);

  async function confirmMetadata(payload: MetadataConfirmPayload) {
    const response = await fetch(`${apiUrl}/api/v1/garments/${garmentId}/metadata/confirm`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("We couldn't save those details. Please try again.");
    onFinished();
  }

  if (stage === "idle" || stage === "uploading") {
    return (
      <UploadStep
        file={file}
        preview={preview}
        dragging={dragging}
        error={error}
        uploading={stage === "uploading"}
        onDragOver={(event: DragEvent) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event: DragEvent) => {
          event.preventDefault();
          setDragging(false);
          acceptFile(event.dataTransfer.files[0]);
        }}
        onFileChange={(event: ChangeEvent<HTMLInputElement>) => acceptFile(event.target.files?.[0])}
        onCancel={discardAndExit}
        onUpload={upload}
      />
    );
  }

  if (stage === "processing") {
    return <ProcessingStep onCancel={discardAndExit} />;
  }

  if (stage === "segmentation-review" && segmentation) {
    return (
      <SegmentationReview
        result={segmentation}
        token={token}
        onCancel={discardAndExit}
        onAccepted={() => {
          setSegmentation(null);
          setStage("processing");
          setPollCycle((value) => value + 1);
        }}
        onRetry={() => {
          setSegmentation(null);
          setStage("processing");
          setPollCycle((value) => value + 1);
        }}
      />
    );
  }

  if (stage === "metadata-confirm" && metadata) {
    return <QuickMetadataConfirm result={metadata} onConfirm={confirmMetadata} onCancel={discardAndExit} />;
  }

  if (stage === "error") {
    return (
      <ErrorStep
        message={error}
        onRetry={() => {
          setStage("processing");
          setPollCycle((value) => value + 1);
        }}
        onCancel={discardAndExit}
      />
    );
  }

  return null;
}

function FlowNav({ label, onCancel }: { label: string; onCancel: () => void }) {
  return (
    <nav className="nav" aria-label="Primary navigation">
      <button className="brand nav-link" onClick={onCancel} aria-label="Cancel and return home">
        <span className="brand-mark" aria-hidden="true">P</span>
        <span>PetDressed</span>
      </button>
      <div className="nav-steps"><button className="active" disabled>{label}</button></div>
      <button className="round-button" aria-label="Cancel and return home" onClick={onCancel}>✕</button>
    </nav>
  );
}

function UploadStep({
  file,
  preview,
  dragging,
  error,
  uploading,
  onDragOver,
  onDragLeave,
  onDrop,
  onFileChange,
  onCancel,
  onUpload,
}: {
  file: File | null;
  preview: string;
  dragging: boolean;
  error: string;
  uploading: boolean;
  onDragOver: (event: DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (event: DragEvent) => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onCancel: () => void;
  onUpload: () => void;
}) {
  return (
    <main>
      <FlowNav label="Add item" onCancel={onCancel} />
      <section className="hero">
        <ClothingRail className="hero-rail" />
        <div className="eyebrow"><span /> Add a garment</div>
        <h1>One photo.<br /><em>That&rsquo;s it.</em></h1>
        <p className="intro">
          Plain background, whole piece in frame. We&rsquo;ll cut it out and fill in
          the details automatically — you can fix anything after.
        </p>

        <section className="upload-card">
          <div className="upload-heading">
            <div><span className="step-number">1</span><h2>Add the photo</h2></div>
            <span className="private-note">Private</span>
          </div>

          <div
            className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          >
            {file ? (
              <>
                <Image src={preview} alt={`Preview of ${file.name}`} width={180} height={190} unoptimized />
                <div>
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1024 / 1024).toFixed(1)} MB · Ready</span>
                </div>
              </>
            ) : (
              <>
                <HangingGarment className="hanger" />
                <strong>Drop the photo here</strong>
                <span>or pull one from your device</span>
              </>
            )}
            <label className="file-button">
              {file ? "Choose another" : "Choose photo"}
              <input type="file" accept="image/jpeg,image/png,image/webp" onChange={onFileChange} />
            </label>
          </div>

          <div className="tips">
            <strong>For best results</strong>
            <span>Lay it flat, show the whole piece, use a background that contrasts.</span>
          </div>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="primary full" disabled={!file || uploading} onClick={onUpload}>
            {uploading ? "Uploading…" : "Continue →"}
          </button>
          <button className="secondary full" type="button" onClick={onCancel}>Cancel</button>
        </section>
      </section>
    </main>
  );
}

function ProcessingStep({ onCancel }: { onCancel: () => void }) {
  return (
    <main>
      <FlowNav label="Preparing" onCancel={onCancel} />
      <section className="hero">
        <div className="eyebrow"><span /> Working</div>
        <h1>Tidying up<br /><em>your photo.</em></h1>
        <div className="success" role="status">
          <strong>Almost there.</strong>
          <span className="processing-line"><i /> Removing the background and identifying the piece…</span>
        </div>
        <button className="secondary full" onClick={onCancel}>Cancel</button>
      </section>
    </main>
  );
}

function ErrorStep({
  message,
  onRetry,
  onCancel,
}: {
  message: string;
  onRetry: () => void;
  onCancel: () => void;
}) {
  return (
    <main>
      <FlowNav label="Trouble" onCancel={onCancel} />
      <section className="hero">
        <div className="eyebrow"><span /> Trouble ahead</div>
        <h1>That didn&rsquo;t<br /><em>quite work.</em></h1>
        <p className="error" role="alert">{message}</p>
        <button className="primary full" onClick={onRetry}>Try again</button>
        <button className="secondary full" onClick={onCancel}>Cancel</button>
      </section>
    </main>
  );
}

function SegmentationReview({
  result,
  token,
  onRetry,
  onAccepted,
  onCancel,
}: {
  result: SegmentationResult;
  token: string;
  onRetry: () => void;
  onAccepted: () => void;
  onCancel: () => void;
}) {
  const imageRef = useRef<HTMLImageElement>(null);
  const [tool, setTool] = useState<Tool>("keep");
  const [points, setPoints] = useState<Array<{ x: number; y: number; value: 0 | 1 }>>([]);
  const [brush, setBrush] = useState<Array<{ x: number; y: number; radius: number; value: 0 | 1 }>>([]);
  const [busy, setBusy] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [boxStart, setBoxStart] = useState<{ x: number; y: number } | null>(null);
  const [box, setBox] = useState<SegmentationResult["bbox"] | null>(null);
  const [imageSize, setImageSize] = useState({ width: 1, height: 1 });

  function coordinates(event: PointerEvent<HTMLDivElement>) {
    const image = imageRef.current;
    if (!image) return null;
    const rect = image.getBoundingClientRect();
    return {
      x: Math.round(((event.clientX - rect.left) / rect.width) * image.naturalWidth),
      y: Math.round(((event.clientY - rect.top) / rect.height) * image.naturalHeight),
    };
  }

  function pointerDown(event: PointerEvent<HTMLDivElement>) {
    const point = coordinates(event);
    if (!point) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    if (tool === "box") setBoxStart(point);
    else setBrush((current) => [...current, { ...point, radius: 18, value: tool === "keep" ? 1 : 0 }]);
  }

  function pointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!(event.buttons & 1) || tool === "box") return;
    const point = coordinates(event);
    if (point) setBrush((current) => [...current, { ...point, radius: 18, value: tool === "keep" ? 1 : 0 }]);
  }

  function pointerUp(event: PointerEvent<HTMLDivElement>) {
    const point = coordinates(event);
    if (!point) return;
    if (tool === "box" && boxStart) {
      setBox({
        x_min: Math.min(boxStart.x, point.x),
        y_min: Math.min(boxStart.y, point.y),
        x_max: Math.max(boxStart.x, point.x),
        y_max: Math.max(boxStart.y, point.y),
      });
      setBoxStart(null);
    } else if (tool !== "box") {
      setPoints((current) => [...current, { ...point, value: tool === "keep" ? 1 : 0 }]);
    }
  }

  async function retry() {
    setBusy(true);
    const response = await fetch(
      `${apiUrl}/api/v1/garments/${result.garment_id}/segmentation/retry`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          positive_points: points.filter((point) => point.value).map(({ x, y }) => ({ x, y })),
          negative_points: points.filter((point) => !point.value).map(({ x, y }) => ({ x, y })),
          bbox: box,
          brush_strokes: brush,
          mask_runs: [],
        }),
      },
    );
    setBusy(false);
    if (response.ok) onRetry();
  }

  async function accept() {
    setBusy(true);
    const response = await fetch(
      `${apiUrl}/api/v1/garments/${result.garment_id}/segmentation/accept`,
      { method: "POST", headers: { Authorization: `Bearer ${token}` } },
    );
    setBusy(false);
    if (response.ok) onAccepted();
  }

  return (
    <main>
      <FlowNav label="Quick check" onCancel={onCancel} />
      <section className="review-shell">
        <div className="review-copy">
          <div className="eyebrow"><span /> A quick check</div>
          <h1>Check the<br /><em>cut.</em></h1>
          <p className="intro">
            We weren&rsquo;t fully confident here, so give it a look. Brush back
            anything the machine ate, or scrub out any background that
            survived.
          </p>
          <div className="toolbox" aria-label="Mask correction tools">
            <button className={tool === "keep" ? "selected" : ""} onClick={() => setTool("keep")}>＋ Keep</button>
            <button className={tool === "remove" ? "selected" : ""} onClick={() => setTool("remove")}>− Remove</button>
            <button className={tool === "box" ? "selected" : ""} onClick={() => setTool("box")}>□ Box</button>
          </div>
          <p className="model-note">
            {Math.round(result.confidence * 100)}% confidence · {result.model_name} {result.model_version}
          </p>
        </div>
        <div className="review-card">
          <div className="preview-toolbar">
            <strong>Cutout</strong>
            <button onClick={() => setShowOriginal((value) => !value)}>
              {showOriginal ? "Show result" : "Show original"}
            </button>
          </div>
          <div
            className={`mask-editor tool-${tool}`}
            onPointerDown={pointerDown}
            onPointerMove={pointerMove}
            onPointerUp={pointerUp}
          >
            {/* Presigned object URLs are intentionally rendered without an optimization proxy. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              ref={imageRef}
              src={showOriginal ? result.preview_url : result.processed_url}
              alt="Garment segmentation preview"
              draggable={false}
              onLoad={(event) =>
                setImageSize({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                })
              }
            />
            {points.map((point, index) => (
              <i
                key={`${point.x}-${point.y}-${index}`}
                className={point.value ? "point keep" : "point remove"}
                style={{
                  left: `${(point.x / imageSize.width) * 100}%`,
                  top: `${(point.y / imageSize.height) * 100}%`,
                }}
              />
            ))}
          </div>
          <div className="review-actions">
            <button className="secondary" disabled={busy} onClick={onCancel}>
              Scrap it
            </button>
            <button className="secondary" disabled={busy} onClick={retry}>
              {busy ? "Working…" : points.length || brush.length || box ? "Apply fixes" : "Run again"}
            </button>
            <button className="primary" disabled={busy} onClick={accept}>Ship it →</button>
          </div>
        </div>
      </section>
    </main>
  );
}

function QuickMetadataConfirm({
  result,
  onConfirm,
  onCancel,
}: {
  result: MetadataResult;
  onConfirm: (payload: MetadataConfirmPayload) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(result.display_name ?? "");
  const [category, setCategory] = useState(result.predicted_category);
  const [subcategory, setSubcategory] = useState(result.subcategory ?? "");
  const [pattern, setPattern] = useState(result.pattern);
  const [plannerEnabled, setPlannerEnabled] = useState(
    !result.degraded && result.category_confidence >= 0.45,
  );
  const [seasons, setSeasons] = useState<Record<(typeof SEASONS)[number], boolean>>(() => {
    const initial = {} as Record<(typeof SEASONS)[number], boolean>;
    SEASONS.forEach((season) => {
      initial[season] = (result.seasons[season] ?? 0) >= 3;
    });
    return initial;
  });
  const [formality, setFormality] = useState(result.formality);
  const [warmth, setWarmth] = useState(result.warmth);
  const [breathability, setBreathability] = useState(result.breathability);
  const [waterResistance, setWaterResistance] = useState(result.water_resistance);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (plannerEnabled && !subcategory.trim()) {
      setError("Add a garment type before including this piece in outfit planning.");
      return;
    }
    setBusy(true);
    setError("");
    const seasonScores = SEASONS.reduce((acc, season) => {
      acc[season] = seasons[season] ? 5 : 0;
      return acc;
    }, {} as SeasonScores);
    try {
      await onConfirm({
        display_name: name || "Unnamed garment",
        category,
        subcategory: subcategory || null,
        formality,
        warmth,
        breathability,
        water_resistance: waterResistance,
        pattern,
        planner_enabled: plannerEnabled,
        seasons: seasonScores,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We couldn't save those details. Please try again.");
      setBusy(false);
    }
  }

  return (
    <main>
      <FlowNav label="Name it" onCancel={onCancel} />
      <section className="metadata-shell">
        <div className="metadata-image">
          <GarmentIcon name={iconForCategory(category)} className="photo-ghost" />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={result.processed_url} alt="Isolated garment" />
          <div className="palette" aria-label="Detected colours">
            {result.colors.map((color) => (
              <span key={color.hex} style={{ background: color.hex }} title={color.hex} />
            ))}
          </div>
        </div>
        <form className="metadata-form" onSubmit={submit}>
          <div className="eyebrow"><span /> Last step</div>
          <h1>Does this<br /><em>look right?</em></h1>
          {result.degraded ? (
            <p className="error" role="alert">
              We couldn&rsquo;t automatically identify this piece. Fill in the category and type below.
            </p>
          ) : (
            <p className="confidence-note">
              Matched with {Math.round(result.category_confidence * 100)}% confidence — change anything that&rsquo;s off.
            </p>
          )}
          <div className="form-grid">
            <label className="wide">
              Garment name
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Navy everyday shirt" required />
            </label>
            <label>
              Category
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {["top", "bottom", "one_piece", "outerwear", "shoes", "accessory"].map((value) => (
                  <option key={value} value={value}>{value.replace("_", " ")}</option>
                ))}
              </select>
            </label>
            <label>
              Type
              <input value={subcategory} onChange={(e) => setSubcategory(e.target.value)} placeholder="e.g. T-shirt" />
            </label>
            <label>
              Pattern
              <select value={pattern} onChange={(e) => setPattern(e.target.value)}>
                {["solid", "striped", "checked", "graphic", "floral", "abstract", "textured", "other", "unknown"].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label className="planner-toggle">
              <input type="checkbox" checked={plannerEnabled} onChange={(e) => setPlannerEnabled(e.target.checked)} />
              Include in outfit planning
            </label>
            <div className="wide">
              <span className="field-label">Seasons</span>
              <div className="season-chips">
                {SEASONS.map((season) => (
                  <label key={season} className={`season-chip ${seasons[season] ? "checked" : ""}`}>
                    <input
                      type="checkbox"
                      checked={seasons[season]}
                      onChange={(e) => setSeasons({ ...seasons, [season]: e.target.checked })}
                    />
                    {season[0].toUpperCase() + season.slice(1)}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <details className="advanced-disclosure">
            <summary>Fine-tune planning details (optional)</summary>
            <div className="season-grid">
              <AttributeSlider label="Formality" value={formality} setValue={setFormality} low="Relaxed" high="Formal" />
              <AttributeSlider label="Warmth" value={warmth} setValue={setWarmth} low="Light" high="Toasty" />
              <AttributeSlider label="Breathability" value={breathability} setValue={setBreathability} low="Low" high="Airy" />
              <AttributeSlider label="Water resistance" value={waterResistance} setValue={setWaterResistance} low="None" high="Rain-ready" />
            </div>
          </details>

          {error && <p className="error" role="alert">{error}</p>}
          <button className="primary full" disabled={busy}>{busy ? "Saving…" : "Add to wardrobe →"}</button>
          <button className="secondary full" type="button" onClick={onCancel}>Cancel</button>
        </form>
      </section>
    </main>
  );
}

function AttributeSlider({ label, value, setValue, low, high }: { label: string; value: number; setValue: (value: number) => void; low: string; high: string }) {
  return (
    <label className="slider-field">
      <span>{label}<strong>{value}</strong></span>
      <input type="range" min="0" max="5" value={value} onChange={(event) => setValue(Number(event.target.value))} />
      <small><span>{low}</span><span>{high}</span></small>
    </label>
  );
}

/* --- Wardrobe ----------------------------------------------------------------- */

function Wardrobe({
  items,
  token,
  onOpenDetail,
}: {
  items: GarmentCard[];
  token: string;
  onOpenDetail: (id: string) => void;
}) {
  const [garments, setGarments] = useState(items);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [season, setSeason] = useState("all");
  const [wardrobeError, setWardrobeError] = useState("");

  async function updateAvailability(item: GarmentCard, availability: string) {
    const response = await fetch(`${apiUrl}/api/v1/garments/${item.garment_id}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ availability }),
    });
    if (response.ok) {
      const updated = await response.json();
      setGarments((current) => current.map((garment) => garment.garment_id === updated.garment_id ? updated : garment));
    }
  }

  const shown = garments.filter(
    (item) =>
      (category === "all" || item.category === category) &&
      item.display_name.toLowerCase().includes(query.toLowerCase()),
  );

  async function changeSeason(next: string) {
    setSeason(next);
    const seasonQuery = next === "all" ? "" : `?season=${next}`;
    const response = await fetch(`${apiUrl}/api/v1/garments${seasonQuery}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) setGarments((await response.json()).items);
  }

  async function markWorn(item: GarmentCard) {
    const response = await fetch(`${apiUrl}/api/v1/garments/${item.garment_id}/worn`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      const updated = await response.json();
      setGarments((current) => current.map((garment) => garment.garment_id === updated.garment_id ? updated : garment));
    }
  }

  async function removeGarment(item: GarmentCard) {
    if (!window.confirm(`Remove ${item.display_name} and its photos?`)) return;
    setWardrobeError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/garments/${item.garment_id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error(`Delete failed with status ${response.status}`);
      setGarments((current) => current.filter((garment) => garment.garment_id !== item.garment_id));
    } catch {
      setWardrobeError("We couldn't remove that piece. Check the API connection and try again.");
    }
  }

  return (
    <main className="wardrobe-page">
      <section className="wardrobe-header">
        <div><div className="eyebrow"><span /> Your collection</div><h1>A wardrobe that<br /><em>works together.</em></h1></div>
      </section>
      <section className="wardrobe-controls">
        <label className="search-field"><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try “navy shirt”" /></label>
        <div className="category-pills">
          {["all", "top", "bottom", "one_piece", "outerwear", "shoes", "accessory"].map((value) => (
            <button key={value} className={category === value ? "selected" : ""} onClick={() => setCategory(value)}>
              {value !== "all" && <GarmentIcon name={iconForCategory(value)} className="pill-icon" />}
              {value.replace("_", " ")}
            </button>
          ))}
        </div>
        <label className="season-filter">
          Season
          <select value={season} onChange={(event) => changeSeason(event.target.value)}>
            <option value="all">All year</option>
            <option value="spring">Spring</option><option value="summer">Summer</option>
            <option value="fall">Fall</option><option value="winter">Winter</option>
          </select>
        </label>
      </section>
      {wardrobeError && <p className="error" role="alert">{wardrobeError}</p>}
      {shown.length ? (
        <section className="garment-grid" aria-label={`${shown.length} wardrobe items`}>
          {shown.map((item) => (
            <article className="garment-card" key={item.garment_id}>
              <div className="garment-photo">
                {/* Silhouette sits behind the photo so a slow or broken image
                    still reads as the right kind of garment. */}
                <GarmentIcon name={iconForCategory(item.category)} className="photo-ghost" />
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img className="photo-original" src={item.original_url} alt={item.display_name} />
                {item.availability !== "available" && <span className="state-badge">{item.availability}</span>}
              </div>
              <div className="garment-details">
                <div><h2>{item.display_name}</h2><p>{item.subcategory ?? item.category}</p></div>
                <div className="mini-palette">{item.colors.slice(0, 3).map((color) => <i key={color.hex} style={{ background: color.hex }} />)}</div>
              </div>
              <select aria-label={`Availability for ${item.display_name}`} value={item.availability} onChange={(event) => updateAvailability(item, event.target.value)}>
                <option value="available">Available</option><option value="laundry">In laundry</option><option value="unavailable">Unavailable</option><option value="packed">Packed</option>
              </select>
              <div className="card-actions">
                <button onClick={() => markWorn(item)}>Wore today</button>
                <button onClick={() => onOpenDetail(item.garment_id)}>Details</button>
                <button onClick={() => removeGarment(item)}>Remove</button>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <div className="empty-state">
          <ClothingRail className="empty-rail" count={4} />
          <strong>Nothing matches.</strong>
          <span>Drop a filter or add a garment.</span>
        </div>
      )}
    </main>
  );
}

/* --- Garment detail (advanced settings live here, not at creation) ----------- */

function GarmentDetailPage({
  garmentId,
  token,
  onBack,
  onRemoved,
}: {
  garmentId: string;
  token: string;
  onBack: () => void;
  onRemoved: () => void;
}) {
  const [detail, setDetail] = useState<GarmentDetail | null>(null);
  const [name, setName] = useState("");
  const [subcategory, setSubcategory] = useState("");
  const [pattern, setPattern] = useState("solid");
  const [plannerEnabled, setPlannerEnabled] = useState(false);
  const [formality, setFormality] = useState(0);
  const [warmth, setWarmth] = useState(0);
  const [breathability, setBreathability] = useState(0);
  const [waterResistance, setWaterResistance] = useState(0);
  const [seasons, setSeasons] = useState<SeasonScores>({ spring: 0, summer: 0, fall: 0, winter: 0 });
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch(`${apiUrl}/api/v1/garments/${garmentId}/detail`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => {
        if (!response.ok) throw new Error("Could not load this garment.");
        return response.json();
      })
      .then((data: GarmentDetail) => {
        if (!active) return;
        setDetail(data);
        setName(data.display_name);
        setSubcategory(data.subcategory ?? "");
        setPattern(data.pattern ?? "solid");
        setPlannerEnabled(data.planner_enabled);
        setFormality(data.formality);
        setWarmth(data.warmth);
        setBreathability(data.breathability);
        setWaterResistance(data.water_resistance);
        setSeasons(data.seasons);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Could not load this garment."));
    return () => {
      active = false;
    };
  }, [garmentId, token]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSaved(false);
    const payload: GarmentUpdatePayload = {
      display_name: name,
      subcategory: subcategory || null,
      pattern,
      planner_enabled: plannerEnabled,
      formality,
      warmth,
      breathability,
      water_resistance: waterResistance,
      seasons,
    };
    const response = await fetch(`${apiUrl}/api/v1/garments/${garmentId}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setBusy(false);
    if (response.ok) setSaved(true);
    else setError("We couldn't save those changes. Please try again.");
  }

  async function remove() {
    if (!detail || !window.confirm(`Remove ${detail.display_name} and its photos?`)) return;
    const response = await fetch(`${apiUrl}/api/v1/garments/${garmentId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) onRemoved();
    else setError("We couldn't remove that piece. Try again.");
  }

  if (!detail) {
    return (
      <main className="detail-shell">
        <div className="empty-state">
          {error ? <p className="error" role="alert">{error}</p> : <span>Loading…</span>}
          <button className="secondary" onClick={onBack}>← Wardrobe</button>
        </div>
      </main>
    );
  }

  return (
    <main className="detail-shell">
      <div className="detail-image">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={detail.original_url} alt={detail.display_name} />
      </div>
      <form onSubmit={save}>
        <button className="back-link" type="button" onClick={onBack}>← Wardrobe</button>
        <div className="eyebrow"><span /> Garment details</div>
        <h1>{detail.display_name}</h1>
        <div className="form-grid">
          <label className="wide">
            Garment name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Category
            <input value={detail.category.replace("_", " ")} disabled />
          </label>
          <label>
            Type
            <input value={subcategory} onChange={(e) => setSubcategory(e.target.value)} />
          </label>
          <label>
            Pattern
            <select value={pattern} onChange={(e) => setPattern(e.target.value)}>
              {["solid", "striped", "checked", "graphic", "floral", "abstract", "textured", "other", "unknown"].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="planner-toggle">
            <input type="checkbox" checked={plannerEnabled} onChange={(e) => setPlannerEnabled(e.target.checked)} />
            Include in outfit planning
          </label>
        </div>

        <details className="advanced-disclosure">
          <summary>Advanced planning details</summary>
          <div className="season-grid">
            <AttributeSlider label="Formality" value={formality} setValue={setFormality} low="Relaxed" high="Formal" />
            <AttributeSlider label="Warmth" value={warmth} setValue={setWarmth} low="Light" high="Toasty" />
            <AttributeSlider label="Breathability" value={breathability} setValue={setBreathability} low="Low" high="Airy" />
            <AttributeSlider label="Water resistance" value={waterResistance} setValue={setWaterResistance} low="None" high="Rain-ready" />
            {SEASONS.map((season) => (
              <AttributeSlider
                key={season}
                label={season[0].toUpperCase() + season.slice(1)}
                value={seasons[season]}
                setValue={(next) => setSeasons({ ...seasons, [season]: next })}
                low="Skip"
                high="Ideal"
              />
            ))}
          </div>
        </details>

        {error && <p className="error" role="alert">{error}</p>}
        <div className="detail-actions">
          <button className="primary" disabled={busy}>{busy ? "Saving…" : saved ? "Saved ✓" : "Save changes"}</button>
          <button className="secondary" type="button" onClick={remove}>Remove garment</button>
        </div>
      </form>
    </main>
  );
}

/* --- Settings ------------------------------------------------------------------ */

interface SettingsValue {
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

function Settings({ token, onBack }: { token: string; onBack: () => void }) {
  const [value, setValue] = useState<SettingsValue | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch(`${apiUrl}/api/v1/settings`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => response.json())
      .then(setValue);
  }, [token]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!value) return;
    const response = await fetch(`${apiUrl}/api/v1/settings`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(value),
    });
    if (response.ok) {
      setValue(await response.json());
      setSaved(true);
    }
  }

  if (!value) return <main><div className="empty-state">Loading settings…</div></main>;
  return (
    <main>
      <form className="settings-panel" onSubmit={save}>
        <button className="back-link" type="button" onClick={onBack}>← Wardrobe</button>
        <div className="eyebrow"><span /> Make it yours</div>
        <h1>Set the<br /><em>constraints.</em></h1>
        <p className="intro">Your approximate location feeds the forecast. Nothing else uses it.</p>
        <div className="form-grid">
          <label>City<input value={value.city ?? ""} onChange={(event) => setValue({ ...value, city: event.target.value || null })} placeholder="Toronto" /></label>
          <label>Timezone<input value={value.timezone} onChange={(event) => setValue({ ...value, timezone: event.target.value })} /></label>
          <label>Approx. latitude<input type="number" step=".01" value={value.latitude ?? ""} onChange={(event) => setValue({ ...value, latitude: event.target.value ? Number(event.target.value) : null })} /></label>
          <label>Approx. longitude<input type="number" step=".01" value={value.longitude ?? ""} onChange={(event) => setValue({ ...value, longitude: event.target.value ? Number(event.target.value) : null })} /></label>
          <label>Leave home<input type="number" min="0" max="23" value={value.active_start_hour} onChange={(event) => setValue({ ...value, active_start_hour: Number(event.target.value) })} /></label>
          <label>Return home<input type="number" min="0" max="23" value={value.active_end_hour} onChange={(event) => setValue({ ...value, active_end_hour: Number(event.target.value) })} /></label>
          <AttributeSlider label="Repetition tolerance" value={value.repetition_tolerance} setValue={(next) => setValue({ ...value, repetition_tolerance: next })} low="Varied" high="Repeat" />
          <AttributeSlider label="Preferred formality" value={value.preferred_formality} setValue={(next) => setValue({ ...value, preferred_formality: next })} low="Relaxed" high="Formal" />
          <AttributeSlider label="Weather strictness" value={value.weather_strictness} setValue={(next) => setValue({ ...value, weather_strictness: next })} low="Flexible" high="Strict" />
          <label className="planner-toggle"><input type="checkbox" checked={value.accessory_usage} onChange={(event) => setValue({ ...value, accessory_usage: event.target.checked })} /> Include accessories in plans</label>
        </div>
        <button className="primary full">{saved ? "Saved ✓" : "Save preferences"}</button>
      </form>
    </main>
  );
}

/* --- Planner --------------------------------------------------------------------- */

function PlannerHost({
  plan,
  planning,
  planError,
  token,
  onGenerate,
}: {
  plan: OutfitPlan | null;
  planning: boolean;
  planError: string;
  token: string;
  onGenerate: () => void;
}) {
  if (planning) {
    return (
      <main className="hero">
        <div className="eyebrow"><span /> Solving</div>
        <h1>Building your<br /><em>week.</em></h1>
        <div className="success" role="status">
          <strong>Crunching the details…</strong>
          <span className="processing-line"><i /> Matching weather, rotation, and your rules…</span>
        </div>
      </main>
    );
  }

  if (!plan) {
    return (
      <main className="hero">
        <div className="eyebrow"><span /> Outfit planner</div>
        <h1>Plan your<br /><em>week.</em></h1>
        <p className="intro">
          We&rsquo;ll pick a full outfit for each day based on the weather and
          what you actually have available to wear.
        </p>
        {planError && <p className="error" role="alert">{planError}</p>}
        <button className="primary full" onClick={onGenerate}>Plan the week →</button>
      </main>
    );
  }

  return <Planner initialPlan={plan} token={token} />;
}

function Planner({ initialPlan, token }: { initialPlan: OutfitPlan; token: string }) {
  const [plan, setPlan] = useState(initialPlan);
  const [busyDay, setBusyDay] = useState("");
  const [selectedDay, setSelectedDay] = useState(initialPlan.days[0]?.date ?? "");

  async function update(path: string, body?: object) {
    setBusyDay(path);
    const response = await fetch(`${apiUrl}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    setBusyDay("");
    if (response.ok) setPlan(await response.json());
  }

  const active = plan.days.find((day) => day.date === selectedDay) ?? plan.days[0];
  return (
    <main className="planner-page">
      <section className="planner-header">
        <div>
          <div className="eyebrow"><span /> Solved</div>
          <h1>Seven days.<br /><em>Zero guesswork.</em></h1>
        </div>
        <div className="plan-health">
          <strong>{plan.status === "optimal" ? "Optimal" : "Feasible"}</strong>
          <span>{plan.solve_time_ms} ms · {plan.relaxed_constraints.length ? `${plan.relaxed_constraints.join(", ")} relaxed` : "all constraints met"}</span>
        </div>
      </section>
      <section className="week-strip" aria-label="Weekly outfits">
        {plan.days.map((day) => {
          const dateValue = new Date(`${day.date}T12:00:00`);
          return (
            <button key={day.date} className={selectedDay === day.date ? "selected" : ""} onClick={() => setSelectedDay(day.date)}>
              <span>{dateValue.toLocaleDateString("en-CA", { weekday: "short" })}</span>
              <strong>{dateValue.getDate()}</strong>
              <small>{typeof day.weather.planning_temp_c === "number" ? `${Math.round(day.weather.planning_temp_c)}°` : "—"}</small>
              {day.is_locked && <i>●</i>}
            </button>
          );
        })}
      </section>
      {active && (
        <section className="day-plan">
          <div className="outfit-stage">
            <div className="weather-badge">
              <strong>{typeof active.weather.planning_temp_c === "number" ? `${Math.round(active.weather.planning_temp_c)}°C` : "Forecast unavailable"}</strong>
              <span>{active.provisional_weather ? "Provisional forecast" : `${active.weather.precipitation_probability ?? 0}% rain`}</span>
            </div>
            {/* The mannequin answers "what does this outfit look like"; the row
                below answers "which of my things is that". Neither does both
                well, so the day shows both. */}
            <Mannequin garments={active.garments} className="outfit-figure" />
            <div className="outfit-pieces">
              {active.garments.map((garment) => (
                <article key={garment.garment_id}>
                  <div className="piece-frame">
                    <GarmentIcon name={iconForCategory(garment.category)} className="photo-ghost" />
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      className="photo-original"
                      src={garment.original_url}
                      alt={garment.display_name}
                    />
                  </div>
                  <strong>{garment.display_name}</strong>
                  <span>{garment.category.replace("_", " ")}</span>
                  <button
                    aria-label={`Replace ${garment.display_name}`}
                    disabled={Boolean(busyDay) || active.is_locked}
                    onClick={() => update(`/api/v1/plans/${plan.plan_id}/days/${active.date}/replace`, {
                      garment_id: garment.garment_id,
                      replacement_category: garment.category,
                    })}
                  >Swap</button>
                </article>
              ))}
            </div>
          </div>
          <aside className="plan-reasoning">
            <span className="step-number">The reasoning</span>
            <h2>{new Date(`${active.date}T12:00:00`).toLocaleDateString("en-CA", { weekday: "long" })}</h2>
            <ul>{active.explanations.map((reason) => <li key={reason}>{reason}</li>)}</ul>
            <div className="score-list">
              <span>Weather <i style={{ width: `${Math.min(100, active.score.weather / 5)}%` }} /></span>
              <span>Compatibility <i style={{ width: `${Math.min(100, active.score.compatibility / 10)}%` }} /></span>
              <span>Rotation <i style={{ width: `${active.score.rotation}%` }} /></span>
            </div>
            <button className="primary full" disabled={Boolean(busyDay)} onClick={() => update(`/api/v1/plans/${plan.plan_id}/days/${active.date}/lock`)}>
              {active.is_locked ? "Unlock this day" : "Lock it in"}
            </button>
            <button className="secondary full" disabled={Boolean(busyDay) || active.is_locked} onClick={() => update(`/api/v1/plans/${plan.plan_id}/days/${active.date}/regenerate`, { preserve_garment_ids: [], exclude_previous_selection: true })}>
              Solve again
            </button>
          </aside>
        </section>
      )}
    </main>
  );
}
