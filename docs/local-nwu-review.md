# Controlled local NWU acceptance review — 14 November 2026

The owner explicitly authorized creation of the necessary review and use of the supplied NWU documents for extraction testing. The initial reviewed scope is the three course-level APPM122 PDFs in Desktop sos/skolo. Their normalized content was inspected: institutional course/assessment information and professional lecturer contacts, without individual student grades, roster, identifiers or submitted student work. General statements about assessment marks and medical modelling examples are course content, not personal records.

The private local record `local-nwu:2026-11-14-appm122-v1` binds exact original-file SHA-256 hashes, the effective existing credential's digest and a 24-hour expiry. Its credential source is the owner's existing Desktop Medusa configuration; the secret is never copied into reports or source. The organization/project identity and account-specific ZDR controls were not independently verified. This record does not claim otherwise.

## Published processing limits reviewed

- [Groq's data-handling documentation](https://console.groq.com/docs/your-data) describes standard inference handling, possible reliability/abuse retention for up to 30 days, usage metadata collection, US storage and optional account ZDR settings. No ZDR setting is attested here.
- [Groq's published FAQ](https://trust.groq.com/faq?s=9pcm46fyh5sypzqgtfto) states it does not train models on customer data for its own purposes.
- The current [Services Agreement](https://console.groq.com/docs/legal/services-agreement) and [DPA](https://console.groq.com/docs/legal/customer-data-processing-addendum) were consulted. This is an operational review of the explicitly authorized limited test, not a legal-compliance certificate or approval for general students/minors.

## Enforced boundary

No general verification environment setting is enabled. The trusted local runner enters a Python context only after checking the reviewed file hashes, credential and expiry; final parsed input hashes are checked again before model processing. Each request verifies the same key and the installed SDK's pinned `https://api.groq.com` API root. Generated drafts stay private and unsaved. No batch/fine-tuning feature, public artifact publication or academic database write is used.

No HTTP route or environment variable enters this context. The general provider guard rejects a copied `local-nwu:` reference even if someone copies the four general flags with it. Exiting the context restores the previous state. General hosted processing still requires its own applicable review and authenticated acceptance; an owner-scoped local run does not establish that result.

Tests cover changed files, mismatched key, wrong origin, expiry, broader/invalid scope, copied references and cleanup. The first attempted run exposed a mistake in the new SDK-origin check (the installed Groq SDK uses the root and appends its versioned resource path); it was corrected before provider use. It also revealed that evidence classification masked configuration errors because `DocumentError` inherits `ValueError`. Those errors now propagate unchanged rather than consuming classification retries.
