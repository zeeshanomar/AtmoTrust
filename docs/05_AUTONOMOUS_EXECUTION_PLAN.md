# AtmoTrust — Autonomous Execution Plan

> Single-agent build plan · 19 September 2026  
> Executor: Codex in the target Git repository

This replaces all team assignment, branch integration, handoff, and approval plans. The user supplies the repository and these six documents once. Codex then owns inspection, implementation, integration, testing, repair, documentation, and final handoff.

## 1. Operating mode

- Work through the complete build without routine human checkpoints.
- Start with a short internal plan, then act immediately.
- Inspect existing code before replacing it.
- Preserve useful working code and unrelated user changes.
- Make reasonable reversible decisions when details are missing.
- Do not stop merely because an optional provider, deployment service, or model is unavailable.
- Ask the user only for a genuinely unavailable credential/permission or an ambiguous destructive decision that cannot be avoided.
- Run tests and repair failures instead of returning a list of tasks for the user.
- Finish with a runnable integrated product, not isolated modules or a plan.

## 2. Read order and authority

Read all files completely before implementation:

1. `01_PROJECT_MASTER.md`
2. `02_TECHNICAL_CONTRACT.md`
3. `03_DATA_AND_AI_PLAN.md`
4. `04_UI_AND_DEMO.md`
5. `05_AUTONOMOUS_EXECUTION_PLAN.md`
6. `06_CODEX_BUILD_RULES.md`

When files appear to conflict, product scope wins first, followed by the machine contract, data/AI policy, UI behaviour, execution plan, and build rules. Resolve minor ambiguity with the smallest end-to-end solution and record the choice in `docs/IMPLEMENTATION_NOTES.md`.

## 3. Phase 0 — Repository audit

Before editing:

1. Read repository instructions such as `AGENTS.md` and the existing README.
2. Inspect Git status and preserve unrelated changes.
3. Map the frontend, backend, data, tests, environment files, and deployment configuration.
4. Run current tests/builds once where practical to establish the baseline.
5. Search for duplicate apps, fixture-only production paths, hard-coded scores, random dashboard data, localhost URLs, secrets, incomplete TODOs, and broken imports.
6. Decide whether to repair the existing structure or converge on the structure in `02_TECHNICAL_CONTRACT.md`.
7. Write a compact implementation checklist and immediately begin.

Do not spend the session producing an audit report instead of code.

## 4. Phase 1 — Establish one runnable spine

Create the smallest connected vertical slice first:

1. Backend health route and typed models.
2. One prepared station frame with all three variables.
3. One run controller with play/pause/reset.
4. One real TrustEngine call returning measured evidence.
5. One state endpoint and WebSocket snapshot/update.
6. Frontend shell and Command Centre consuming that state.
7. Root-level start instructions or script.

Verify the slice before widening scope. This avoids building six disconnected subsystems.

## 5. Phase 2 — Data package and analytical core

In order:

1. Reuse verified repository data or prepare `demo_v1` using the source policy.
2. Validate units, time order, overlap, missingness, and provenance.
3. Generate station metadata, peer links, policy, manifest, and data report.
4. Implement causal rolling and direct-pattern features.
5. Implement expected-value and spatial/multivariate evidence.
6. Train or prepare Isolation Forest and optional regressors.
7. Implement evidence fusion, Trust Score, confidence, and severity.
8. Implement transparent fault classification.
9. Implement Sensor Health and maintenance priority.
10. Add unit/no-leakage tests.
11. Build artifacts and run a small benchmark smoke test.

The runtime and benchmark must call the same analysis code and policy.

## 6. Phase 3 — Replay, simulation, and operations

1. Load warm-up plus demo frames from the prepared package.
2. Implement atomic frame processing and deterministic scheduling.
3. Add play, pause, speed, and reset with generation changes.
4. Implement all six fault transforms on copied observations.
5. Implement atomic 1–8 item injection batches.
6. Implement the coherent regional scenario.
7. Support a regional scenario plus independent fault.
8. Add incidents, actions, health history, and maintenance ranking.
9. Persist required records in SQLite.
10. Add WebSocket state broadcasting and reconnect snapshots.
11. Add deterministic controller and integration tests.

## 7. Phase 4 — Complete the four-screen frontend

Build against the live backend rather than a separate mock server:

1. Shared API client, WebSocket client, and run store.
2. Auto-create or restore a demo run on first load.
3. Global status strip and connection/error states.
4. Command Centre map/fallback, charts, alerts, and summaries.
5. Station Investigation charts, trust panel, evidence, peer comparison, and actions.
6. Simulation Lab controls, multi-fault builder, active injections, and regional event.
7. Maintenance Centre ranking, health trend, recommendation, and action history.
8. Cross-screen selection and synchronization.
9. Responsive desktop layout and accessibility pass.
10. Production frontend build and targeted component tests.

Delete development-only random data and hidden fixture fallbacks before integration testing.

## 8. Phase 5 — Live lane

1. Implement the provider adapter with strict timeouts and schema validation.
2. Normalize live results to the shared Observation schema.
3. Expose provider and timestamps in source status.
4. Show a structured unavailable state on failure.
5. Allow clearly labelled test overlays on preserved live copies if supported.
6. Prove that replay remains unaffected by live failure.

Do not delay the core release while repeatedly fighting a blocked provider.

## 9. Phase 6 — Integrated release testing

Run and repair, in this order:

1. Backend unit tests.
2. Data/AI leakage and benchmark smoke tests.
3. Backend integration tests.
4. Frontend tests, typecheck, lint if configured, and production build.
5. Full-stack smoke test.
6. Two-client WebSocket synchronization test.
7. Every release test in `02_TECHNICAL_CONTRACT.md`.
8. Golden demo twice after reset.

For every failure:

1. reproduce the smallest case;
2. inspect logs/state/diff;
3. fix the root cause;
4. add or strengthen a regression test;
5. rerun the affected suite;
6. rerun the full release gate after integration changes.

Do not disable validation, delete failing tests, return empty success objects, or swallow exceptions to make checks green.

## 10. Phase 7 — Benchmark and evidence package

1. Run the full held-out injected-fault benchmark.
2. Save JSON/CSV metrics and a readable Markdown summary.
3. Include evaluated sample counts, per-fault results, latency, and limitations.
4. Ensure UI/README claims do not exceed the measured output.
5. Capture or generate any small architecture/benchmark visuals required by the README from real results.

If the benchmark exposes a weak fault type, tune only with validation data and rerun the untouched test set once after the final policy is frozen.

## 11. Phase 8 — Documentation and deployment

Update or create:

- `README.md` with problem, solution, architecture, setup, commands, screenshots if available, demo flow, metrics, data provenance, and limitations;
- `.env.example` with safe values;
- `docs/IMPLEMENTATION_NOTES.md` for compatible deviations and fallbacks;
- `docs/DEMO_GUIDE.md` with the five-minute sequence and recovery path;
- `docs/USE_CASES.md` covering six faults, genuine regional weather, and the compound case;
- executable or clearly documented local start commands;
- existing deployment configuration when present.

If deployment credentials and a configured target are already available, deploy and smoke-test the public result. If deployment is blocked by missing external authority, leave a production-ready configuration and fully tested local build. Do not weaken or fake the application to obtain a URL.

## 12. Phase 9 — Final repository cleanup

Before completion:

1. Inspect the full diff and Git status.
2. Remove temporary debug output, generated caches, dead duplicate code, fixture-only production paths, and unused dependencies.
3. Confirm no `.env`, token, API key, absolute personal path, database, `node_modules`, or virtual environment is committed.
4. Confirm all source labels and metrics are truthful.
5. Run the final tests/build one last time.
6. Ensure README commands exactly match the final repository.
7. Leave the worktree in a coherent reviewable state.

Do not rewrite Git history, force-push, or delete unrelated user files.

## 13. Scope-cut ladder

If time or environment constraints make everything impossible, cut only in this order:

1. extra visual effects;
2. optional SHAP/LIME view;
3. corrected-value suggestion;
4. extra live providers;
5. extra benchmark charts;
6. hosted deployment when credentials are absent.

Never cut:

- real backend analysis;
- all six fault types;
- regional versus isolated reasoning;
- synchronized core screens;
- truthful evidence and states;
- replay reliability;
- tests for the golden path;
- local runnable delivery.

## 14. Autonomous blocker policy

Do not ask for help when a safe fallback exists.

| Blocker | Autonomous response |
|---|---|
| Historical download unavailable | use existing verified data, then clearly labelled deterministic fallback as last resort |
| Live provider unavailable | structured degraded state; keep replay functional |
| Optional model performs poorly | retain simpler validated baseline |
| Map tiles unavailable | render offline station layout |
| Deployment credentials absent | finish and verify production-ready local build/config |
| Existing module is broken | repair or replace only that project-owned module with tests |
| Contract detail is ambiguous | choose smallest compatible interpretation and document it |

Stop and ask only when continuing would require an unavailable secret/permission, overwrite ambiguous user data, or perform another irreversible action outside the build scope.

## 15. Required final handoff

Codex's final response must state:

- what is now implemented;
- exact start command(s);
- tests/builds run and their pass/fail counts;
- benchmark results and dataset provenance;
- deployed URL if successfully created;
- honest remaining limitations;
- important files changed.

Do not end with “next, you should integrate/test/build.” Those are part of this autonomous task.
