# Local telemetry and repair evals

Use only for an explicitly authorized isolated eval. Never inject faults into a
shared application or production namespace. This Linux-only runner requires the
local Docker Unix socket, Bubblewrap, Python, Node 22, an existing Codex model
login and Impression's installed esbuild dependencies. A missing prerequisite is
a blocker, never authority to use production credentials or a remote engine.

The entrypoint is `../scripts/live-eval.py`. It loads
`internal/src/maintenance_live_eval.py` from the containing package, using
`internal/defaults/maintenance-eval/backend.json`. The offline `eval.py` remains a
separate fixture suite with zero real model calls.

Pass explicit existing Impression checkout, registered Vault, installed skill,
Node executable and private machine-local output paths:

```sh
python3 ../scripts/live-eval.py \
  --impression <existing-checkout> --vault <registered-vault> \
  --skills <installed-skill-root> --node <node-22-executable> \
  --output-root <private-machine-local-state> --mode detect
```

First run detection, then `--mode preflight` without a model call, then one
`--mode repair --trials 1`. Repeat three to five repair trials only after that
first complete case works. For long execution, use a bounded owned local job
with a complete tool PATH and no dependency on the primary Mac or an SSH
session. Do not add a recurring schedule. Keep the production mutation lock,
timers, queue, cursors and issue destination untouched.

The backend test uses Impression's real prompt builder, error middleware and
logger. The fault is a run-owned source overlay, never a production source edit
or commit. A separately compiled, authenticated test server has fixed scenarios,
a five-minute lifetime, a 32-request budget and an 8 KiB request bound. It has no
network interface to shared services. A private local Loki receives actual
application stdout. The actual collector's loopback-only test transport retains
its real query, pagination, redaction and routing code. The actual durable queue
checks grouping, replay and empty-window dispatch.

The actual maintenance agent adapter uses an eval-only external command.
Bubblewrap enforces a restricted view of the existing Vault and permits editing
only the seeded source overlay. It hides application credentials, host sockets,
Git destinations and production resources. A blind CONNECT proxy permits only
model-service TLS destinations. Existing model login custody is consumed
opaquely and is distinct from application authority. The inner Codex sandbox is
disabled because nested user namespaces are unavailable after the outer sandbox
drops capabilities; the outer boundary remains enforced and tested before every
agent invocation. Never copy this invocation into normal maintenance execution.

The host verifier is outside the fixing agent's writable area. It rebuilds the
repair, repeats the original request and additional behavior probes, checks the
exact source identity, requires preserved original telemetry, and exercises an
immutable failing logging control after repair. A plausible outcome or a
`repaired` status is insufficient. Both successful and failed trials retain the
private trajectory, hashes, timings, queue, resource ledger and cleanup proof.
Only exact owned containers/process groups are removed. No credential values
belong in exported evidence.

A passing backend trial excludes browser reporting, native Langfuse,
Kubernetes inventory, a second service, cross-source logical-occurrence
deduplication, production deployment and rollback. These need separate live
scenarios. Missing configured telemetry remains incomplete. Read Impression's
`.docs/k3s-triage-evals.md` for the application boundary and current reproduction
command. The private canonical source and installed daily runtime are separate;
source preparation does not authorize replacing that runtime.


The private runtime also supplies `maintenance_browser_eval.py`,
`maintenance_native_eval.py` and `maintenance_service_eval.py` for real browser,
native Langfuse and Testimonials detection. They preserve their own checkpoints,
resource ledgers and grades. The browser uses the actual reporter and action
through an eval HTTP transport; Next RSC wire acceptance remains separate. The
native case provisions only local dependencies on an internal Docker network,
uses generated project-only credentials, and invokes the unchanged native API
collector. No paid model call manufactures an observation. The second-service
fixture exercises the actual readiness/error/log path with a connection refusal
inside a namespace without external networking. Each source identity and local
resource is recorded and cleanup verified.

`maintenance_verifier_eval.py` tests the actual verifier against stdout
suppression and a hardcoded result. These are adversarial host stubs with real
application/Loki telemetry, explicitly zero coding-agent invocations and no
autonomous repair grade. Keep the repeated real-agent cohort separate from
these verifier tests and from offline replay. Production fault injection,
release/rollback, cross-source logical-occurrence deduplication and production
native custody remain unaccepted by those local passes.
