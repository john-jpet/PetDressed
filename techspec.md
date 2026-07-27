# Technical Specification: PetDressed

## Smart Wardrobe Digitization and Constraint-Based Outfit Planning

**Version:** 1.0
**Status:** Proposed
**Primary implementation language:** Python 3.11+
**Target platform:** Responsive web application
**Project type:** Computer vision, backend systems, optimization, and full-stack application

---

## 1. Executive Summary

PetDressed is a smart wardrobe management and weekly outfit-planning application.

The system allows a user to:

1. photograph individual garments;
2. automatically remove image backgrounds;
3. classify garment characteristics;
4. review and correct generated metadata;
5. organize garments in a searchable digital wardrobe;
6. generate weather-appropriate weekly outfit schedules;
7. lock, replace, or manually override generated outfits.

PetDressed combines three primary technical systems:

* a computer-vision ingestion pipeline;
* a wardrobe metadata and persistence layer;
* a constraint-based outfit optimization engine.

The computer-vision pipeline generates initial metadata suggestions but does not treat model output as authoritative. Users can correct segmentation masks and garment attributes before an item becomes available to the planner.

The outfit planner uses Google OR-Tools CP-SAT rather than an LLM. Hard constraints ensure that generated outfits are structurally valid, while a weighted objective function rewards weather suitability, compatibility, wardrobe rotation, and user preferences.

The first release is designed around a constrained but reliable workflow:

* one garment per uploaded image;
* user-assisted correction when automatic segmentation fails;
* broad garment categories;
* deterministic, explainable outfit generation;
* user-controlled regeneration and overrides.

---

## 2. Product Goals

### 2.1 Primary Goals

PetDressed must:

* reduce the effort required to digitize a wardrobe;
* produce valid outfits from garments the user actually owns;
* account for forecast conditions;
* avoid excessive garment repetition;
* allow users to correct all automated decisions;
* explain why garments were selected or rejected;
* remain responsive despite computationally expensive image processing;
* support incremental improvement without requiring a complete redesign.

### 2.2 Secondary Goals

The system should:

* surface underused garments;
* support visual similarity search;
* learn from accepted and rejected outfit recommendations;
* identify substitute garments;
* help users plan outfits for several days at once.

### 2.3 Non-Goals for Version 1

The first version will not:

* identify multiple garments from a single closet photograph;
* infer exact garment materials with guaranteed accuracy;
* automatically determine whether an outfit is fashionable;
* provide body-shape or attractiveness judgments;
* generate synthetic clothing images;
* purchase or recommend external clothing products;
* guarantee a fully automatic workflow without user review;
* use an LLM as the primary outfit-selection engine.

---

## 3. High-Level Architecture

```text
┌──────────────────────────────┐
│ Responsive Web Client        │
│ Next.js + React + TypeScript │
└──────────────┬───────────────┘
               │
               │ HTTPS
               ▼
┌──────────────────────────────┐
│ FastAPI Application Server   │
│                              │
│ - Authentication             │
│ - Wardrobe API               │
│ - Upload orchestration       │
│ - Planner API                │
│ - User preferences           │
└───────┬───────────┬──────────┘
        │           │
        │           └──────────────────────────┐
        │                                      │
        ▼                                      ▼
┌───────────────────┐              ┌───────────────────────┐
│ PostgreSQL 16     │              │ S3-Compatible Storage │
│                   │              │                       │
│ - User metadata   │              │ - Original photos     │
│ - Garment records │              │ - Processed PNGs      │
│ - Planner state   │              │ - Mask previews       │
│ - pgvector        │              │                       │
└───────────────────┘              └───────────────────────┘
        ▲                                      ▲
        │                                      │
        └──────────────┬───────────────────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │ Background Job Queue│
            │ Redis + Celery      │
            └──────────┬──────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │ CV Worker Pool       │
            │                      │
            │ - SAM 2 segmentation │
            │ - Fashion-CLIP       │
            │ - Color extraction   │
            │ - Metadata inference │
            └──────────────────────┘

┌──────────────────────────────┐
│ Outfit Planning Service      │
│                              │
│ - Weather normalization      │
│ - Candidate pruning          │
│ - Compatibility scoring      │
│ - OR-Tools CP-SAT solver     │
└──────────────────────────────┘
```

---

## 4. Technology Stack

### 4.1 Backend

* Python 3.11+
* FastAPI
* Pydantic v2
* SQLAlchemy 2.x
* Alembic
* PostgreSQL 16
* pgvector
* Celery
* Redis
* Google OR-Tools
* PyTorch
* OpenCV
* Pillow
* NumPy

### 4.2 Computer Vision

* SAM 2 for garment segmentation
* Fashion-CLIP for image embeddings and zero-shot metadata suggestions
* OpenCV K-Means for dominant-color extraction
* CIELAB colour space for perceptual colour calculations

### 4.3 Frontend

* Next.js with App Router
* React
* TypeScript
* Tailwind CSS
* TanStack Query
* React Hook Form
* Zod
* Indexed browser state only for temporary UI drafts

### 4.4 Infrastructure

* S3-compatible object storage
* MinIO for local development
* PostgreSQL for persistent application data
* Redis for task queuing
* Docker Compose for local development
* Optional CUDA-enabled worker deployment
* CPU fallback for development and testing

---

## 5. Delivery Phases

```text
Phase 1: Garment Upload and Segmentation
        ↓
Phase 2: Metadata Extraction and Review
        ↓
Phase 3: Digital Wardrobe Management
        ↓
Phase 4: Outfit Compatibility and Planning
        ↓
Phase 5: Full Product Integration
        ↓
Phase 6: Feedback Learning and Advanced Features
```

Each phase must produce a demonstrable, independently testable result.

---

# 6. Phase 1: Garment Upload and Segmentation

## 6.1 Goal

Accept a photograph containing one primary garment, isolate the garment from its background, and create a transparent cropped image.

The automatic segmentation result must be treated as a draft. The user must be able to correct or replace it.

## 6.2 Supported Input Assumptions

Version 1 assumes:

* one primary garment per image;
* the garment is mostly visible;
* the garment is not being worn;
* severe occlusion is absent;
* the image uses a supported format;
* the user can provide a tap or bounding-box hint if needed.

Recommended capture guidance:

* use a contrasting background;
* keep the full garment inside the frame;
* avoid overlapping objects;
* avoid extreme shadows;
* photograph the front-facing side where possible.

## 6.3 Upload Flow

The application will use direct object-storage uploads.

```text
1. Client requests upload session
2. Server creates garment draft record
3. Server returns presigned object-storage URL
4. Client uploads image directly to object storage
5. Client confirms upload completion
6. Server marks garment as uploaded
7. Server enqueues segmentation job
8. Worker processes the image
9. User reviews generated mask
10. User accepts or corrects result
```

Large image bytes must not be passed through Celery or Redis.

## 6.4 Upload API

### Create Upload Session

```http
POST /api/v1/garments/uploads
```

Request:

```json
{
  "filename": "blue-shirt.jpg",
  "content_type": "image/jpeg",
  "file_size_bytes": 2480123
}
```

Response:

```json
{
  "garment_id": "uuid",
  "upload_url": "presigned-object-storage-url",
  "object_key": "users/{user_id}/garments/{garment_id}/original.jpg",
  "expires_at": "2026-07-26T18:30:00Z"
}
```

### Confirm Upload

```http
POST /api/v1/garments/{garment_id}/uploads/complete
```

Request:

```json
{
  "object_key": "users/{user_id}/garments/{garment_id}/original.jpg"
}
```

Response:

```json
{
  "garment_id": "uuid",
  "processing_status": "queued"
}
```

## 6.5 Input Validation

Supported formats:

* JPEG
* PNG
* WebP
* HEIC only if the deployment environment supports decoding

Default limits:

* maximum file size: 15 MB;
* maximum input dimension: 6000 pixels;
* minimum input dimension: 256 pixels;
* maximum decoded pixel count: 30 million pixels.

The server must verify:

* declared MIME type;
* detected file signature;
* decoded dimensions;
* user ownership;
* object-storage key prefix;
* upload completion.

## 6.6 Image Normalization

The processing worker will:

1. load the original image;
2. apply EXIF orientation;
3. convert to RGB;
4. preserve the original image in object storage;
5. generate an inference copy;
6. downscale the inference copy to a maximum dimension of 1600 pixels;
7. maintain the original aspect ratio.

The final mask will be mapped back to original-image coordinates before generating the cropped artifact.

## 6.7 Segmentation Strategy

### Automatic Attempt

The worker initially runs automatic mask generation.

Example starting parameters:

```python
points_per_side = 32
pred_iou_thresh = 0.88
stability_score_thresh = 0.92
min_mask_region_area = 500
```

These are initial tuning values, not guaranteed production constants.

### Candidate Filtering

Candidate masks are rejected when they:

* cover less than 2% of the image;
* cover more than 90% of the image;
* touch nearly every image boundary;
* contain highly fragmented regions;
* have poor predicted IoU;
* have poor stability scores.

### Candidate Ranking

Remaining masks are ranked using a weighted score:

```text
MaskScore =
    0.30 × segmentation confidence
  + 0.20 × stability score
  + 0.20 × garment-class similarity
  + 0.15 × centre proximity
  + 0.15 × boundary quality
```

Fashion-CLIP can be used to estimate whether a candidate crop resembles clothing.

### User-Assisted Fallback

When confidence is below a threshold, the application requests:

* a positive tap;
* a negative tap;
* a bounding box;
* or manual brush correction.

The user-assisted mask is generated using SAM 2 prompt input.

## 6.8 Mask Output

The worker will:

1. apply the selected mask;
2. set non-garment pixels to zero alpha;
3. remove isolated mask fragments;
4. smooth severe edge artifacts conservatively;
5. crop around the garment bounding box;
6. apply proportional padding;
7. write a transparent PNG.

Padding should use a percentage of the bounding-box size rather than a fixed 10-pixel value:

```text
padding = max(8 pixels, 3% of maximum bounding-box dimension)
```

## 6.9 Segmentation Result Model

```python
from pydantic import BaseModel
from typing import Literal

class BoundingBox(BaseModel):
    x_min: int
    y_min: int
    x_max: int
    y_max: int

class SegmentationResult(BaseModel):
    garment_id: str
    processed_object_key: str
    preview_object_key: str
    mask_area_ratio: float
    bbox: BoundingBox
    confidence: float
    review_status: Literal["pending", "accepted", "correction_required"]
    model_name: str
    model_version: str
```

## 6.10 Segmentation Review

The user must be able to:

* accept the mask;
* request automatic retry;
* add positive and negative points;
* provide a bounding box;
* manually erase mask regions;
* manually restore mask regions;
* replace the original image.

A garment cannot enter the active wardrobe until the segmentation result is accepted.

---

# 7. Phase 2: Metadata Extraction and Review

## 7.1 Goal

Generate structured garment metadata and an image embedding after segmentation has been accepted.

The system stores generated metadata separately from user-confirmed metadata.

## 7.2 Processing Pipeline

```text
Accepted garment crop
        ↓
Fashion-CLIP embedding
        ↓
Broad category prediction
        ↓
Attribute scoring
        ↓
Dominant-colour extraction
        ↓
Confidence evaluation
        ↓
User review and correction
        ↓
Garment becomes planner eligible
```

## 7.3 Embedding Generation

The image crop is passed through Fashion-CLIP.

Expected output:

```text
512-dimensional normalized floating-point vector
```

The embedding may support:

* duplicate detection;
* visual similarity search;
* substitute-garment retrieval;
* wardrobe clustering;
* diversity calculations.

The embedding must not be treated as a direct measure of outfit compatibility.

## 7.4 Category Taxonomy

### Primary Categories

```text
top
bottom
one_piece
outerwear
shoes
accessory
```

### Example Subcategories

#### Top

* t-shirt
* shirt
* blouse
* polo
* sweater
* hoodie
* tank top

#### Bottom

* jeans
* trousers
* shorts
* skirt
* leggings
* sweatpants

#### One-Piece

* dress
* jumpsuit
* romper
* coverall

#### Outerwear

* light jacket
* rain jacket
* coat
* parka
* blazer
* cardigan

#### Shoes

* sneakers
* boots
* formal shoes
* sandals
* heels
* athletic shoes

#### Accessory

* hat
* scarf
* belt
* bag
* gloves
* jewellery

## 7.5 Zero-Shot Classification

Each attribute is predicted independently using text prompts.

Example category prompts:

```python
CATEGORY_PROMPTS = {
    "top": [
        "a photo of a shirt or top",
        "a standalone upper-body garment"
    ],
    "bottom": [
        "a photo of pants, shorts, or a skirt",
        "a standalone lower-body garment"
    ],
    "one_piece": [
        "a photo of a dress, jumpsuit, or one-piece garment"
    ],
    "outerwear": [
        "a photo of a coat or outerwear layer"
    ],
    "shoes": [
        "a photo of footwear or shoes"
    ],
    "accessory": [
        "a photo of a clothing accessory"
    ]
}
```

Multiple prompts per class may be averaged to reduce prompt sensitivity.

## 7.6 Attribute Model

The system stores discrete and continuous attributes.

### User-Confirmable Attributes

* primary category;
* subcategory;
* display name;
* formality;
* warmth;
* water resistance;
* breathability;
* season suitability;
* pattern;
* dominant colours;
* planner eligibility.

### Recommended Scales

#### Formality

```text
0 = athletic or lounge
1 = very casual
2 = casual
3 = smart casual
4 = business
5 = formal
```

#### Warmth

```text
0 = minimal insulation
1 = very light
2 = light
3 = moderate
4 = warm
5 = heavy winter insulation
```

#### Water Resistance

```text
0 = unsuitable for moisture
1 = limited resistance
2 = light-rain suitable
3 = rain resistant
4 = highly water resistant
5 = waterproof
```

#### Breathability

```text
0 = very low
1 = low
2 = moderate-low
3 = moderate
4 = high
5 = very high
```

## 7.7 Colour Extraction

Only non-transparent garment pixels are included.

Processing steps:

1. remove transparent pixels;
2. reduce noise with light downsampling;
3. convert RGB pixels to CIELAB;
4. run K-Means;
5. merge nearly identical clusters;
6. sort clusters by pixel proportion;
7. convert cluster centres to display RGB and hexadecimal values.

Default number of clusters:

```text
k = min(4, number of meaningful clusters)
```

Each extracted colour includes:

```json
{
  "hex": "#263C78",
  "lab": [31.4, 8.2, -34.7],
  "proportion": 0.61
}
```

Near-white transparent-edge artifacts and near-black shadow artifacts may be excluded when their cluster confidence is low.

## 7.8 Pattern Classification

Initial supported values:

```text
solid
striped
checked
graphic
floral
abstract
textured
other
unknown
```

Pattern output should initially be treated as a user-editable suggestion.

## 7.9 Prediction Confidence

The system must store:

* top predicted class;
* confidence score;
* alternate predictions;
* model version;
* prompt-set version.

Low-confidence predictions must be highlighted in the review interface.

Example:

```json
{
  "predicted_category": "top",
  "confidence": 0.73,
  "alternatives": [
    {
      "category": "outerwear",
      "confidence": 0.19
    },
    {
      "category": "one_piece",
      "confidence": 0.05
    }
  ]
}
```

## 7.10 Metadata Review

The user must explicitly confirm:

* primary category;
* garment name;
* planner eligibility.

Other fields may use generated defaults but remain editable.

Generated and user-confirmed fields must remain separately traceable.

---

# 8. Persistence Model

## 8.1 PostgreSQL Extensions

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
```

`gen_random_uuid()` should be preferred over `uuid-ossp` unless compatibility requirements dictate otherwise.

## 8.2 Enum Types

```sql
CREATE TYPE garment_category AS ENUM (
    'top',
    'bottom',
    'one_piece',
    'outerwear',
    'shoes',
    'accessory'
);

CREATE TYPE garment_processing_status AS ENUM (
    'draft',
    'uploading',
    'uploaded',
    'queued',
    'segmenting',
    'segmentation_review',
    'extracting_metadata',
    'metadata_review',
    'ready',
    'failed',
    'archived'
);

CREATE TYPE garment_availability AS ENUM (
    'available',
    'laundry',
    'unavailable',
    'packed',
    'archived'
);

CREATE TYPE metadata_source AS ENUM (
    'model',
    'user',
    'default'
);
```

## 8.3 Garments Table

```sql
CREATE TABLE garments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL,

    display_name VARCHAR(100),

    processing_status garment_processing_status
        NOT NULL DEFAULT 'draft',

    availability garment_availability
        NOT NULL DEFAULT 'available',

    planner_enabled BOOLEAN
        NOT NULL DEFAULT FALSE,

    original_object_key TEXT,
    processed_object_key TEXT,
    preview_object_key TEXT,

    category garment_category,
    predicted_category garment_category,
    category_confidence REAL,
    category_source metadata_source,

    subcategory VARCHAR(64),
    predicted_subcategory VARCHAR(64),

    formality SMALLINT
        CHECK (formality BETWEEN 0 AND 5),

    warmth SMALLINT
        CHECK (warmth BETWEEN 0 AND 5),

    breathability SMALLINT
        CHECK (breathability BETWEEN 0 AND 5),

    water_resistance SMALLINT
        CHECK (water_resistance BETWEEN 0 AND 5),

    pattern VARCHAR(32),

    embedding vector(512),

    wear_count INTEGER
        NOT NULL DEFAULT 0
        CHECK (wear_count >= 0),

    last_worn_at TIMESTAMPTZ,

    processing_error_code VARCHAR(64),
    processing_error_message TEXT,

    segmentation_model VARCHAR(100),
    segmentation_model_version VARCHAR(100),
    embedding_model VARCHAR(100),
    embedding_model_version VARCHAR(100),
    prompt_set_version VARCHAR(50),

    metadata_confirmed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    archived_at TIMESTAMPTZ
);
```

## 8.4 Garment Colours Table

A normalized table is preferred over nested SQL arrays.

```sql
CREATE TABLE garment_colors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    garment_id UUID NOT NULL
        REFERENCES garments(id)
        ON DELETE CASCADE,

    rank SMALLINT NOT NULL,
    hex_value CHAR(7) NOT NULL,

    lab_l REAL NOT NULL,
    lab_a REAL NOT NULL,
    lab_b REAL NOT NULL,

    proportion REAL NOT NULL
        CHECK (proportion >= 0 AND proportion <= 1),

    UNIQUE (garment_id, rank)
);
```

## 8.5 Garment Seasons Table

```sql
CREATE TABLE garment_seasons (
    garment_id UUID NOT NULL
        REFERENCES garments(id)
        ON DELETE CASCADE,

    season VARCHAR(16) NOT NULL
        CHECK (season IN ('spring', 'summer', 'fall', 'winter')),

    suitability SMALLINT NOT NULL
        CHECK (suitability BETWEEN 0 AND 5),

    PRIMARY KEY (garment_id, season)
);
```

## 8.6 Garment Prediction Audit Table

```sql
CREATE TABLE garment_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    garment_id UUID NOT NULL
        REFERENCES garments(id)
        ON DELETE CASCADE,

    attribute_name VARCHAR(64) NOT NULL,
    predicted_value TEXT NOT NULL,
    confidence REAL,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(100),
    prompt_set_version VARCHAR(50),

    created_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW()
);
```

## 8.7 Vector Index

The index should be added after enough records exist to justify it.

```sql
CREATE INDEX garments_embedding_hnsw_idx
ON garments
USING hnsw (embedding vector_cosine_ops)
WHERE embedding IS NOT NULL;
```

At personal wardrobe scale, exact vector search may already be sufficiently fast. The HNSW index is primarily useful for demonstrating scalable similarity search or supporting future shared catalogues.

## 8.8 Standard Indexes

```sql
CREATE INDEX garments_user_ready_idx
ON garments (user_id, processing_status);

CREATE INDEX garments_user_category_idx
ON garments (user_id, category);

CREATE INDEX garments_user_availability_idx
ON garments (user_id, availability);

CREATE INDEX garments_last_worn_idx
ON garments (user_id, last_worn_at);
```

---

# 9. Background Job System

## 9.1 Job Types

```text
segment_garment
resegment_garment
extract_garment_metadata
generate_embedding
extract_palette
reprocess_garment
delete_garment_artifacts
```

## 9.2 Job Payload

```python
from pydantic import BaseModel
from uuid import UUID

class GarmentProcessingJob(BaseModel):
    garment_id: UUID
    user_id: UUID
    source_object_key: str
    processing_revision: int
```

## 9.3 Idempotency

Each processing request must include a monotonically increasing processing revision.

The worker must verify that:

* the garment still exists;
* the user still owns the garment;
* the revision remains current;
* the garment has not been archived;
* the same stage has not already completed successfully.

Stale worker results must not overwrite newer user corrections.

## 9.4 Retry Policy

Retryable failures:

* temporary object-storage errors;
* transient database failures;
* worker memory pressure;
* temporary GPU failures.

Non-retryable failures:

* invalid image;
* unsupported format;
* corrupted object;
* missing garment record;
* permanently invalid model input.

Example retry schedule:

```text
Attempt 1: immediate
Attempt 2: 10 seconds
Attempt 3: 60 seconds
Attempt 4: 5 minutes
```

## 9.5 Progress Reporting

The client may poll:

```http
GET /api/v1/garments/{garment_id}/status
```

Example response:

```json
{
  "processing_status": "extracting_metadata",
  "progress": 72,
  "stage": "Extracting colours and attributes",
  "error": null
}
```

WebSockets or server-sent events may be added later, but polling is sufficient for the MVP.

---

# 10. Phase 3: Digital Wardrobe

## 10.1 Goal

Provide a searchable, filterable interface for viewing and managing garments.

## 10.2 Required Features

Users can:

* view all ready garments;
* filter by category;
* filter by colour;
* filter by formality;
* filter by season;
* filter by availability;
* search by garment name;
* sort by last worn;
* sort by wear count;
* mark garments as laundry;
* disable garments from planning;
* edit metadata;
* archive garments;
* locate visually similar garments.

## 10.3 Wardrobe API

```http
GET /api/v1/garments
```

Example query:

```text
?category=top
&availability=available
&season=summer
&sort=least_worn
&page=1
&page_size=30
```

## 10.4 Similarity Search

```http
GET /api/v1/garments/{garment_id}/similar
```

Example SQL:

```sql
SELECT
    id,
    display_name,
    processed_object_key,
    1 - (embedding <=> :query_embedding) AS similarity
FROM garments
WHERE user_id = :user_id
  AND id <> :garment_id
  AND processing_status = 'ready'
  AND embedding IS NOT NULL
ORDER BY embedding <=> :query_embedding
LIMIT 10;
```

Similarity search must be described as visual or semantic similarity, not outfit compatibility.

---

# 11. Phase 4: Weather Normalization

## 11.1 Goal

Convert external forecast data into a stable daily planning representation.

The planner must not depend directly on a provider-specific response format.

## 11.2 Forecast Provider Interface

```python
from typing import Protocol
from datetime import date

class WeatherProvider(Protocol):
    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        days: int
    ) -> list["DailyWeather"]:
        ...
```

This permits replacement of the initial weather provider without changing the solver.

## 11.3 Daily Weather Model

```python
from pydantic import BaseModel
from datetime import date

class DailyWeather(BaseModel):
    date: date

    min_temp_c: float
    max_temp_c: float
    apparent_min_temp_c: float
    apparent_max_temp_c: float

    precipitation_probability: float
    precipitation_mm: float

    max_wind_kph: float
    humidity_percent: float | None

    weather_code: str
    confidence: float | None
```

## 11.4 Planning Temperature

The planner derives a representative temperature based on the user’s expected active hours.

Example:

```text
planning_temperature =
    weighted average of apparent temperature
    between user-defined departure and return times
```

When hourly data is unavailable, the system may use:

```text
0.4 × apparent minimum
+ 0.6 × apparent maximum
```

## 11.5 Seven-Day Requirement

The selected provider or endpoint must support at least seven forecast days.

If only five days are available:

* days six and seven must be marked low confidence;
* the planner may use climatological fallback data;
* or the UI may present those days as provisional.

The application must not silently present a five-day forecast as a reliable seven-day forecast.

## 11.6 Weather Suitability Rules

Each garment receives a suitability score for the day.

Example considerations:

* warmth;
* breathability;
* water resistance;
* season;
* category;
* precipitation;
* apparent temperature;
* wind.

Example rule:

```text
TemperatureSuitability(g, d) =
    100
    - |RequiredWarmth(d) - GarmentWarmth(g)| × penalty
```

Weather suitability is a soft score unless the condition creates a true safety or structural requirement.

---

# 12. Phase 5: Outfit Planning Engine

## 12.1 Goal

Generate a complete outfit schedule that:

* satisfies structural outfit requirements;
* uses only available garments;
* respects user locks and exclusions;
* avoids undesirable repetition;
* accounts for weather;
* balances style compatibility and garment rotation.

## 12.2 Solver

* Google OR-Tools
* CP-SAT solver
* integer objective coefficients
* bounded execution time
* deterministic seed for reproducible testing

## 12.3 Sets

Let:

* (D) be the set of planning days;
* (G) be the set of eligible garments;
* (T) be tops;
* (B) be bottoms;
* (O) be one-piece garments;
* (J) be outerwear;
* (S) be shoes;
* (A) be optional accessories.

## 12.4 Primary Decision Variable

[
x_{d,g} \in {0,1}
]

Where:

[
x_{d,g}=1
]

means garment (g) is assigned to day (d).

## 12.5 Outfit Mode Variable

[
m_d \in {0,1}
]

Where:

* (m_d=0): top-and-bottom outfit;
* (m_d=1): one-piece outfit.

## 12.6 Category Completeness Constraints

For every day (d):

[
\sum_{g\in O}x_{d,g}=m_d
]

[
\sum_{g\in T}x_{d,g}=1-m_d
]

[
\sum_{g\in B}x_{d,g}=1-m_d
]

[
\sum_{g\in S}x_{d,g}=1
]

Outerwear is optional unless required by weather or user rules:

[
\sum_{g\in J}x_{d,g}\leq1
]

Accessory count may be bounded:

[
\sum_{g\in A}x_{d,g}\leq A_{\max}
]

## 12.7 Eligibility Constraints

A garment may only enter the candidate set when:

```text
processing_status = ready
planner_enabled = true
availability = available
category is not null
metadata is confirmed
```

Excluded garments do not receive decision variables.

## 12.8 User Lock Constraints

A user may lock garment (g) to day (d):

[
x_{d,g}=1
]

A user may exclude garment (g) from day (d):

[
x_{d,g}=0
]

Before solving, the application validates locked combinations for structural conflicts.

## 12.9 Rotation Constraints

Rotation windows should vary by category.

Example defaults:

| Category  | Minimum reuse gap |
| --------- | ----------------: |
| Top       |            3 days |
| Bottom    |            2 days |
| One-piece |            3 days |
| Outerwear |            0 days |
| Shoes     |            0 days |
| Accessory |            0 days |

For a garment (g) with reuse window (K_g):

[
\forall d \in {1,\dots,|D|-K_g+1},
\quad
\sum_{\tau=0}^{K_g-1}x_{d+\tau,g}\leq1
]

Some categories should use soft repetition penalties rather than hard constraints, especially when the wardrobe is small.

## 12.10 Weather Constraints

Weather rules should be divided into hard and soft conditions.

### Example Hard Conditions

When precipitation is severe and the user enables rain protection:

[
\sum_{g\in J_{\text{rain-capable}}}x_{d,g}\geq1
]

When the apparent temperature is below the configured cold threshold:

[
\sum_{g\in J_{\text{warm}}}x_{d,g}\geq1
]

### Example Soft Conditions

* prefer breathable garments in hot weather;
* prefer warm garments in cold weather;
* penalize low water resistance in rain;
* prefer boots in snow;
* prefer lighter colours in extreme heat.

## 12.11 Pair Compatibility Variables

The objective cannot directly multiply Boolean decision variables.

For each compatible candidate pair (g_1,g_2), introduce:

[
y_{d,g_1,g_2}\in{0,1}
]

Where:

[
y_{d,g_1,g_2}
=============

x_{d,g_1}\land x_{d,g_2}
]

Linearization:

[
y_{d,g_1,g_2}\leq x_{d,g_1}
]

[
y_{d,g_1,g_2}\leq x_{d,g_2}
]

[
y_{d,g_1,g_2}\geq x_{d,g_1}+x_{d,g_2}-1
]

Pair variables should only be created for meaningful category relationships:

* top and bottom;
* top and outerwear;
* one-piece and outerwear;
* garment and shoes;
* garment and accessory.

## 12.12 Compatibility Model

Version 1 uses a transparent heuristic model.

[
Compatibility(g_1,g_2)=
w_cC(g_1,g_2)
+w_fF(g_1,g_2)
+w_pP(g_1,g_2)
+w_uU(g_1,g_2)
]

Where:

* (C): colour compatibility;
* (F): formality compatibility;
* (P): pattern compatibility;
* (U): learned user preference.

## 12.13 Colour Compatibility

CIELAB distance alone is insufficient.

The initial system uses explicit colour rules:

* neutral-neutral compatibility;
* neutral-colour compatibility;
* analogous hue combinations;
* complementary hue combinations;
* lightness contrast;
* saturation balance;
* excessive colour-count penalty.

Example normalized score:

```text
0   = strongly discouraged combination
50  = acceptable combination
100 = strongly preferred combination
```

The exact rule set must be versioned.

## 12.14 Formality Compatibility

Let formality values range from 0 to 5.

Example:

[
F(g_1,g_2)
==========

100-20\cdot |f_{g_1}-f_{g_2}|
]

The result is clamped between 0 and 100.

Some category pairs may use different tolerances.

## 12.15 Pattern Compatibility

Example initial rules:

* solid and solid: neutral;
* patterned and solid: preferred;
* patterned and patterned: penalized unless manually approved;
* matching suit pieces: strongly preferred;
* identical graphic-heavy items: penalized.

## 12.16 User Preference Score

Initially, user preference is derived from explicit actions:

* accepted outfit;
* rejected outfit;
* replaced garment;
* manually created outfit;
* favourited garment pair.

The MVP should not claim sophisticated personalization from limited data.

## 12.17 Garment Utility Scores

For each garment and day, calculate:

* weather suitability;
* underuse reward;
* favourite reward;
* recent-wear penalty;
* user-exclusion penalty;
* event suitability.

All scores are scaled to integers before entering CP-SAT.

Example:

```text
floating score: 0.873
integer solver score: 873
```

## 12.18 Objective Function

Maximize:

[
Z =
\sum_{d\in D}
\sum_{g\in G}
x_{d,g}
\left(
w_wWeather_{d,g}
+w_rRotation_{d,g}
+w_fFavorite_g
+w_eEvent_{d,g}
\right)
]

[
+
\sum_{d\in D}
\sum_{(g_1,g_2)\in P}
y_{d,g_1,g_2}
\cdot
w_cCompatibility_{g_1,g_2}
]

## [

\sum_{d\in D}
\sum_{g\in G}
x_{d,g}
\cdot
w_pRecentWearPenalty_{d,g}
]

The score must remain explainable by retaining each component.

## 12.19 Candidate Pruning

Before creating solver variables:

* remove unavailable garments;
* remove excluded garments;
* remove weather-incompatible garments when necessary;
* retain the highest-scoring candidates per category;
* always retain user-locked garments;
* retain a diversity sample of alternatives.

Example limits per day:

```text
tops: 20
bottoms: 20
one-pieces: 15
outerwear: 10
shoes: 12
accessories: 10
```

This reduces pair-variable growth while remaining sufficient for personal wardrobes.

## 12.20 Infeasibility Handling

The solver may become infeasible because:

* the user owns too few eligible garments;
* rotation constraints are too strict;
* locked garments conflict;
* weather requirements cannot be satisfied;
* all items in a category are unavailable.

The system should solve in stages.

### Relaxation Order

1. preserve all user locks;
2. preserve structural category constraints;
3. preserve explicit exclusions;
4. relax repetition rules;
5. relax soft weather requirements;
6. reduce accessory expectations;
7. report unresolved hard conflicts.

The application must not silently violate locked or structural constraints.

## 12.21 Solver Result

```python
from pydantic import BaseModel
from datetime import date
from uuid import UUID

class ScoreBreakdown(BaseModel):
    weather: int
    compatibility: int
    rotation: int
    preference: int
    event: int
    total: int

class PlannedOutfit(BaseModel):
    date: date
    garment_ids: list[UUID]
    score: ScoreBreakdown
    explanations: list[str]
    provisional_weather: bool

class PlannerResult(BaseModel):
    status: str
    outfits: list[PlannedOutfit]
    relaxed_constraints: list[str]
    solve_time_ms: int
    objective_value: int | None
```

---

# 13. Solver Implementation Skeleton

```python
from collections import defaultdict
from ortools.sat.python import cp_model


def solve_weekly_outfits(
    days,
    garments,
    pair_scores,
    garment_day_scores,
    locked_items,
    excluded_items,
    max_solve_seconds=5.0,
):
    model = cp_model.CpModel()

    garment_by_id = {garment["id"]: garment for garment in garments}
    garments_by_category = defaultdict(list)

    for garment in garments:
        garments_by_category[garment["category"]].append(garment)

    x = {}

    for day_index, _day in enumerate(days):
        for garment in garments:
            garment_id = garment["id"]
            x[day_index, garment_id] = model.NewBoolVar(
                f"wear_d{day_index}_g{garment_id}"
            )

    outfit_mode = {
        day_index: model.NewBoolVar(f"one_piece_mode_d{day_index}")
        for day_index in range(len(days))
    }

    for day_index in range(len(days)):
        model.Add(
            sum(
                x[day_index, garment["id"]]
                for garment in garments_by_category["one_piece"]
            )
            == outfit_mode[day_index]
        )

        model.Add(
            sum(
                x[day_index, garment["id"]]
                for garment in garments_by_category["top"]
            )
            == 1 - outfit_mode[day_index]
        )

        model.Add(
            sum(
                x[day_index, garment["id"]]
                for garment in garments_by_category["bottom"]
            )
            == 1 - outfit_mode[day_index]
        )

        model.Add(
            sum(
                x[day_index, garment["id"]]
                for garment in garments_by_category["shoes"]
            )
            == 1
        )

        model.Add(
            sum(
                x[day_index, garment["id"]]
                for garment in garments_by_category["outerwear"]
            )
            <= 1
        )

    for day_index, garment_id in locked_items:
        if (day_index, garment_id) not in x:
            raise ValueError(f"Locked garment {garment_id} is not eligible")

        model.Add(x[day_index, garment_id] == 1)

    for day_index, garment_id in excluded_items:
        if (day_index, garment_id) in x:
            model.Add(x[day_index, garment_id] == 0)

    for garment in garments:
        garment_id = garment["id"]
        reuse_window = garment["reuse_window_days"]

        if reuse_window <= 1:
            continue

        for start_day in range(len(days) - reuse_window + 1):
            model.Add(
                sum(
                    x[start_day + offset, garment_id]
                    for offset in range(reuse_window)
                )
                <= 1
            )

    pair_vars = {}
    objective_terms = []

    for day_index in range(len(days)):
        for garment in garments:
            garment_id = garment["id"]
            score = garment_day_scores.get((day_index, garment_id), 0)

            if score:
                objective_terms.append(
                    score * x[day_index, garment_id]
                )

        for (left_id, right_id), pair_score in pair_scores.items():
            if (
                (day_index, left_id) not in x
                or (day_index, right_id) not in x
            ):
                continue

            pair_var = model.NewBoolVar(
                f"pair_d{day_index}_{left_id}_{right_id}"
            )

            pair_vars[day_index, left_id, right_id] = pair_var

            model.Add(pair_var <= x[day_index, left_id])
            model.Add(pair_var <= x[day_index, right_id])
            model.Add(
                pair_var
                >= x[day_index, left_id]
                + x[day_index, right_id]
                - 1
            )

            objective_terms.append(pair_score * pair_var)

    model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_solve_seconds
    solver.parameters.random_seed = 42
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    return parse_solver_output(
        status=status,
        solver=solver,
        x=x,
        days=days,
        garments=garments,
        garment_by_id=garment_by_id,
    )
```

Production code must additionally implement:

* weather constraints;
* constraint relaxation;
* score explanations;
* cancellation;
* structured logging;
* status-specific errors;
* objective coefficient bounds;
* deterministic testing configuration.

---

# 14. Outfit Planning API

## 14.1 Generate Plan

```http
POST /api/v1/plans/generate
```

Request:

```json
{
  "start_date": "2026-07-27",
  "days": 7,
  "location": {
    "latitude": 43.4723,
    "longitude": -80.5449,
    "timezone": "America/Toronto"
  },
  "daily_requirements": [
    {
      "date": "2026-07-28",
      "minimum_formality": 3,
      "maximum_formality": 5,
      "label": "Office"
    }
  ],
  "locked_items": [
    {
      "date": "2026-07-28",
      "garment_id": "uuid"
    }
  ],
  "excluded_items": []
}
```

Response:

```json
{
  "plan_id": "uuid",
  "status": "complete",
  "solve_time_ms": 184,
  "relaxed_constraints": [],
  "days": [
    {
      "date": "2026-07-27",
      "garments": [
        {
          "garment_id": "uuid",
          "category": "top"
        },
        {
          "garment_id": "uuid",
          "category": "bottom"
        },
        {
          "garment_id": "uuid",
          "category": "shoes"
        }
      ],
      "score": {
        "weather": 87,
        "compatibility": 82,
        "rotation": 91,
        "preference": 70,
        "event": 100,
        "total": 430
      },
      "explanations": [
        "Suitable for warm weather",
        "The navy top coordinates with the neutral trousers",
        "Neither item has been worn recently"
      ],
      "provisional_weather": false
    }
  ]
}
```

## 14.2 Regenerate One Day

```http
POST /api/v1/plans/{plan_id}/days/{date}/regenerate
```

Request:

```json
{
  "preserve_garment_ids": [
    "uuid"
  ],
  "exclude_previous_selection": true
}
```

## 14.3 Replace One Garment

```http
POST /api/v1/plans/{plan_id}/days/{date}/replace
```

Request:

```json
{
  "garment_id": "current-garment-uuid",
  "replacement_category": "top"
}
```

## 14.4 Lock Outfit

```http
POST /api/v1/plans/{plan_id}/days/{date}/lock
```

---

# 15. Planner Persistence

## 15.1 Plans Table

```sql
CREATE TABLE outfit_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL,

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    status VARCHAR(32) NOT NULL,

    solver_version VARCHAR(50) NOT NULL,
    scoring_version VARCHAR(50) NOT NULL,
    weather_provider VARCHAR(50),
    weather_generated_at TIMESTAMPTZ,

    solve_time_ms INTEGER,
    objective_value BIGINT,

    created_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW()
);
```

## 15.2 Plan Days Table

```sql
CREATE TABLE outfit_plan_days (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    plan_id UUID NOT NULL
        REFERENCES outfit_plans(id)
        ON DELETE CASCADE,

    plan_date DATE NOT NULL,

    is_locked BOOLEAN
        NOT NULL DEFAULT FALSE,

    weather_snapshot JSONB NOT NULL,
    score_breakdown JSONB NOT NULL,
    explanations JSONB NOT NULL,
    relaxed_constraints JSONB NOT NULL,

    UNIQUE (plan_id, plan_date)
);
```

## 15.3 Plan Garments Table

```sql
CREATE TABLE outfit_plan_garments (
    plan_day_id UUID NOT NULL
        REFERENCES outfit_plan_days(id)
        ON DELETE CASCADE,

    garment_id UUID NOT NULL
        REFERENCES garments(id),

    category garment_category NOT NULL,

    is_user_locked BOOLEAN
        NOT NULL DEFAULT FALSE,

    PRIMARY KEY (plan_day_id, garment_id)
);
```

---

# 16. User Feedback Model

## 16.1 Goal

Capture explicit user feedback without pretending that sparse behavioural data is sufficient for advanced machine learning.

## 16.2 Feedback Types

```text
accepted_plan
accepted_day
rejected_day
replaced_item
locked_item
favourited_pair
disliked_pair
manual_outfit
worn_as_planned
not_worn
```

## 16.3 Feedback Table

```sql
CREATE TABLE outfit_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL,
    plan_id UUID
        REFERENCES outfit_plans(id)
        ON DELETE SET NULL,

    plan_day_id UUID
        REFERENCES outfit_plan_days(id)
        ON DELETE SET NULL,

    feedback_type VARCHAR(32) NOT NULL,

    garment_ids UUID[] NOT NULL,

    metadata JSONB,

    created_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW()
);
```

## 16.4 Initial Personalization

Version 1 may update simple preference weights:

* repeated acceptance increases pair preference;
* explicit dislike decreases pair preference;
* repeated manual pairing increases pair preference;
* replacing a garment decreases the rejected pairing’s preference.

Weights must be bounded to prevent early feedback from dominating all future plans.

---

# 17. Frontend Application

## 17.1 Main Screens

### Capture and Upload

* camera or file selection;
* photo-quality guidance;
* upload progress;
* processing progress;
* retry handling.

### Segmentation Review

* transparent-background preview;
* original-image toggle;
* positive and negative point tools;
* bounding-box tool;
* brush correction;
* accept and retry controls.

### Metadata Review

* editable category;
* editable name;
* attribute sliders;
* colour palette preview;
* confidence indicators;
* model suggestions.

### Digital Wardrobe

* responsive card grid;
* category filters;
* colour filters;
* availability controls;
* search;
* sorting;
* similarity results.

### Weekly Planner

* seven-day calendar;
* weather summary;
* outfit cards;
* score explanation;
* lock controls;
* replace controls;
* regenerate controls;
* drag-and-drop manual overrides.

### Settings

* location;
* active hours;
* preferred temperature ranges;
* repetition tolerance;
* preferred formality;
* accessory usage;
* weather strictness;
* data deletion.

## 17.2 Accessibility

The application must support:

* keyboard navigation;
* visible focus indicators;
* semantic labels;
* sufficient contrast;
* screen-reader descriptions;
* reduced-motion preferences;
* non-colour-only status indicators;
* accessible drag-and-drop alternatives.

---

# 18. Security and Privacy

## 18.1 Data Ownership

Every garment, plan, image, and feedback record must be associated with a user.

All queries must scope records by authenticated user ID.

Object-storage paths must include non-guessable identifiers and user-specific prefixes.

## 18.2 Presigned URLs

Presigned URLs must:

* expire quickly;
* be limited to one object key;
* restrict content length;
* restrict permitted operation;
* never expose storage credentials.

Processed-image read URLs should also be temporary unless delivered through an authenticated proxy.

## 18.3 Uploaded Content

The system must:

* verify file signatures;
* reject unsupported formats;
* enforce size limits;
* isolate image decoding;
* strip unneeded metadata;
* avoid rendering unsanitized SVG uploads;
* log processing errors without storing raw file bytes in logs.

## 18.4 Location Privacy

Exact location should not be stored unless necessary.

Preferred approach:

* store approximate coordinates or a selected city;
* permit manual weather location;
* explain why location is required;
* allow location deletion.

## 18.5 Model and Data Isolation

User garments must not be used for model training by default.

Any future opt-in training program must:

* be explicit;
* be revocable;
* define retention;
* define anonymization;
* explain how images are used.

## 18.6 Data Deletion

Deleting a garment must remove:

* database metadata;
* generated predictions;
* plan references where safe;
* original object;
* processed object;
* previews;
* cached derivatives.

Deletion may be asynchronous but must expose status.

---

# 19. Observability

## 19.1 Structured Logs

Logs should include:

* request ID;
* user ID hash or internal ID;
* garment ID;
* plan ID;
* worker task ID;
* processing stage;
* model version;
* latency;
* error code.

Logs must not contain image bytes, presigned URLs, or sensitive metadata.

## 19.2 Metrics

### API Metrics

* request count;
* error rate;
* p50, p95, and p99 latency;
* upload-session failures;
* planner request latency.

### Worker Metrics

* queue depth;
* queue delay;
* segmentation latency;
* metadata extraction latency;
* task retry count;
* GPU utilization;
* worker memory use;
* failure rate by stage.

### Solver Metrics

* solve time;
* feasible-plan rate;
* infeasible-plan rate;
* relaxation frequency;
* number of variables;
* number of pair variables;
* candidate count;
* objective score distribution.

---

# 20. Testing Strategy

## 20.1 Unit Tests

Test:

* colour conversion;
* palette merging;
* score normalization;
* formality compatibility;
* colour compatibility rules;
* weather suitability;
* rotation-window generation;
* candidate pruning;
* constraint linearization;
* API validators;
* status transitions.

## 20.2 Solver Tests

Create deterministic test wardrobes.

### Minimum Wardrobe

* one top;
* one bottom;
* one pair of shoes.

Expected:

* one valid day;
* repetition relaxation required for multi-day plans.

### Standard Wardrobe

* ten tops;
* six bottoms;
* three pairs of shoes;
* three outerwear items.

Expected:

* seven-day feasible plan;
* no invalid category combinations;
* configured repetition windows respected.

### One-Piece Wardrobe

Expected:

* one-piece mode replaces top and bottom;
* shoes remain required.

### Locked Conflict

Example:

* one-piece locked;
* top locked;
* bottom locked on the same day.

Expected:

* validation error before solver execution.

### Weather Failure

Example:

* severe rain requirement;
* no rain-capable outerwear.

Expected:

* explicit infeasibility or documented relaxation;
* no silent constraint violation.

## 20.3 Integration Tests

Test:

* upload session creation;
* object confirmation;
* worker enqueueing;
* processing-state transitions;
* segmentation result persistence;
* metadata review;
* garment activation;
* weather retrieval;
* planner generation;
* plan regeneration;
* garment deletion.

## 20.4 End-to-End Tests

Primary user journey:

```text
Register
→ Upload garment
→ Review segmentation
→ Confirm metadata
→ Add several garments
→ Generate weekly plan
→ Replace one item
→ Lock a day
→ Regenerate remaining days
→ Mark worn items
```

## 20.5 Computer-Vision Evaluation Dataset

Create a versioned internal dataset containing:

* clean backgrounds;
* cluttered backgrounds;
* dark garments;
* light garments;
* patterned garments;
* reflective fabrics;
* shoes;
* dresses;
* outerwear;
* partial occlusion;
* low-light images;
* unusual aspect ratios.

Each sample should include:

* manually reviewed segmentation mask;
* primary category;
* major attributes;
* acceptance status.

---

# 21. Success Metrics

## 21.1 Phase 1: Segmentation

| Metric                             |              Initial target |
| ---------------------------------- | --------------------------: |
| Mean mask IoU                      | ≥ 0.85 on controlled images |
| Boundary F-score                   |                      ≥ 0.80 |
| Accepted without correction        |                       ≥ 75% |
| Accepted after assisted correction |                       ≥ 95% |
| Median GPU processing time         |               < 2.5 seconds |
| p95 GPU processing time            |                 < 6 seconds |

A single speed target is not sufficient; both quality and correction rate must be measured.

## 21.2 Phase 2: Metadata

| Metric                        | Initial target |
| ----------------------------- | -------------: |
| Broad-category macro F1       |         ≥ 0.85 |
| Broad-category top-1 accuracy |         ≥ 0.88 |
| High-confidence error rate    |           < 5% |
| User correction rate          |          < 25% |
| Palette user-acceptance rate  |          ≥ 80% |

Results must be reported by category rather than only as overall accuracy.

## 21.3 Phase 3: Wardrobe

| Metric                              |      Initial target |
| ----------------------------------- | ------------------: |
| Wardrobe query p95                  |            < 400 ms |
| Metadata update p95                 |            < 500 ms |
| Similarity query p95                |            < 500 ms |
| Garment-processing failure recovery | ≥ 99% after retries |

## 21.4 Phase 4: Planner

| Metric                                 |                 Initial target |
| -------------------------------------- | -----------------------------: |
| Structurally valid generated outfits   |                           100% |
| Solver p95 for 100 garments and 7 days |                    < 2 seconds |
| Plans solved without relaxation        | ≥ 90% for valid test wardrobes |
| Constraint violations                  |                              0 |
| User day-level acceptance              |        ≥ 70% during evaluation |
| Manual garment replacement rate        |                          < 35% |

## 21.5 End-to-End Processing

Separate acknowledgement and background completion.

| Metric                           | Initial target |
| -------------------------------- | -------------: |
| Upload-session response p95      |       < 300 ms |
| Upload confirmation response p95 |       < 300 ms |
| Median processing completion     |    < 5 seconds |
| p95 processing completion        |   < 12 seconds |
| UI processing-status freshness   |    < 2 seconds |

---

# 22. Deployment Topology

## 22.1 Local Development

```text
Docker Compose
├── frontend
├── api
├── worker
├── PostgreSQL
├── Redis
└── MinIO
```

Model checkpoints may be mounted into the worker container.

## 22.2 Production MVP

```text
Frontend:
    Vercel or equivalent static/server-rendered host

API:
    Container host or virtual private server

PostgreSQL:
    Managed PostgreSQL with pgvector

Redis:
    Managed Redis or colocated secured instance

Object Storage:
    S3-compatible managed storage

CV Worker:
    GPU instance or CPU-compatible worker
```

The API and worker may be deployed separately because their resource profiles differ substantially.

## 22.3 CPU Fallback

The system must support CPU processing for development.

CPU mode may:

* use a smaller segmentation checkpoint;
* lower inference resolution;
* limit worker concurrency;
* accept slower completion targets.

The user-facing API must remain asynchronous regardless of inference hardware.

---

# 23. Failure Handling

## 23.1 Segmentation Failure

Display:

* clear failure state;
* retry option;
* bounding-box option;
* manual mask option;
* image replacement option.

## 23.2 Metadata Failure

The garment may still proceed through manual metadata entry when:

* segmentation succeeded;
* the processed image exists;
* embedding or classification failed.

Model failure must not permanently block garment creation.

## 23.3 Weather Failure

When weather retrieval fails:

* use recently cached forecast when sufficiently fresh;
* mark weather data as stale;
* allow planning without weather;
* do not fabricate forecast values.

## 23.4 Solver Failure

When the solver times out:

* return the best feasible solution found;
* mark the result as non-optimal;
* retain score and solve-time metadata.

When no solution exists:

* return structured conflict information;
* suggest which constraints could be relaxed;
* do not return an invalid outfit.

---

# 24. Versioning

The following components must be versioned:

* database schema;
* segmentation model;
* embedding model;
* prompt set;
* metadata classifier;
* colour-rule set;
* compatibility scoring;
* solver configuration;
* weather normalization;
* API.

Example:

```text
segmentation_model_version = sam2-hiera-small-1
embedding_model_version = fashion-clip-vit-b32-1
prompt_set_version = category-prompts-2
scoring_version = compatibility-heuristic-3
solver_version = weekly-cpsat-2
```

Versioning allows previous plans and predictions to remain explainable after algorithms change.

---

# 25. Implementation Roadmap

## Milestone 1: Upload Foundation

Deliverables:

* garment draft record;
* presigned upload flow;
* object-storage integration;
* image validation;
* processing status endpoint.

## Milestone 2: Segmentation Prototype

Deliverables:

* local SAM 2 worker;
* automatic segmentation;
* transparent PNG generation;
* mask-quality benchmark;
* bounding-box fallback.

## Milestone 3: Segmentation Review UI

Deliverables:

* original and processed preview;
* accept and reject flow;
* positive and negative point correction;
* processing-state updates.

## Milestone 4: Metadata Extraction

Deliverables:

* Fashion-CLIP embedding;
* broad category predictions;
* colour extraction;
* model confidence storage;
* prediction audit records.

## Milestone 5: Metadata Review and Wardrobe

Deliverables:

* metadata editing;
* wardrobe grid;
* filters;
* laundry and availability state;
* similarity search.

## Milestone 6: Compatibility Engine

Deliverables:

* colour compatibility;
* formality compatibility;
* pattern rules;
* integer scoring;
* score explanations.

## Milestone 7: CP-SAT Planner

Deliverables:

* outfit modes;
* category constraints;
* rotation rules;
* pair-variable linearization;
* locked items;
* exclusions;
* deterministic solver tests.

## Milestone 8: Weather Integration

Deliverables:

* provider abstraction;
* seven-day normalization;
* weather suitability;
* cached forecasts;
* stale-data handling.

## Milestone 9: Planner Interface

Deliverables:

* weekly calendar;
* explanations;
* item replacement;
* day regeneration;
* locking;
* manual overrides.

## Milestone 10: Product Hardening

Deliverables:

* retries;
* idempotency;
* security review;
* accessibility;
* monitoring;
* end-to-end tests;
* benchmark report;
* deployed demonstration.

---

# 26. Advanced Features

The following features are intentionally deferred.

## 26.1 Multi-Garment Image Detection

Use an object detector or grounded segmentation system before SAM 2 to locate multiple garments.

## 26.2 Learned Compatibility Model

Train or fine-tune a model using:

* public outfit compatibility datasets;
* opt-in user feedback;
* accepted combinations;
* rejected combinations.

The learned model should augment, not silently replace, explainable constraints.

## 26.3 Wardrobe Gap Analysis

Identify categories or functional requirements that are difficult to satisfy, such as:

* no rain-compatible footwear;
* insufficient formal outfits;
* limited hot-weather bottoms;
* excessive duplication.

## 26.4 Packing Planner

Generate a minimized garment set for a trip while covering:

* all travel days;
* forecast conditions;
* planned activities;
* laundry opportunities;
* luggage limits.

## 26.5 Calendar Integration

Import event labels and dress requirements from a calendar, subject to explicit permission.

## 26.6 Outfit History

Store actual outfits worn rather than assuming planned outfits were used.

## 26.7 Personal Style Learning

Use explicit feedback and manual outfits to gradually personalize:

* colour combinations;
* preferred silhouettes;
* repetition tolerance;
* formality;
* favourite garments.

---

# 27. Final Acceptance Criteria

PetDressed Version 1 is complete when:

1. a user can upload an individual garment image;
2. the system creates an automatic segmentation result;
3. the user can correct and approve the mask;
4. the system extracts an embedding, broad category, and colour palette;
5. the user can review and correct metadata;
6. the garment appears in a searchable wardrobe;
7. the user can manage availability and laundry state;
8. the application can retrieve and normalize a seven-day forecast;
9. the planner can generate structurally valid seven-day outfits;
10. one-piece outfits work correctly;
11. compatibility terms are linearized for CP-SAT;
12. rotation rules vary by garment category;
13. users can lock, exclude, replace, and regenerate garments;
14. infeasible plans return clear explanations;
15. generated plans include score breakdowns;
16. the complete workflow is covered by end-to-end tests;
17. benchmark results are documented;
18. the application is deployed as a working demonstration.

---

## 28. Technical Positioning

PetDressed should be presented as an explainable wardrobe-planning system that combines:

* interactive computer vision;
* asynchronous inference pipelines;
* multimodal embeddings;
* relational and vector persistence;
* discrete constraint optimization;
* weather-aware planning;
* full-stack product design.

The strongest technical differentiator is not automatic garment classification alone. It is the integration of imperfect computer-vision output, user correction, structured garment state, and explainable constraint-based planning into one coherent product.
