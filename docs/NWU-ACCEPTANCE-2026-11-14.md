# Controlled NWU extraction acceptance

This remains a draft change, not a claim that Medusa is generally reliable or ready
for unrestricted student document processing.

## Review boundary

The owner authorized controlled testing of the supplied institutional NWU course
material. Separate private, expiring records bind the selected APPM122 and MTHS111
files by hash, the existing credential by digest and the official Groq API origin.
They exclude individual student records. The trusted CLI context cannot be enabled
by an HTTP request or by copying its reference into hosted settings. Credentials,
original sources, full worker output and generated drafts remain outside Git.

The review acknowledges standard retention and US processing, without claiming
Zero Data Retention or independent verification of organization/project controls.
It does not approve the hosted service's broader audience or set general review
flags. References: [Groq data handling](https://console.groq.com/docs/your-data),
[Groq trust FAQ](https://trust.groq.com/faq?s=9pcm46fyh5sypzqgtfto).

## Implemented safeguards

- Strict supported GPT-OSS schemas, distinct schema identifiers, explicit field
  ownership, bounded schema/transport recovery and per-attempt budget admission.
  Literal workers use low reasoning effort; grading retains medium. No billing or
  quota was increased.
- Grading splits owned fields when necessary while retaining source evidence.
  Participation formulas own weights; assessment definitions do not independently
  invent weights or progress. Orphan weights and unsupported module codes fail.
- Short source continuations and explicit assessment rows in teaching-plan tables
  reach grading even if the classifier labels them only as calendar evidence.
  Original cells, neighboring rows, source page/block and row indices are retained.
- Narrow source links preserve explicit final splits, conditional supplement prose
  and unambiguous fully year-qualified date ranges. Populated disagreement is not
  overwritten. Conditional prose never becomes invented arithmetic.
- Semester-end and module-exam dates require matching, verbatim source anchors;
  general examination-period starts are not specific module exam slots.
- Exact negative-one placeholders become unset only for known optional nonnegative
  requirements, with review notes. Required marks, weights and thresholds still fail
  validation when unknown. This avoids a full grading repair discarding valid rules
  merely because an optional field was unknown.
- Differing literal numbered class-test study-unit descriptions are preserved in
  review notes and the optional coverage field remains unset. The narrow recognizer
  is not a general contradiction detector; different granularity may be compatible.
  Genuine unresolved worker conflicts still block rather than selecting a winner.

## Real evidence

Two actual worker runs, `20261114T163051010287Z` and
`20261114T171208128461Z`, reparsed the same original APPM122 PDFs and used two
independently classified evidence caches. Each passed 26 checked grading/date facts
and Studio's runtime draft parser. These are evidence-cache replays, not two fresh
end-to-end classifications. One earlier fresh full classification took about 19
minutes and its then-current output failed expanded acceptance. Earlier schema,
identity and semantic failures remain failures.

Manual review subsequently found differing Class Test 2 coverage in the information
sheet and semester plan. The grading evidence had omitted the relevant plan row.
This exposed a gap beyond those 26 checks. Reassembling archived real worker output
with reconciled original evidence and the new deterministic scope review passed
27/27 checks. That reassembly used zero new provider calls and is diagnostic proof,
not a successful generation with the latest code.

The real run including the table fallback, `20261114T173853337849Z`, failed with
HTTP 429 before completion. It is not accepted. Latest-code real generation remains
a gate. A separate MTHS111 real test uses its original planning/general-information
PDFs and an explicit two-page study-guide excerpt (original PDF pages 15–16).
The 173-page original guide remains rejected by the existing 100-page limit; this
is not full-guide support. MTHS111 maxima missing from the selected evidence must
not be invented merely to make a template pass.

## Regression and remaining gates

The full local suite ran 127 tests: 123 passed, four optional legacy Chroma retrieval
tests skipped because that dependency is not installed. The default extraction path
does not use Chroma. Current pipeline fixtures exercise actual field ownership,
source-code verification and schema dispatch rather than obsolete schema names.

No academic module was saved. No authenticated hosted import, actual hosted OCR,
process-restart/browser recovery or device flow is claimed. The wider 19-document
normalization corpus had 14 successes, three local OCR blockers, one document that
disallows encrypted extraction and one over the page limit. Limits were preserved.

Academiq PR 21 adds nullable source-note persistence and the existing editor field;
its database migration and rollback isolation checks passed, but its frontend is
unmerged and undeployed. Medusa PR 5 remains draft and undeployed. Hosted audience
review, current-code real extraction acceptance, representative missing/grouped
assessment handling and authenticated recovery remain distinct acceptance gates.

### MTHS111 observed result

Run `20261114T174311114895Z` finished real evidence classification in about 12
minutes, then failed closed with `request_budget_exceeded` before an identity or
grading completion. Selected context text was 11,631 identity / 22,121 grading /
10,272 calendar characters. No draft was generated. Supporting this representative
three-file case needs bounded context extraction/assembly work; raising a quota or
silently cropping academic evidence is not an accepted fix. The missing MIC/ALEKS
maxima are a separate manually identified source gap, not an observed invented
model result. This run began at `e6bef9c`, before the final scope-review/header
follow-ups, and does not verify those later changes through actual model calls.

Additional zero-provider checks passed on 14 normalized originals, with 619 adjacent
table pairs preserved and the two observed APPM122/MTHS111 routing gaps covered
using calendar-only table classification. Four runner-manifest tests passed for
course/path/type/count boundaries, explicit excerpts and duplicate filenames.
