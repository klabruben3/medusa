# Medusa

Evidence routing now returns source IDs and categories only. Python copies the
original section text, including table formatting, into the assembly context.
The model no longer has to reproduce exact quotes. Coverage still requires one
decision for every supplied ID; unknown/duplicate IDs are rejected. Failed retries
log a safe reason code and return `evidence_classification_failed`, not a claim
that the document is unclear. Retaining whole selected sections may still reach
the existing assembly token budget; that limit remains explicit.

## Revised extraction path (September 30)

The default pipeline now reads every normalized section in bounded batches, extracts
verbatim academic evidence, verifies quote provenance and batch coverage, and then
assembles the Module through identity/grading/calendar schemas and semantic validation.
This replaces top-k retrieval in the default path. Voyage and Chroma credentials are
no longer required; the legacy retrieval implementation and its tests remain available.
Small documents bypass fact selection and pass all sections directly to the workers.
For historical retrieval tests only, also install `requirements-legacy.txt`; the
Docker server no longer installs Voyage or Chroma.

Model routing defaults:

| Stage | Groq model | Maximum output tokens |
| --- | --- | --- |
| Evidence extraction | openai/gpt-oss-20b | 2200 |
| Identity | openai/gpt-oss-20b | 1200 |
| Grading | openai/gpt-oss-120b | 2500 |
| Calendar | openai/gpt-oss-20b | 1200 |

`GROQ_EVIDENCE_MODEL`, `GROQ_IDENTITY_MODEL`, `GROQ_GRADING_MODEL`, and
`GROQ_CALENDAR_MODEL` override individual stages. An existing `GROQ_MODULE_MODEL`
overrides all unspecified stages: remove it to use the new defaults, or set each
stage explicitly. Only configure models supporting Groq JSON-schema responses.
The implementation uses best-effort structured output plus local validation.
Grading failures get one evidence-grounded repair attempt. Participation component
weights must total 100%; incomplete or contradictory rules are rejected, not invented.

`GROQ_TPM_BUDGET` defaults to 8000. Requests reserve estimated prompt/schema tokens
plus maximum output tokens and leave 500 tokens of headroom. The estimate is a
UTF-8-based approximation, not the model's exact tokenizer. A per-model sliding
window schedules requests; explicit 429 retries also reserve tokens. Provider 413
is distinguished from a confirmed context-window error. Oversized assembly requests
fail explicitly instead of silently dropping facts. Do not increase the budget
beyond the account's actual limit. External requests using the same account are
not visible to this local limiter; provider rejections still need handling.

Academiq now uses `POST /extractions` (multipart `files`, Supabase bearer token),
which returns HTTP 202 and `{jobId,status}`. It polls authenticated
`GET /extractions/{jobId}` for `processing`, `completed` with `{result}`, or `failed`
with `{error: {detail,code,status}}`. Only the owner can retrieve a job. Quota is
charged at submission, never on polling. The old `/process-documents` synchronous
endpoint remains compatible for old clients, with its original 240-second deadline.

Jobs run for at most 20 minutes; completed results are ephemeral and expire within
30 minutes. Uploaded temporary files close on success, failure, timeout or cancellation.
Jobs/results do not survive server restarts. Keep one process/instance for this
deployment (`WEB_CONCURRENCY=1`, `MAX_CONCURRENT_EXTRACTIONS=1`); multiple replicas
need a shared job store, queue and rate limiter before enabling them. Keep the browser
page open while processing. The browser retains selected files when an error occurs.

Deploy Medusa first, then Academiq. Existing Render services may require setting the
environment values manually; committing render.yaml alone does not establish that
the dashboard service is managed by a Blueprint.

Coverage checks prove every section was submitted and returned quotes exist in the
source; they do not prove the model captured every relevant fact. User review remains
required. No second provider is enabled or sent documents automatically. A vision
provider still needs representative scan/table evaluation and explicit configuration.

The original architecture notes below describe the previous retrieval implementation;
the revision above is authoritative for the default endpoint behavior.

Academiq's existing FastAPI document-to-module service. Extraction returns an
unsaved draft; only the user's explicit save in Academiq's ModuleEditor creates
or updates a Supabase user_modules row.

## Flow

```
Academiq File objects + Supabase access token
  → multipart POST /process-documents
  → verify registered user + existing consume_ai_quota RPC
  → validate files → native PDF text / tables / selective OCR / DOCX
  → ordered blocks with source, page, type, origin and position
  → private in-memory Chroma collection + Voyage embeddings
  → identity / grading / calendar retrieval
  → delete collection in finally
  → three focused Groq calls → deterministic merge + validation
  → {module, warnings} → user review → existing editor save
```

Medusa does not expose permanent file storage or accept browser paths/URLs.
Academiq's separate R2 `{key,url}` upload flow serves profile/support uploads;
extraction preserves the existing temporary multipart contract. Starlette may spool
large uploads to temporary files during a request; request cleanup closes/deletes
them on completion or failure. Chroma has no persistent path, uses a unique
collection per extraction, and disables its analytics telemetry. No source text,
embeddings, OCR output or documents are saved by the extraction service.

Voyage receives document blocks for embeddings and Groq receives relevant retrieved
blocks. Provider processing/retention terms still apply; local deletion is not a
promise about third-party retention. No real student documents are used in tests.

## API

`POST /process-documents` uses multipart fields named `files` and
`Authorization: Bearer <Supabase access token>`. The token is verified against the
configured Supabase project and the existing per-user AI quota is consumed. Anonymous
users are rejected. CORS is not authentication. `GET /` is a public health check.

Success returns `{module: <camelCase Module draft>, warnings: string[]}`.
`module.id` is empty; scores/completion and pin state cannot be imported.
Errors return `{detail: <safe message>, code: <stable category>}`. Categories include
unauthorized, account_limit, unsupported_file, empty_document, encrypted_pdf,
ocr_failed, file_too_large, conflicting_sources, invalid_output, invalid_grading,
provider_error, rate_limited, timeout and processing_error. No validation input
values, internal paths or exception traces are returned.

Limits: 10 files, 50 MiB/file, 100 MiB combined, 100 PDF pages, 180,000 extracted
characters, 12,000 characters per intact block, 48,000 characters per worker context,
25 million pixels per raster image. Oversized structured tables/contexts fail rather
than being silently truncated. Multipart parsing also bounds actual streamed bytes.

## Document handling

PDF pages use pdfplumber native extraction. Table cells stay in ordered row arrays,
including empty cells; their text is excluded from prose. Pages lacking usable text
use Tesseract. Mixed pages OCR relevant image regions, skipping small decorative
assets and full-page backgrounds already covered by native text. Native prose is
conservatively sentence-split; headings, lists, math and structured metadata remain
intact. OCR column layouts are retained as table blocks when detectable; this is
heuristic layout preservation, not guaranteed scanned-table cell recognition.

PNG/JPEG use the same OCR normalization. DOCX paragraphs, tables and embedded images
remain supported; page 0 means page number unavailable. Source order is approximate
for complex multi-column layouts and DOCX embedded images. Bilingual text is retained.

## Workers and models

Worker schemas are selected from `app/types/schema.py:Module` in `ai/partials.py`:

* Identity: module code/name and teaching contacts/groups.
* Grading: assessments (including their dates), formula references, pass requirements,
  final-mark split, hasExam and exam papers. Linked facts remain in one worker.
* Calendar: semester, recess and exam-opportunity dates.

The frontend source of truth remains Academiq `types/index.ts`. `Module` includes
its optional `dataNote`; application-owned fields never come from a worker.
Each worker has a small purpose-specific retrieval query group. Results retain
provenance and neighboring context. Only normalized exact duplicates are removed;
similar passages with different numbers/dates must remain available as conflicts.
Retrieval cannot guarantee exhaustive recall; the UI explicitly requires review.

The default Groq model remains `openai/gpt-oss-20b`. All workers inherit
GROQ_MODULE_MODEL unless their own override is configured. The unused legacy formula
worker's `openai/gpt-oss-safeguard-20b` remains untouched; it is not silently adopted.
Voyage's default remains `voyage-4-lite`. Workers execute sequentially to avoid bursts;
Groq has one SDK retry and workers have one schema-repair attempt. Inconsistent
merged academic rules fail explicitly rather than being fixed by inventing facts.

Legacy `categorize.py`, `chroma_connection.py`, `workers.py` and language-filtering
helpers are not called by the endpoint. In particular, the shared cloud
`document_chunks` collection and its CHROMA_* credentials are not used. Existing
cloud data is not deleted by this change.

## Configuration and deployment

Required Medusa environment variables:

```
GROQ_API_KEY=...
VOYAGE_API_KEY=...
SUPABASE_URL=https://<the-same-project-as-academiq>.supabase.co
SUPABASE_ANON_KEY=<publishable-or-anon-key>
CORS_ORIGINS=https://<academiq-origin>,http://localhost:3000
```

Optional: GROQ_MODULE_MODEL, GROQ_IDENTITY_MODEL, GROQ_GRADING_MODEL,
GROQ_CALENDAR_MODEL, VOYAGE_EMBEDDING_MODEL, OCR_LANGUAGES, TESSERACT_CMD,
MAX_CONCURRENT_EXTRACTIONS (default 2; Render blueprint uses 1).
No service-role key is required. Quotas are shared with Iris using the existing
`consume_ai_quota` migration/RPC. Per-instance admission also allows only one job
per user; multiple instances still share the database quota.

Academiq requires NEXT_PUBLIC_ACADEMIQ_API_URL pointing to this service; its import
entry point stays disabled in production without this configuration. Development
defaults to http://localhost:3001. Neither repository's local secrets are changed.

`render.yaml` selects the existing Dockerfile, which installs Tesseract and English/
Afrikaans language data. Set secrets in Render, rebuild Academiq with its public API
URL, and verify OCR in the deployed image. Chroma is used as bounded in-process
working memory, not a persistent production database; size/concurrency limits may
need lowering on a small Render plan. No service was deployed by this change.

```
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3001
python -m unittest discover -s tests -p "test_*.py"
python -m tooling.smoke_generation
```

The test suite mocks external providers but exercises real PDF parsing and local
Chroma insertion/query/deletion, concurrent isolation, cancellation and invalid output.
The smoke tool sends synthetic facts to Voyage and Groq and requires both keys.
Structured stage logs contain counts, durations and random job IDs only.

Cancellation waits for any synchronous document/retrieval operation to release its
resources before returning. A 240-second timeout can therefore include extra cleanup
time (including a bounded in-flight provider/OCR operation). Collection cleanup runs
before generation, so model errors, invalid JSON and timeouts cannot leave a collection.
An abrupt process termination also loses the in-memory collection; local upload-temp
cleanup after an OS/container failure is the hosting runtime's responsibility.
