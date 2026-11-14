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
   and a 1,800-token completion allowance. Field names and record kinds are
   allowlisted. Exit: all section IDs are covered, every retained quote exists in
   its block and every numeric value appears in cited wording. Coverage does not
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
Malformed output can split a batch only twice; a single unverifiable block stops
instead of retrying indefinitely. No account quota or paid plan is changed.
These are bounded upper estimates, not a promise of actual token consumption.
Usage from successful provider responses excludes any failed-attempt billing.

The local runner stores private batch checkpoints scoped by review reference,
credential digest, model, exact input, prompt, schema and implementation fingerprint.
Loaded batches are revalidated for coverage, types and source quotes before reuse.
This local cache is not a hosted multi-user cache or proof of authenticated recovery.
No keys, raw documents, full prompts or outputs enter ordinary logs or this repo.

## Current measurements

The initial MTHS111 plan covers 145 sections in four requests, each below 7,500
estimated tokens including reserved output. First-attempt reservations total 29,436;
the conservative one-retry-per-request bound is 58,872. Source JSON decreased from
50,213 to 38,789 bytes through lossless filename grouping/compact encoding. These
are planning results, not proven model accuracy or observed token savings.

The full initial implementation suite ran 142 tests: 138 passed and four optional
legacy Chroma tests were skipped. Focused cases cover lost/duplicate block coverage,
foreign/invented quotes, numeric grounding, forbidden progress fields, strict field
types, budget preflight, verified cache reuse, missing maxima and competing rules.

Official implementation references: [Groq structured output](https://console.groq.com/docs/structured-outputs),
[rate limits](https://console.groq.com/docs/rate-limits) and
[API parameters](https://console.groq.com/docs/api-reference). Schema compliance is
not evidence of factual correctness; the manual acceptance corpus is mandatory.
