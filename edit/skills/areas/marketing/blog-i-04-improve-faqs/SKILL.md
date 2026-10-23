---
name: blog-i-04-improve-faqs
description: Use when the user asks to generate, research, audit, or improve a blog article's FAQs or AEO question coverage. Combines article intent with observed PAA, search queries, and customer questions to draft concise supported answers or recommend focused body edits.
---

# 4. Blog · Improve FAQs

Find useful questions an article leaves unanswered. Return only questions worth answering for its audience, with evidence and concise answers. An FAQ-only request can start here; a new article uses this after the main draft exists.

## Question and evidence contract

- Read the full article, its research brief if available, audience/voice guidance, and relevant neighboring pages. Identify core intent and the main inferred search question; an inference is not measured demand.
- Gather available Search Console questions, customer/support evidence, actual PAA, and related searches for the topic and target locale. Existing research tools, observed SERPs, supplied exports, or DataForSEO may supply evidence.
- Record question origin, source/query, observation date, locale, and any real volume metric in the private research artifact. Clearly label model-suggested questions and related-query expansions as hypotheses. Do not call them observed Google query fanouts.
- Group duplicate intent and remove questions already answered adequately in the article. Skip generic padding, unrelated topics, and questions better owned by another page. Prefer linking to an existing good answer over duplicating it.
- Select only questions with a clear reader benefit and supported answers, usually three to six. Zero is a valid result; do not force a fixed count.
- Answer directly in the first sentence. Use only as much detail as the question needs, with a concrete example or limitation when useful. Avoid repeating the article introduction or turning every answer into a product pitch.
- Support answers with article evidence or current verified primary sources. The article alone is not proof of a changing claim. Compose `$blog-i-02-research-and-brief` for missing facts and keep unresolved claims out of the draft.
- Use `$unslop` and the author's voice. Preserve meaningful nuance, including cases where the owner-product is not the best fit.

## Output and source integration

Return proposed questions/answers plus a short private evidence note explaining why each belongs, what it adds, and unresolved facts. Suggest an edit in the article body when that answers the question more naturally. Keep evidence bookkeeping out of public FAQs and normal Vault note bodies.

For draft-only requests, save the proposal beside the article's private research/draft artifacts. For authorized edits, compose `$blog-i-03-write-and-refresh` for the authoritative source and verification contract, applying only the relevant question coverage. Do not invoke a full rewrite. Respect tenant/source ownership, Vault-generated boundaries, Notion status, and unsupported local draft fields.

If a typed page has no FAQ field, propose a supported body-field edit or deliver the FAQ draft. Do not invent schema fields, add a new renderer, or change application architecture for this task.

## Search claims and services

Useful questions and verifiable answers are the goal. Do not guarantee rankings, citations, PAA placement, or AI visibility. Do not add FAQ schema automatically; only use the site's supported structured data when it describes visible content and has a current documented purpose.

Check current Google documentation before making claims about AI optimization or rich-result eligibility. Google retired FAQ rich results in May 2026; clear FAQs can still help readers, but that is distinct from a special search feature. Primary guidance: <https://developers.google.com/search/docs/fundamentals/ai-optimization-guide> and <https://developers.google.com/search/updates>.

No paid service is mandatory. DataForSEO optionally supplies structured PAA/related searches. Missing PAA access limits the observed evidence; it does not license fabricated PAA. Profound is only useful here when real prompt-demand evidence is already available.
