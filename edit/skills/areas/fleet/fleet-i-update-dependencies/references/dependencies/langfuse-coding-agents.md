## Langfuse coding-agent integration

Dependency ID: `langfuse-coding-agent-integration`. This optional service is selected explicitly and managed through `$fleet-configure-langfuse-coding-agents`. Codex and Node 22+ are prerequisites for Codex; Claude and uv are needed only when its integration is selected.

Distribute only non-secret instance metadata. Codex uses its official plugin and approved user-only local JSON credentials, outside Git and fleet sync. Claude retains native custody. Enrollment, harmless trace verification, rotation and complete cleanup follow the owning skill. Never synchronize API keys or authorization headers.
