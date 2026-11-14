# NWU document acceptance checkpoint — 14 November 2026

The owner authorized the Desktop sos/skolo assessment documents. Local normalization covered 19 selected course documents: 14 normalized, three need OCR absent locally, one is extraction-disallowed/encrypted and one exceeds the existing 100-page limit. This is not 19 successful module imports.

## Output contract and source precedence

The live Academiq schema stores course structure in `user_modules`/`module_templates` and personal scores/completion separately in `assessment_statuses`. Medusa must return the existing `ExtractionResult` containing an unsaved client-shaped `Module` and warnings. IDs remain unsaved; processing does not create a user module. Direct individual assessment weights and pooled-category completion/drop rules are both supported. Participation admission, final pass thresholds and final exam weights are separate facts.

Read-only inspection found templates for four of the selected NWU courses. Existing templates establish the app contract, not source correctness. Visual inspection of page 1 of the owner's MTHS121 planning PDF confirms Test 9 is in the 6 October 2026 continuation row; the existing template places it on 22 September. No stored academic record was edited. Document conflicts require review rather than silently copying a template or choosing an inferred date.

## Evidence-context correction

Two regression checks failed before the correction: timetable row adjacency was lost at section boundaries, and the source course-year heading could be routed only to identity. Table sections now retain one previous source row when it fits the existing byte bound; size-retry table partitions also overlap. Course-code/year headings are copied from original source into all worker contexts. The worker prompt distinguishes upload metadata from source years and repeated context from additional assessments.

The focused evidence, pipeline, grading-link, journal, job and processing-review suite passed 51 tests, including size-retry continuation preservation. Actual splitting/routing checks on the 14 privately normalized documents preserved 619 bounded adjacent table pairs and routed the detected source-year heading to all workers. Classification was a test double; no provider request or document upload occurred. This verifies context preservation, not model interpretation accuracy. Source files and normalized content remain outside the repository.

## Recovery evidence

A live SQL transaction exercised the existing journal functions/RLS with simulated JWT claims for the selected test owner and a synthetic draft, then rolled back. It verified wrong-proof rejection, completion, identical callback retry, rejection of changed retry content, owner draft readback, cross-account read denial, and unchanged saved-module count. This is database-layer recovery evidence; it does not establish real HTTP authentication, browser/process restart recovery or model output. No schema migration or durable academic write was made.

The owner enabled durable jobs and public health confirms it. Hosted unauthenticated upload/admission/lookup requests returned 401. Applicable Medusa provider-account/audience review and an authorized user session are still required for hosted NWU extraction and interrupted/reopened-client acceptance. Do not copy Iris's owner-only review, mint a user session through SQL, or report fixture output as actual model extraction.
