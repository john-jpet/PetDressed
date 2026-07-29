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
  MetadataResult,
  OutfitPlan,
  SegmentationResult,
} from "@shared/types";
import {
  ClothingRail,
  GarmentIcon,
  HangingGarment,
  iconForCategory,
} from "./garment-icons";
import { Mannequin } from "./mannequin";

type Stage = "idle" | "uploading" | "queued" | "error";
type Tool = "keep" | "remove" | "box";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:58000";

function getSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  return url && key ? createClient(url, key) : null;
}

export function UploadExperience() {
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dragging, setDragging] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");
  const [signedIn, setSignedIn] = useState(false);
  const [accessToken, setAccessToken] = useState("");
  const [garmentId, setGarmentId] = useState("");
  const [pollCycle, setPollCycle] = useState(0);
  const [segmentation, setSegmentation] = useState<SegmentationResult | null>(null);
  const [metadata, setMetadata] = useState<MetadataResult | null>(null);
  const [wardrobe, setWardrobe] = useState<GarmentCard[] | null>(null);
  const [plan, setPlan] = useState<OutfitPlan | null>(null);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);
  const supabase = useMemo(() => getSupabase(), []);

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
      try {
        const response = await fetch(`${apiUrl}/api/v1/garments/in-progress`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const garment = await response.json();
          if (garment?.garment_id) {
            setGarmentId(garment.garment_id);
            setStage("queued");
            setPollCycle((current) => current + 1);
          }
        }
      } catch {
        setError("Signed in, but the processing service is temporarily unavailable.");
      }
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
    setStage("idle");
  }

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (!supabase) {
      setError("Add your Supabase settings to .env.local to enable sign-in.");
      return;
    }
    const { error: authError } =
      authMode === "signup"
        ? await supabase.auth.signUp({ email, password })
        : await supabase.auth.signInWithPassword({ email, password });
    if (authError) setError(authError.message);
    else {
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        setNotice("Account created. Check your email to confirm it, then return here to sign in.");
        setAuthMode("signin");
      } else {
        setAccessToken(data.session.access_token);
        setSignedIn(true);
      }
    }
  }

  async function upload() {
    if (!file || !supabase) return;
    setStage("uploading");
    setError("");
    try {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (!token) throw new Error("Please sign in before uploading.");

      const sessionResponse = await fetch(`${apiUrl}/api/v1/garments/uploads`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
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
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ object_key: session.object_key }),
        },
      );
      if (!confirmResponse.ok) throw new Error("Could not confirm the upload.");
      setStage("queued");
    } catch (caught) {
      setStage("error");
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    }
  }

  useEffect(() => {
    if (stage !== "queued" || !garmentId || !accessToken) return;
    const timer = window.setInterval(async () => {
      try {
        const statusResponse = await fetch(`${apiUrl}/api/v1/garments/${garmentId}/status`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!statusResponse.ok) return;
        const current = await statusResponse.json();
        if (current.processing_status === "segmentation_review") {
          const resultResponse = await fetch(
            `${apiUrl}/api/v1/garments/${garmentId}/segmentation`,
            { headers: { Authorization: `Bearer ${accessToken}` } },
          );
          if (resultResponse.ok) {
            setSegmentation(await resultResponse.json());
            window.clearInterval(timer);
          }
        } else if (current.processing_status === "metadata_review") {
          const resultResponse = await fetch(
            `${apiUrl}/api/v1/garments/${garmentId}/metadata`,
            { headers: { Authorization: `Bearer ${accessToken}` } },
          );
          if (resultResponse.ok) {
            setMetadata(await resultResponse.json());
            window.clearInterval(timer);
          }
        } else if (current.processing_status === "failed") {
          setError(current.error ?? "Garment processing failed.");
          setStage("error");
          window.clearInterval(timer);
        }
      } catch {
        setError("Temporarily unable to reach the processing service. Retrying…");
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [accessToken, garmentId, pollCycle, stage]);

  if (plan) {
    return <Planner initialPlan={plan} token={accessToken} onBack={() => setPlan(null)} />;
  }

  if (wardrobe) {
    return (
      <Wardrobe
        items={wardrobe}
        token={accessToken}
        onPlan={setPlan}
        onAdd={() => {
          setWardrobe(null);
          setGarmentId("");
          setFile(null);
          setSegmentation(null);
          setMetadata(null);
          setError("");
          setNotice("");
          setStage("idle");
        }}
      />
    );
  }

  if (metadata) {
    return (
      <MetadataReview
        result={metadata}
        token={accessToken}
        onConfirmed={async () => {
          const response = await fetch(`${apiUrl}/api/v1/garments`, {
            headers: { Authorization: `Bearer ${accessToken}` },
          });
          if (response.ok) setWardrobe((await response.json()).items);
          setMetadata(null);
        }}
      />
    );
  }

  if (segmentation) {
    return (
      <SegmentationReview
        result={segmentation}
        token={accessToken}
        onRetry={() => {
          setSegmentation(null);
          setStage("queued");
          setPollCycle((current) => current + 1);
        }}
        onAccepted={() => {
          setSegmentation(null);
          setStage("queued");
          setPollCycle((current) => current + 1);
        }}
        onReplace={async () => {
          await fetch(`${apiUrl}/api/v1/garments/${segmentation.garment_id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${accessToken}` },
          });
          setSegmentation(null);
          setGarmentId("");
          setFile(null);
          setStage("idle");
        }}
      />
    );
  }

  return (
    <main>
      <nav className="nav" aria-label="Primary navigation">
        <a className="brand" href="#" aria-label="PetDressed home">
          <span className="brand-mark" aria-hidden="true">P</span>
          <span>PetDressed</span>
        </a>
        <div className="nav-steps" aria-label="Wardrobe setup progress">
          <span className="active">1 · Add item</span>
          <span>2 · Tidy photo</span>
          <span>3 · Describe</span>
        </div>
        <button className="round-button" aria-label="Open help">?</button>
      </nav>

      <section className="hero">
        <ClothingRail className="hero-rail" />
        <div className="eyebrow"><span /> 01 // Intake</div>
        <h1>Build your<br /><em>wardrobe.</em></h1>
        <p className="intro">
          One garment. One photo. Plain background. The machine cuts it out and
          guesses the details — you approve or override every single call.
        </p>

        {!signedIn ? (
          <form className="auth-card" onSubmit={signIn}>
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
            <button className="auth-switch" type="button" onClick={() => setAuthMode((mode) => mode === "signin" ? "signup" : "signin")}>
              {authMode === "signin" ? "New here? Create account" : "Already have an account? Sign in"}
            </button>
          </form>
        ) : (
          <section className="upload-card">
            <div className="upload-heading">
              <div>
                <span className="step-number">01</span>
                <h2>Feed it a garment</h2>
              </div>
              <span className="private-note">Private</span>
            </div>

            <div
              className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event: DragEvent) => {
                event.preventDefault();
                setDragging(false);
                acceptFile(event.dataTransfer.files[0]);
              }}
            >
              {file ? (
                <>
                  <Image
                    src={preview}
                    alt={`Preview of ${file.name}`}
                    width={180}
                    height={190}
                    unoptimized
                  />
                  <div>
                    <strong>{file.name}</strong>
                    <span>{(file.size / 1024 / 1024).toFixed(1)} MB · Locked and loaded</span>
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
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => acceptFile(event.target.files?.[0])}
                />
              </label>
            </div>

            <div className="tips">
              <strong>Rules of engagement</strong>
              <span>Lay it flat. Show the whole piece. Use a background that fights it.</span>
            </div>
            {error && <p className="error" role="alert">{error}</p>}
            {notice && <p className="success" role="status">{notice}</p>}
            {stage === "queued" ? (
              <div className="success" role="status">
                <strong>Photo received.</strong>
                <span className="processing-line"><i /> Stripping the background…</span>
              </div>
            ) : (
              <button className="primary full" disabled={!file || stage === "uploading"} onClick={upload}>
                {stage === "uploading" ? "Uploading…" : "Send it →"}
              </button>
            )}
          </section>
        )}
      </section>

      <aside className="side-note" aria-label="Photography guidance">
        <span className="spark">✣</span>
        <p><strong>One piece at a time.</strong><br />Front-facing. Sharp. No exceptions.</p>
      </aside>
    </main>
  );
}

function SegmentationReview({
  result,
  token,
  onRetry,
  onAccepted,
  onReplace,
}: {
  result: SegmentationResult;
  token: string;
  onRetry: () => void;
  onAccepted: () => void;
  onReplace: () => void;
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
      <nav className="nav" aria-label="Primary navigation">
        <a className="brand" href="#"><span className="brand-mark">P</span><span>PetDressed</span></a>
        <div className="nav-steps">
          <span>1 · Add item</span><span className="active">2 · Tidy photo</span><span>3 · Describe</span>
        </div>
        <button className="round-button" aria-label="Open help">?</button>
      </nav>
      <section className="review-shell">
        <div className="review-copy">
          <div className="eyebrow"><span /> 02 // Verify</div>
          <h1>Check the<br /><em>cut.</em></h1>
          <p className="intro">Brush back anything the machine ate. Scrub out any background that survived. Your call is final.</p>
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
            <button className="secondary" disabled={busy} onClick={onReplace}>
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

function MetadataReview({
  result,
  token,
  onConfirmed,
}: {
  result: MetadataResult;
  token: string;
  onConfirmed: () => void;
}) {
  const [name, setName] = useState(result.display_name ?? "");
  const [category, setCategory] = useState(result.predicted_category);
  const [subcategory, setSubcategory] = useState(result.subcategory ?? "");
  const [formality, setFormality] = useState(result.formality);
  const [warmth, setWarmth] = useState(result.warmth);
  const [breathability, setBreathability] = useState(result.breathability);
  const [waterResistance, setWaterResistance] = useState(result.water_resistance);
  const [pattern, setPattern] = useState(result.pattern);
  const [plannerEnabled, setPlannerEnabled] = useState(
    !result.degraded && result.category_confidence >= 0.45,
  );
  const [seasons, setSeasons] = useState(result.seasons);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (plannerEnabled && !subcategory.trim()) {
      setError("Add a garment type before including this piece in outfit planning.");
      return;
    }
    setBusy(true);
    setError("");
    const response = await fetch(
      `${apiUrl}/api/v1/garments/${result.garment_id}/metadata/confirm`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: name,
          category,
          subcategory: subcategory || null,
          formality,
          warmth,
          breathability,
          water_resistance: waterResistance,
          pattern,
          planner_enabled: plannerEnabled,
          seasons,
        }),
      },
    );
    setBusy(false);
    if (response.ok) onConfirmed();
    else setError("We couldn’t save those details. Please try again.");
  }

  return (
    <main>
      <AppNav active={3} />
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
        <form className="metadata-form" onSubmit={confirm}>
          <div className="eyebrow"><span /> 03 // Label</div>
          <h1>Name the<br /><em>evidence.</em></h1>
          <p className="confidence-note">
            {result.degraded ? "Needs your input" : "Guessed from the photo"} ·{" "}
            {Math.round(result.category_confidence * 100)}% category confidence ·{" "}
            {result.inference_backend}
          </p>
          {result.degraded && (
            <p className="error" role="alert">
              Semantic classification is unavailable. Choose the category and type before enabling
              outfit planning.
            </p>
          )}
          <div className="form-grid">
            <label className="wide">Garment name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Navy everyday shirt" required /></label>
            <label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}>
              {["top","bottom","one_piece","outerwear","shoes","accessory"].map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
            </select></label>
            <label>Type<input value={subcategory} onChange={(event) => setSubcategory(event.target.value)} /></label>
            <AttributeSlider label="Formality" value={formality} setValue={setFormality} low="Relaxed" high="Formal" />
            <AttributeSlider label="Warmth" value={warmth} setValue={setWarmth} low="Light" high="Toasty" />
            <AttributeSlider label="Breathability" value={breathability} setValue={setBreathability} low="Low" high="Airy" />
            <AttributeSlider label="Water resistance" value={waterResistance} setValue={setWaterResistance} low="None" high="Rain-ready" />
            <label>Pattern<select value={pattern} onChange={(event) => setPattern(event.target.value)}>
              {["solid","striped","checked","graphic","floral","abstract","textured","other","unknown"].map((value) => <option key={value}>{value}</option>)}
            </select></label>
            <label className="planner-toggle"><input type="checkbox" checked={plannerEnabled} onChange={(event) => setPlannerEnabled(event.target.checked)} /> Include in outfit planning</label>
            <div className="season-grid wide">
              {(["spring", "summer", "fall", "winter"] as const).map((season) => (
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
          </div>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="primary full" disabled={busy}>{busy ? "Saving…" : "Commit to wardrobe →"}</button>
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

function AppNav({ active = 1, onSettings }: { active?: number; onSettings?: () => void }) {
  return (
    <nav className="nav" aria-label="Primary navigation">
      <a className="brand" href="#"><span className="brand-mark">P</span><span>PetDressed</span></a>
      <div className="nav-steps"><span className={active === 1 ? "active" : ""}>Wardrobe</span><span className={active === 2 ? "active" : ""}>Planner</span><span className={active === 3 ? "active" : ""}>Add item</span></div>
      <button className="round-button" aria-label="Open settings" onClick={onSettings}>⚙</button>
    </nav>
  );
}

function Wardrobe({
  items,
  token,
  onPlan,
  onAdd,
}: {
  items: GarmentCard[];
  token: string;
  onPlan: (plan: OutfitPlan) => void;
  onAdd: () => void;
}) {
  const [garments, setGarments] = useState(items);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [season, setSeason] = useState("all");
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState("");
  const [wardrobeError, setWardrobeError] = useState("");
  const [showSettings, setShowSettings] = useState(false);

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

  async function generatePlan() {
    setPlanning(true);
    setPlanError("");
    const start = new Date();
    start.setDate(start.getDate() + 1);
    const settingsResponse = await fetch(`${apiUrl}/api/v1/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const settings = settingsResponse.ok ? await settingsResponse.json() : null;
    const response = await fetch(`${apiUrl}/api/v1/plans/generate`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        start_date: start.toISOString().slice(0, 10),
        days: 7,
        location: {
          latitude: settings?.latitude ?? 43.6532,
          longitude: settings?.longitude ?? -79.3832,
          timezone: settings?.timezone ?? "America/Toronto",
        },
        daily_requirements: [],
        locked_items: [],
        excluded_items: [],
      }),
    });
    setPlanning(false);
    if (response.ok) onPlan(await response.json());
    else {
      const body = await response.json().catch(() => null);
      setPlanError(body?.detail?.message ?? body?.detail ?? "We couldn’t build a complete week yet.");
    }
  }

  async function changeSeason(next: string) {
    setSeason(next);
    const query = next === "all" ? "" : `?season=${next}`;
    const response = await fetch(`${apiUrl}/api/v1/garments${query}`, {
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
      setGarments((current) =>
        current.filter((garment) => garment.garment_id !== item.garment_id),
      );
    } catch {
      setWardrobeError("We couldn’t remove that piece. Check the API connection and try again.");
    }
  }

  if (showSettings) {
    return <Settings token={token} onBack={() => setShowSettings(false)} />;
  }

  return (
    <main className="wardrobe-page">
      <AppNav active={1} onSettings={() => setShowSettings(true)} />
      <section className="wardrobe-header">
        <div><div className="eyebrow"><span /> The archive</div><h1>Every piece<br /><em>on file.</em></h1></div>
        <div className="header-actions">
          <button className="secondary" onClick={onAdd}>＋ Add piece</button>
          <button className="primary" onClick={generatePlan} disabled={planning}>
            {planning ? "Solving…" : "Plan the week →"}
          </button>
        </div>
      </section>
      {planError && <p className="plan-error error" role="alert">{String(planError)}</p>}
      <section className="wardrobe-controls">
        <label className="search-field"><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try “navy shirt”" /></label>
        <div className="category-pills">
          {["all","top","bottom","one_piece","outerwear","shoes","accessory"].map((value) => (
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
                {/* The uploaded photo, not the cutout: segmentation crops to the
                    mask bounding box, and a poor mask makes the item harder to
                    recognise than the original ever was. */}
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
                <button onClick={() => removeGarment(item)}>Remove</button>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <div className="empty-state">
          <ClothingRail className="empty-rail" count={4} />
          <strong>Nothing matches.</strong>
          <span>Drop a filter or feed it a garment.</span>
        </div>
      )}
    </main>
  );
}

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

  if (!value) return <main><AppNav /><div className="empty-state">Loading settings…</div></main>;
  return (
    <main>
      <AppNav active={0} />
      <form className="settings-panel" onSubmit={save}>
        <button className="back-link" type="button" onClick={onBack}>← Wardrobe</button>
        <div className="eyebrow"><span /> Parameters</div>
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

function Planner({ initialPlan, token, onBack }: { initialPlan: OutfitPlan; token: string; onBack: () => void }) {
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
      <AppNav active={2} />
      <section className="planner-header">
        <button className="back-link" onClick={onBack}>← Wardrobe</button>
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
