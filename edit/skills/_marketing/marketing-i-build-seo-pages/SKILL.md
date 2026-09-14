---
name: marketing-i-build-seo-pages
description: Use when the user asks to research, draft, build, or refresh one SEO-targeted page such as an alternatives roundup, best-tools list, comparison, pricing guide, how-to guide, or glossary page.
---

# Marketing · Build SEO Pages

Build one useful SEO page from current search evidence, primary sources, and verified product facts. Deliver a draft or pull request for human review. Do not publish it.

This skill owns page creation and refreshes. Use a dedicated SEO audit skill for a site-wide audit, a technical SEO skill for crawling and indexing defects, and a programmatic SEO skill for templated page systems.

For Impression's typed competitor routes, keep using the repository-specific sequence: `$blog-research-competitor`, `$blog-research-create-briefs`, then `$blog-competitor-pages`. Use this skill there only when the user explicitly asks to replace or extend that workflow.

## Evidence contract

- Use current keyword and SERP data when available. Never invent search volume, difficulty, CPC, rankings, or SERP features.
- If no SEO data source is available, ask for exported data or screenshots when exact metrics matter. Qualitative research may continue, clearly labeled as such.
- Quote only real public posts. Keep the wording verbatim, link the source, and verify that the URL resolves. Mark omissions with `…` and substitutions with square brackets.
- Verify pricing, feature availability, limits, and other changeable facts against official sources during the task.
- Credit competitors where they are strong. If the site owner sells a product in the category, disclose that relationship and include real drawbacks.
- Never reuse quotes, FAQs, product summaries, or other substantial copy from sibling pages.
- Work on one page per run. If asked for many pages, research and prioritize the queue, then build the first approved page.

## Research sources

Use the best sources available for each job:

- Keyword and ranking data: Ahrefs, DataForSEO, Semrush, Search Console, or user-provided exports.
- Live results: a search engine or an available SERP API.
- User language: public Reddit, Hacker News, X, review sites, and relevant community forums.
- Product facts: official pricing pages, documentation, changelogs, and company announcements.

Do not read credentials from plaintext files. Use already configured tools or managed environment bindings.

## Workflow

1. Establish the topic, market and locale, page type, audience, owning site, target URL, and whether this is a new page or a refresh.
2. Read the repository's brand, product, audience, and content guidance. Inspect the existing page and nearby pages when relevant.
3. Build a keyword set around the topic. Include natural commercial modifiers and questions that match the page type.
4. Collect current volume, difficulty, CPC, and ranking data when available. Check whether an existing page is already within reach of the target query.
5. Inspect the live SERP for the primary query. Record the dominant intent and format, recurring subtopics, list depth, People Also Ask questions, visible AI answer features, and weaknesses in ranking pages.
6. Check cannibalization against nearby pages. Refresh an existing page when it already owns the intent. Otherwise set a distinct primary query, title, and internal-link relationship.
7. Mine public discussions for six to ten useful excerpts. Favor specific experiences, objections, tradeoffs, recommendations, migrations, and failed approaches. Verify each quote and URL.
8. Verify every product fact that will appear. For roundups, capture current pricing, best-fit user, strengths, drawbacks, and the important differentiator for every option.
9. Write the page in the format supported by the SERP. Use the source material to add information competitors do not have, not as decoration.
10. Integrate the draft with the site's existing components, metadata conventions, sitemap, canonicals, schema helpers, and internal-link patterns.
11. Run the repository's relevant checks and complete the QA contract below.

Save research beside the site's existing content-research artifacts. When no convention exists, propose a location before adding a new repository-wide pattern.

## Page requirements

- Lead with a direct answer and the main finding from the research.
- Put useful comparison or decision information early.
- For roundups, include a comparison table and a substantive section for each option with verified pricing, best fit, strengths, and drawbacks.
- For comparisons, explain the deciding dimensions and state who should choose each option.
- For guides, use real examples and include failed approaches when the source material supports them.
- Answer real search questions in the FAQ. Do not invent questions to pad the page.
- Add only schema that matches visible content. Use real author and date values. Preserve the original publication date on a refresh and update the modified date.
- Add a concise methodology note when evaluation or ranking is involved.
- Keep copy plain, specific, and consistent with the site's voice.

## QA contract

Before handoff, confirm:

- Every quoted source is public, live, and transcribed accurately.
- Every changeable claim was checked during this task and the page uses consistent figures.
- The page matches the observed search intent without copying ranking pages.
- Competitor strengths, owner-product drawbacks, and any vendor disclosure are present when relevant.
- Metadata, canonical URL, internal links, sitemap entry, dates, and visible schema agree.
- No sibling-product names, placeholder copy, repeated paragraphs, broken images, or captured bot and cookie walls remain.
- Build, lint, type checks, and relevant tests pass when the page lives in a code repository.

Report the target query, available metrics, SERP format decision, sources used, page location, checks run, and any stale facts found elsewhere. Clearly distinguish measured data from judgment.

## Refreshes

Re-run keyword, SERP, source, and fact research. Keep the URL and original publication date unless the user explicitly changes the strategy. Replace stale evidence, update the modified date, and compare the result with the old page to confirm it became more specific and useful, not merely longer.
