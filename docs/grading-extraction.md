# Grading extraction compatibility

The extraction workers preserve module-code references from original document sections for identity, including references in assessment and examination paragraphs. Prerequisite codes remain evidence, rather than becoming the current module by default.

An absent or wholly unknown participation formula may be linked to explicit individual non-exam assessment weights only when those weights total 100%. Existing formula weights, pool rules, incomplete plans and unknown assessment weights are not rewritten. Maximum marks and all other semantic checks still apply. Conditional bonuses belong in the existing `dataNote` field; they are not automatically calculated as fixed weights. Missing final exam splits remain unknown.

Failed synchronous responses and account-owned queued jobs may include an additive `issues` array with static `{code, message}` explanations. These explanations contain no source text or generated identifiers. Existing clients can continue reading `detail` and `code`. The health endpoint reports `extractionVersion: 2` for deployment verification.

No database migration, persisted-module format change, new provider or additional model call is required. Extracted modules remain unsaved drafts that users must review before saving.
