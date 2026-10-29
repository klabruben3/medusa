# Academic document completion journal

The existing extraction request and in-memory polling path remain available. Set `ACADEMIQ_DURABLE_JOBS=true` only after deploying the Academiq document endpoints and applying `20261023094915_native_document_and_release_events.sql` in its Supabase project.

The journal reuses `SUPABASE_URL`, `SUPABASE_ANON_KEY` and the authenticated request's bearer session. The URL and anon key are public client configuration; the user's bearer session is sensitive and transient. No Supabase service key or FCM credential belongs in Medusa for this integration.

At admission Medusa creates a random per-job completion capability, stores only its hash through the authenticated RPC, and keeps the capability in server memory. Admission retries use the same job ID and capability hash. The RPC derives ownership from the verified session, rejects anonymous sessions, limits active/rate admissions and does not consume the existing AI usage quota a second time.

On terminal processing, Medusa posts a bounded result to the fixed HTTPS Academiq completion endpoint. Its capability cannot read a result, admit a job or change another job. It must never be logged or returned to the browser. Completion has bounded retries, stops on a rejected/expired capability, and logs only a stage and job identifier. The browser is explicitly told whether durable admission succeeded; failure preserves ordinary processing and tells the user to keep the screen open.

Results up to 256 KiB are recoverable for seven days. Larger results continue through normal polling without truncation, while the journal records that the result was not retained. A generic terminal notice opens authenticated result review; it contains no document content, grades or private module details. Saving an extracted module remains an explicit user action through the existing editor.

The journal persists completion state, not uploaded source files or a resumable extraction task. If the service restarts before completion, its source-file handles and capability can be lost. After the 22-minute deadline, the durable scheduler marks the job **unconfirmed**, explaining the interruption without asserting that the extraction failed or removing an already saved module. Ensure the Academiq delivery scheduler is configured and active before promising background notices. Its activation is separate from this feature flag.

Deployment order: database migration → Academiq web/API → Medusa code → enable the flag → controlled authenticated extraction/notification/recovery test. Roll back by disabling the flag; existing clients and ordinary extraction continue working. Do not drop retained results or academic tables as a rollback step.

The public health endpoint retains `status`, `service` and `extractionVersion`, adding `documentJournalVersion: 1` and the non-secret boolean `durableJobsEnabled`. Verify these fields against the exact live Render commit after deployment; an HTTP 200 from older code alone does not establish journal readiness. Existing Render services must set the flag in their service environment; the Blueprint default remains off.

Keep the existing Groq processing-review gate intact. Journal activation does not approve a provider review, enable Groq, change its account credentials or guarantee push delivery. A missing review must remain an explicit processing limitation; a synthetic failure/callback check is not evidence of a successful model extraction.

Run the focused tests with `python -m unittest discover -s tests -p test_job_journal.py -v` from the Medusa project. This verifies HTTP behavior with isolated fixtures; it does not prove a deployed callback, push display or Android tap.
