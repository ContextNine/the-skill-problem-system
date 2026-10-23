# Evaluation file contract

Preserve these repository-relative paths:

```text
.agents/evaluations/<evaluation-id>/
  manifest.json
  evidence.json
  triage.md
  traces/
  recommendations/
  final.md
```

Recommendations must state scope, finding, evidence trace IDs and relative links, observed fact, inference, likely cause, specific fix, implementation surface, benefit, risk, focused proof, and confidence. Use `No finding` when evidence is insufficient. Never reproduce credentials, authorization headers, cookies, signed URLs, or binary/data URLs.

The final report must include scope and coverage, what works, failure modes, slow or expensive paths, output-quality problems, instrumentation gaps, proposed fixes, recommended order, evidence index, and limits. Dossiers are examples; aggregate evidence is the population.

