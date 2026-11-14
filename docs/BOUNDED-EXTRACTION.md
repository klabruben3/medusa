# Bounded extraction: implementation and acceptance

Status: experimental engine alongside the existing pipeline. No hosted route or
deployment setting selects it. Existing academic records, Module API and default
processing remain intact. Owner authorization permits this redesign and controlled
institutional NWU tests; unrestricted hosted audience review is separate.

## Why change the pipeline

The old path classifies source blocks, then sends overlapping original material to
identity, grading and calendar workers. MTHS111 completed classification but its
selected contexts could not fit the request budget. Shortening prose alone cannot
solve repeated large inputs. The alternative extracts bounded, source-linked facts
once and assembles them in code; it does not ask a final model to rewrite a module.

## Implementation sequence and exit criteria

1. **Measure and plan before spending.** Use the actual provider request-format
   builder for schema, prompt, framing and output-reservation estimates. Retain the
   existing 8,000-token model budget and 500-token admission margin. Group repeated
   filenames without changing source text or order. Record model-reported usage
   separately from conservative estimates. Exit: every planned request fits and
   the whole job is admitted before its first provider call.
2. **Extract bounded facts.** The ledger reads every supported source section,
   rather than classifying and resending it to three owners. The initial model is
   the existing supported GPT-OSS 20B with low reasoning, strict structured output
   and a 2,600-token completion allowance. Field names and record kinds are
   allowlisted. Exit: all section IDs are covered, every retained quote exists in
   its block and every numeric value appears in cited wording. The model supplies
   block/row pointers; the server retrieves original text. Strict JSON parsing
   rejects duplicate keys before values can disappear. Coverage does not
   by itself prove all facts were extracted: source-fact acceptance remains needed.
3. **Assemble deterministically.** Type-check values against existing Module field
   definitions. Equal values deduplicate while retaining all references; competing
   values remain candidates, with no last-write-wins behavior. Formula references
   and IDs are constructed in code. Reuse existing grading, range, identity and
   calendar checks. Exit: accepted output satisfies the existing unsaved Module
   contract and source acceptance facts; incomplete proposals retain review issues.
4. **Complete review handling.** Missing marks stay absent in the proposal; they
   do not become an assumed 100. Unresolved required values/contradictions withhold
   an accepted result. The experimental proposal is not yet a hosted UI response.
   Exit: a versioned review UI can show source-linked issues, accept permitted owner
   corrections, revalidate the whole proposal and prevent saving invalid grading.
5. **Prove representative accuracy and efficiency.** Repeat real APPM122 and MTHS111
   runs, including group dates, optional source-scope differences and missing marks.
   Compare checked facts, total accepted-response tokens, rejected attempts and
   elapsed time with the existing path. Include genuine conflicts and adverse input
   fixtures. Exit: no invented facts or silently lost conditions in the chosen
   corpus, with explicit unsupported cases; current-code real proof is required.
6. **Integrate and recover.** Connect the accepted engine/review contract to the
   authenticated job journal, owner-bound checkpoints and existing note persistence.
   Verify uploaded sources, save/reopen and process-restart recovery through real
   authenticated flows, plus actual hosted OCR. Exit: no cross-account result
   access, duplicate writes or lost review decisions after interruption.
7. **Promote deliberately.** Keep the old engine available until the new path meets
   these gates. Deploy compatible backend/frontend changes, verify the deployed
   source/version and monitor validation failures and token usage. This is distinct
   from mobile/desktop signing, notification and updater acceptance.

## Budget and cache safeguards

`fact_ledger.py` caps a job at 32 reserved attempts and 120,000 reserved tokens,
including a conservative two-attempt allowance for each provider invocation.
Malformed output can split a batch only twice; a single structurally unverifiable
block stops instead of retrying indefinitely. Unsupported individual claims are
quarantined without buying the same valid fields again. Every quarantine blocks
an accepted result pending source review. No account quota or paid plan is changed.
These are bounded upper estimates, not a promise of actual token consumption.
HTTP-200 response usage is recorded before local validation, including rejected
responses. Rejected HTTP-400 generation billing is not available as usage proof.
Daily quota exhaustion stops immediately rather than retrying prematurely.

The local runner stores private batch checkpoints scoped by review reference,
credential digest, explicit owner scope, model, related source hashes and exact
request fingerprint (prompt, schema, output options and engine version). An
unrelated source change need not invalidate a batch. Validation implementation
hashes do not invalidate identical requests: loaded batches are always revalidated
under current coverage, type and source-role rules before reuse. A cache hash is
not authorization; hosted storage still needs verified owner identity and access control.
This local cache is not a hosted multi-user cache or proof of authenticated recovery.
No keys, raw documents, full prompts or outputs enter ordinary logs or this repo.

## Current measurements

The initial four-request plan did not succeed. Live tests exposed schema repair
ambiguity, a Groq integer/number-union schema restriction, truncation and missing
domain vocabulary. Those defects were addressed, but no complete new-engine run
has yet passed source acceptance.

Version 1 indexed inputs covered 145 MTHS111 sections in six requests. One real
120B response reported 3,162 input / 1,728 output tokens. Its later structural replay
was not factual acceptance: manual review found invented dates, copied lecture
times, unsupported exam/semester claims and eight duplicate JSON keys. Historical
v1 checkpoint evidence is superseded for template acceptance, not erased.

Version 2 adds deterministic merged-table context, English/Afrikaans date handling,
source-row identity checks, conservative semester/exam checks and explicit tutorial
session semantics. It recovers date context across table chunks while preserving
every original cell. Ambiguous weekday/date combinations remain candidates for
review. Tutorial windows are exposed separately from exact test starts.

The version-2 archived-source plan is seven batches, with first-request estimates
7,327 / 7,363 / 7,336 / 7,273 / 7,207 / 7,373 / 5,375 tokens. Repair estimates are
also below 7,500. This extra context currently costs more than the version-1 plan;
no net token saving or better full-template accuracy is claimed. Both evaluated
models reached their daily quota during live tests; no plan upgrade was made.

Ten zero-provider checks on the actual MTHS111 timetable pass: all eight Group 1
weekly-test dates and their own 16:15–17:45 tutorial windows, the Group 2 Test 4
date ambiguity, and rejection of the duplicate-key historical response. These are
parser/rejection checks, not a complete generated module. Focused tests additionally
cover quarantine, typed values, checkpoint scope and retained valid fields.

Latest full local suite: 168 tests, 164 passed, four optional legacy Chroma skips.
Offline current-version checkpoint verification reused zero historical v1 batches;
all seven remain pending. Planning reserved 49,254 first-attempt estimated tokens
or 100,154 with the conservative retry allowance. These include reserved output,
not actual usage or pricing. No live request was sent by either verification.

## Completion boundary

Steps 1–3 have experimental implementations and focused tests; they have not met
whole-corpus model acceptance. Step 4 has a reviewable proposal/issue contract but
still needs correction/revalidation and the hosted UI. Steps 5–7 remain gated:
fresh representative model runs and actual cost comparison, authenticated durable
integration/restart/save/reopen tests, hosted OCR and compatible deployment. The
hosted job timeout must also accommodate bounded multi-batch work. Neither local
checkpoint replay nor a healthy journal proves these flows. Keep the current
engine in service until these gates pass; this architecture is not yet promoted.

Official implementation references: [Groq structured output](https://console.groq.com/docs/structured-outputs),
[rate limits](https://console.groq.com/docs/rate-limits) and
[API parameters](https://console.groq.com/docs/api-reference). Schema compliance is
not evidence of factual correctness; the manual acceptance corpus is mandatory.
