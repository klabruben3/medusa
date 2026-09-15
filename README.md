# Medusa

**Medusa is Academiq's document-to-module extraction service.**

It processes university study guides and related academic documents and converts their contents into a structured **Academiq Module draft** that can be reviewed before being saved by the frontend.

Medusa exists to bridge the gap between:

```text
University document
        ↓
PDF / DOCX / image
        ↓
Academic information
        ↓
Structured Academiq module
```

The service does **not** write student academic records directly.

Its responsibility ends at producing a validated, unsaved module draft and identifying information that still requires human review.

---

## Purpose

University module information is often distributed through documents designed for humans rather than software.

A study guide may contain:

* Module metadata
* Lecturer information
* Contact details
* Student groups
* Assessment schedules
* Assessment weights
* Participation formulas
* Pass requirements
* Examination information
* Important academic dates
* Tables
* Bilingual content

Medusa converts that information into the structured format expected by Academiq.

The goal is not merely to extract text.

The goal is to understand enough of the document's academic structure to construct a usable module definition.

---

## Processing Flow

At a high level:

```text
Uploaded documents
        │
        ▼
File validation
        │
        ▼
Text / table / OCR extraction
        │
        ▼
Combined document context
        │
        ▼
LLM structured extraction
        │
        ▼
Schema + academic validation
        │
        ├── valid facts
        │
        ├── missing information
        │
        └── review warnings
        ▼
Unsaved Academiq Module
        │
        ▼
User review
        │
        ▼
Academiq frontend saves module
```

Medusa deliberately keeps **extraction** separate from **persistence**.

---

## API

### `POST /process-documents`

Processes one or more files describing a **single academic module**.

The request uses `multipart/form-data` with one or more `files` fields.

Example response:

```json
{
  "module": {
    "id": "",
    "code": "MTHS121",
    "name": "Mathematics 121"
  },
  "warnings": [
    "Examination date could not be determined from the supplied documents."
  ]
}
```

The returned module uses Academiq's camelCase module structure.

`id` is intentionally returned as an empty string.

Medusa does not create the corresponding `user_modules` record. The Academiq frontend saves the reviewed draft and Supabase assigns the persistent database UUID.

---

## Supported Documents

Medusa currently accepts:

* **PDF**
* **DOCX**
* **PNG**
* **JPEG**

Multiple files may be uploaded when they describe the same module.

For example:

```text
Study guide.pdf
Assessment plan.pdf
Exam information.pdf
```

may be processed together if they all belong to the same module.

A single request should **not** contain documents for unrelated modules.

---

## OCR

Image-based documents and scanned PDF content require OCR.

Medusa uses **Tesseract** for local optical character recognition.

The deployment environment must provide:

* The Tesseract executable
* Required language data

English OCR is the default.

Additional configured languages require their corresponding language packs.

For example:

```text
OCR_LANGUAGES=eng+afr
```

requires both English and Afrikaans Tesseract data to exist on the host.

If OCR is required but unavailable, Medusa returns an error rather than pretending that unreadable content was successfully extracted.

This is intentional.

> **Missing text is safer than fabricated academic information.**

---

## Extraction Principles

Medusa follows several rules intended to make generated module data safer and easier to review.

### Never invent student data

The service never creates:

* Student marks
* Completion state
* Assessment results
* Personal academic progress

Medusa extracts **module structure**, not student performance.

---

### Missing information remains missing

If a date, location, lecturer detail, or similar value cannot be determined reliably, it should remain empty and generate a review warning where appropriate.

The model should not create plausible-looking replacements.

---

### Academic rules must be explicit

Important grading information should only be represented when supported by the source documents.

This includes concepts such as:

* Assessment weights
* Minimum participation requirements
* Dropped assessments
* Required assessment counts
* Category weighting
* Examination requirements
* Final-mark formulas

A phrase such as:

```text
Best 3 of 4 tests count
```

has a very different meaning from:

```text
Complete at least 3 tests
```

The extraction layer must preserve that distinction.

---

### Zero is different from missing

Academic values must preserve semantic differences between:

```text
0
```

and:

```text
unknown / absent
```

This is particularly important once extracted module structures reach Academiq's calculation systems.

---

### Human review is mandatory

A successful extraction means:

> **The module draft passed Medusa's structural validation.**

It does **not** mean:

> **Every extracted fact is guaranteed to be correct.**

LLM-based extraction can make mistakes.

Users must review the resulting module before saving it into their academic workspace.

---

## Validation

Medusa validates extracted output before returning it to Academiq.

Important academic information that is required to construct a valid grading model may cause extraction to fail when it cannot be established safely.

Less critical missing information can remain empty and produce warnings instead.

Conceptually:

```text
Extracted information
        │
        ├── Required + valid ────────► accept
        │
        ├── Optional + missing ──────► warning
        │
        └── Required + unreliable ───► reject
```

This prevents malformed grading structures from silently entering Academiq.

---

## Request Limits

The service enforces input limits before generation.

Current limits include:

* Maximum **10 files**
* Maximum **50 MB per file**
* Maximum **100 MB combined upload**
* Maximum **100 pages per PDF**
* Maximum **180,000 extracted characters**

Requests exceeding these limits are rejected rather than silently truncated.

Academic extraction depends on having the full relevant context. Quietly removing part of a study guide could create a structurally valid but factually incomplete module.

---

## Tables & Bilingual Content

Extracted content is not limited to plain paragraphs.

Relevant source material can include:

* Tables
* Structured assessment schedules
* Mixed formatting
* English content
* Afrikaans content
* Bilingual academic material

The complete extracted context is supplied to the module-generation stage within the request limits.

---

## Generation

Structured module extraction currently uses **Groq**.

Required environment configuration:

```text
GROQ_API_KEY
```

The generation model can optionally be configured with:

```text
GROQ_MODULE_MODEL
```

Default:

```text
openai/gpt-oss-20b
```

The generation layer is responsible for transforming extracted document content into Academiq's module schema.

---

## Legacy Retrieval Pipeline

Earlier versions of Medusa explored a more elaborate document-processing architecture using:

* VoyageAI embeddings
* ChromaDB
* Document chunk categorization
* Retrieval-based extraction

Those helpers may still exist in the repository.

They are **not part of the current `/process-documents` production path**.

The active extraction path currently depends primarily on:

```text
Document extraction
      +
Local OCR when required
      +
Groq structured generation
```

The older Voyage/Chroma work remains useful as an experiment and may become relevant again if Academiq later needs retrieval across larger academic document collections.

---

## Academiq Integration

Medusa is a supporting service for Academiq rather than a standalone student application.

The frontend points to the deployed service using:

```text
NEXT_PUBLIC_ACADEMIQ_API_URL
```

For local development, the expected backend origin defaults to:

```text
http://localhost:3001
```

The frontend should treat Medusa's output as a **draft**.

The expected product flow is:

```text
Upload documents
      ↓
Medusa extraction
      ↓
Review module draft
      ↓
User corrects anything necessary
      ↓
Save to Academiq
```

Medusa never bypasses this review step by writing directly to student records.

---

## Service Boundary

Medusa owns:

* Document validation
* Text extraction
* OCR
* Academic information extraction
* Module-schema construction
* Extraction warnings
* Structural validation

Medusa does **not** own:

* Academiq authentication state
* Student marks
* Student progress
* Module persistence
* Template administration
* Assessment synchronization
* Academic calculations
* Iris conversations

Keeping this boundary narrow allows the extraction service to evolve independently from the main Academiq application.

---

## Technology

The service is built primarily with:

* **Python**
* **FastAPI**
* **Uvicorn**
* **Groq**
* **Tesseract OCR**
* PDF and DOCX extraction tooling

Legacy experiments also include:

* **VoyageAI**
* **ChromaDB**

---

## Local Development

Install the required Python dependencies and start the API with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 3001
```

At minimum, configure:

```text
GROQ_API_KEY
```

Optional service configuration includes:

```text
GROQ_MODULE_MODEL
CORS_ORIGINS
TESSERACT_CMD
OCR_LANGUAGES
```

If Tesseract is not available through the system `PATH`, `TESSERACT_CMD` should point to the executable.

---

## Testing

Run the offline test suite with:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Development/test dependencies are defined separately in:

```text
requirements-dev.txt
```

A live generation smoke test is also available:

```bash
python -m tooling.smoke_generation
```

Unlike the offline tests, the smoke test makes a real request to the configured Groq provider and therefore requires a valid API key.

---

## Deployment

Medusa can run as a separate service from the Academiq frontend.

The current deployment architecture keeps:

```text
Academiq
Next.js / Vercel
       │
       │ HTTP
       ▼
Medusa
FastAPI service
       │
       ├── Document extraction
       ├── Tesseract
       └── Groq
```

The deployment environment must provide Tesseract separately when OCR functionality is required.

For platforms such as Render, this may require a container or system configuration that explicitly installs the Tesseract executable and the required language packs.

OCR should be verified in the deployed environment before document uploads are enabled for users.

---

## Current Status

Medusa is an active Academiq subsystem, but document import is still treated as a **deferred production feature** in the main application.

The extraction pipeline exists and continues to be developed, but Academiq should not expose document import as a fully trusted workflow until:

* OCR works reliably in production
* Academic extraction is sufficiently consistent
* Validation covers the required module structures
* Failure states are clear
* Review workflows are reliable
* Real university documents have been tested across enough formats

The objective is not simply to make document import work.

The objective is to make it **safe enough that students can trust the academic structures it produces**.

---

## Design Principle

Medusa is built around one principle:

> **Extract what the document says. Preserve what is unknown. Never make academic uncertainty look like certainty.**

A module can always be corrected during review.

A confidently fabricated grading rule is much harder to detect.
