# Controlled NWU extraction acceptance

The owner authorized a local test review for three APPM122 course documents from
the supplied NWU corpus. The private record binds the exact original file hashes,
the existing API credential by digest, the official Groq API origin and a 24-hour
expiry. It covers institutional assessment material and professional contacts,
with no individual student records. No API key, source text or generated draft is
stored in this repository. The CLI-only context cannot be enabled by an HTTP
request or by copying its reference into hosted review settings.

The review acknowledges standard retention/US processing; it does not attest to
Zero Data Retention or independently verify organization/project settings. It
does not approve the hosted service's broader audience or change its review flags.
Terms consulted: [Groq data handling](https://console.groq.com/docs/your-data) and
[Groq trust FAQ](https://trust.groq.com/faq?s=9pcm46fyh5sypzqgtfto).

## Findings and resulting changes

Real provider calls exposed transport failures, incomplete strict-schema output,
false conflict reports, and omitted grading facts. Requests now use a strict
schema on the supported GPT-OSS models, bounded schema/transport recovery, and
low reasoning effort within the existing completion allowance. Each attempt is
admitted against the configured model budget. No quota or billing limit changed.
Oversized grading requests split owned fields while retaining original evidence;
assessment handoff metadata excludes weights so placeholders cannot become source
facts. Candidate contradictions receive one verification pass; genuine unresolved
contradictions still block the draft.

Short source continuations remain attached to selected grading clauses. A narrow
source linker retains explicit equal final-mark weights and quoted conditional
supplement clauses. It never assumes a 50/50 default, silently overwrites a
conflicting formula, or converts conditional prose into executable arithmetic.
Optional local callbacks allow private evidence/worker diagnostics; hosted callers
do not persist raw worker output through these callbacks.

## Evidence and limits

Run `20261114T151650340243Z` reparsed the three original PDFs and reused previously
classified evidence. The real identity/grading/calendar workers and semantic repair
produced an unsaved draft passing all 21 manually established source-fact checks.
Studio's actual runtime parser accepted it with no personal scores/completion.
Checks include both class tests, the September semester-test range, maximum marks,
participation contributions, admission/exam/pass thresholds, explicit 50/50 final
split, exam maximum and conditional supplement notes. The initial assembly had
unknown weights on extra exam records; bounded semantic re-extraction resolved it.
Earlier failed runs remain failures; they are not counted as successful imports.

Manual review subsequently found an untested calendar defect: that draft used
the general exam-period start as semester end. It is not a fully accepted draft.
Acceptance now has 25 checks, including unknown semester/module-exam dates,
the explicit recess range and exam duration. Calendar extraction requires a verbatim block anchor with an explicit
semester-end label and matching date; missing/invalid support leaves the date
blank with a review warning. Exam starts, last tests, invented quotes, wrong block
IDs, mismatched dates/years and negated/relative end statements are rejected.
Specific exam dates additionally require a module-scoped exam slot; general
university examination periods cannot become a scheduled module exam.

This is one successful grading/assessment worker run, not general or repeated-run reliability.
A fresh full classification run is pending at this checkpoint. No academic module
was saved and no authenticated hosted import, OCR acceptance or browser recovery
is claimed. Across the wider 19-document corpus, 14 normalized locally, three need
unavailable local OCR, one disallows encrypted extraction, and one exceeds the
existing page limit. Those limits were not bypassed.

All 72 focused regression tests passed, covering calendar source anchors, review scope/expiry/key/origin,
bounded retries, evidence coverage/continuations, source links, grading budgets,
validation, durable jobs and account isolation. See the companion Academiq change
for `dataNote` persistence and review UI; existing Studio otherwise discarded those
notes on save/reload. Deployment and owner source review remain distinct gates.
