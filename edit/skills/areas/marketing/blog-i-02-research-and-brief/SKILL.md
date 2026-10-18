---
name: blog-i-02-research-and-brief
description: Use when the user asks to research a blog topic or competitor, prepare a blog writing brief, or refresh the evidence for a comparison, alternatives article, or guide. Verifies search intent, customer questions, product facts, and sources before writing.
---

# 2. Blog · Research and brief

Prepare a source-backed writing brief for the selected site and audience. Support ordinary articles and competitor comparisons without requiring separate research and briefing invocations.

## Research contract

- Resolve the owning repository through `$fleet-i-code-folder-and-computer-topology`; read its instructions, nearest content README, brand/product facts, existing research, and relevant neighboring articles.
- Establish topic, audience, locale, owning tenant, new/refresh intent, and publication format. An explicit topic may start here without an opportunity audit.
- Verify pricing, availability, product status, features, and other changing facts against current official sources. Existing dossiers reduce repeated research but never override fresh contradictory evidence. Browse whenever the brief relies on changing facts; no separate refresh request is needed.
- Search evidence may come from Search Console, live SERPs, DataForSEO, Semrush, Ahrefs, or supplied exports. Never invent search volume, difficulty, rankings, CPC, PAA, or prompt demand.
- Record observed search intent, result formats, common questions, and missing information. Label suggested query expansions as hypotheses, distinct from observed PAA/related searches and measured customer questions.
- Find relevant first-hand experiences and useful customer language where available. Do not require a fixed quote count or pad research with weak sources. Public quotations must be real, accurately transcribed, and linked to a resolving source. Private calls inform the brief without becoming attributed public quotes unless approved for that use.
- Check overlap with existing pages; choose an existing URL when it already owns the intent. A new article needs a distinct purpose and useful information beyond summaries of current results.
- Distinguish current product behavior, marketed claims, roadmap ideas, outside opinions, and uncertainty. Do not treat generated product documentation alone as proof of deployed availability.
- Credit competitors where strong, respect category boundaries, and state when the owning product is only adjacent. Rank alternatives on explicit criteria rather than automatically placing the owner first.

## Brief and artifacts

Reuse existing artifact conventions. Without one, use repository-relative `./.agents/blog/<site-or-tenant>/research/` and `./.agents/blog/<site-or-tenant>/briefs/`. Refresh an existing artifact rather than create a near-duplicate. For the established competitor format, read `./references/competitor-briefs.md`.

A brief must stand on its own and contain:

- Audience, core intent, primary query/question cluster, target URL, and new/refresh decision.
- Available measured demand, evidence source/date/locale, missing metrics, and qualitative judgment.
- An honest thesis and the distinct information this page contributes.
- Proposed structure, useful examples, relevant internal links, and remaining questions.
- Verified facts with their source links and dates; current versus planned capabilities.
- For comparisons, fair candidates/axes, competitor wins, owner wins, category limits, and pricing confidence.
- Claims to avoid, unresolved evidence, owner disclosure where relevant, and the intended source/format for the writer.

Do not write polished public prose in the research brief or create a separate claim-map sidecar. Keep facts and source links together. Preserve useful existing research, including uncertainty and unfavorable findings.

## Handoff and services

Compose `$blog-i-03-write-and-refresh` when writing is part of the request. Compose `$blog-i-04-improve-faqs` for a focused question review. Research alone ends with a brief, not publication.

Current web research is required for changing facts. SEO tools and Profound are optional, and existing exports are valid. Do not add paid services or claim access to unconfigured integrations.
