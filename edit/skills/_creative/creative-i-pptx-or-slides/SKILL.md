---
name: creative-i-pptx-or-slides
description: Use when the user asks to create, edit, inspect, convert, or export a presentation, PowerPoint, PPTX, or slide deck and the agent must choose the right Claude or Codex slide workflow.
---

# Creative · PPTX or Slides

Choose one route before authoring. Follow the user's named route when they specify one. Otherwise, choose from the options for the current agent.

## Claude

### Default Claude PowerPoint

Use Claude's built-in PowerPoint and PPTX capabilities for straightforward deck creation, editing, and native `.pptx` delivery. Prefer it when the request does not need Witan's lower-level scripting or Frontend Slides' HTML and motion workflow.

### Witan PPTX

Use `$witan-pptx-officejs` for editable `.pptx` files, native PowerPoint objects, charts, scripted changes, rendering, linting, or precise inspection. Prefer it for PowerPoint deliverables.

### Frontend Slides

Use `$creative-frontend-slides` for self-contained, animated HTML presentations. Prefer it when browser delivery, motion, or a web-native presentation matters more than native PowerPoint editing.

## Codex

### Default Codex Presentations

Use `$presentations:Presentations` for the standard Codex PowerPoint and Google Slides workflow. Prefer it for editable decks, existing templates, broad presentation work, and requests without a more specific route.

### Witan PPTX

Use `$witan-pptx-officejs` for deterministic Office.js-compatible creation or editing, native charts, low-level inspection, rendering, and linting.

### Codex Slides

Use the installed `codex-slides@codex-slides` plugin for a browser-first creative workflow with visual iteration and image-native PPTX or PDF export. Prefer it when visual polish and rapid art direction matter more than editing individual PowerPoint elements. Its exported PPTX uses full-slide images, so do not choose it when the user needs editable shapes, text, tables, or charts.

If Codex Slides is unavailable in the current Codex session, use Default Codex Presentations or Witan PPTX instead. A newly installed plugin may require a new task before its skills and tools appear.
