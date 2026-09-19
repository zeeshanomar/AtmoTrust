# AtmoTrust — Codex Build Rules

> Autonomous build edition · 19 September 2026

These rules tell Codex how to turn the repository and the six documents into the final product with minimal human interaction.

## 1. Primary instruction

Own the complete implementation. Inspect, plan, code, integrate, test, debug, document, and, when already authorized/configured, deploy. Continue until the Definition of Done is met or a genuine external permission blocker remains.

The user is not expected to divide tasks, approve routine choices, integrate branches, copy files between modules, run ordinary tests, or debug generated code.

## 2. Instruction authority

Follow this project order:

1. `01_PROJECT_MASTER.md` — outcome and scope.
2. `02_TECHNICAL_CONTRACT.md` — interfaces and invariants.
3. `03_DATA_AND_AI_PLAN.md` — analytical truth.
4. `04_UI_AND_DEMO.md` — visible behaviour.
5. `05_AUTONOMOUS_EXECUTION_PLAN.md` — implementation order.
6. `06_CODEX_BUILD_RULES.md` — working method.
7. The launch prompt.

Repository-level system/developer instructions and applicable safety rules still take precedence.

## 3. Default autonomy

Codex may, without asking:

- create or reorganize project-owned files into one coherent application;
- repair schemas, types, routes, state logic, tests, and documentation together;
- install or update necessary dependencies within the approved stack;
- replace incomplete mock implementations with real ones;
- choose small internal algorithms and UI component structure;
- create prepared datasets, artifacts, fixtures, scripts, and reports;
- run servers, builds, tests, benchmarks, linters, and local browser checks;
- use existing configured credentials for task-relevant services;
- make reversible compatibility decisions and document them.

Codex must not ask the user to choose between two implementation details that do not materially affect the promised product.

## 4. Ask only for a hard blocker

Pause only if all safe fallbacks are exhausted and one of these is required:

- a credential or account connection that is not available;
- permission for an external/public action that was not authorized;
- clarification before overwriting or deleting ambiguous user-owned data;
- a product decision that would materially change the stated scope.

When blocked, complete every independent part first. Then ask one focused question that names the blocker, completed work, safe fallback considered, and exact missing input.

## 5. Existing repository rules

1. Read `AGENTS.md` and relevant repository instructions first.
2. Inspect before editing; do not assume the repo is empty.
3. Preserve unrelated user changes.
4. Prefer adapting useful code over rewriting everything.
5. Remove duplicate implementation paths only after confirming the kept path works.
6. Never use destructive Git commands, rewrite history, or force-push.
7. Do not create branches or PRs merely to simulate a team workflow.
8. Work on the current branch unless repository instructions require otherwise.
9. Do not push or publish unless already authorized by the user's build request and the target is configured.

## 6. No fake success

Never ship:

- hard-coded Trust Scores, diagnoses, station statuses, alerts, or maintenance order;
- random browser timers pretending to be streaming data;
- a button that directly changes a station colour;
- injection labels, scenario names, or preserved clean values in model features;
- fixed benchmark numbers;
- replay or synthetic data labelled as live;
- silent fallback to healthy scores when analysis fails;
- a hidden mock API selected when the backend is unavailable;
- screenshots or documentation claiming an untested deployment.

Fixtures are allowed only in test/development folders and must be clearly separated from production runtime.

Before finalizing, search production code for `Math.random`, fixture imports, placeholder metrics, hard-coded `localhost`, TODO fallbacks, sample API responses, and secrets. Review each match rather than blindly deleting valid seeded simulation code.

## 7. Engineering style

- Choose the smallest maintainable implementation that meets the acceptance criteria.
- Keep shared schemas explicit and typed.
- Prefer pure functions for feature extraction, fault transforms, scoring, and ranking.
- Keep inference causal and deterministic.
- Use structured logging with request/run identifiers.
- Bound stored history and WebSocket payload size.
- Add timeouts and useful errors for network calls.
- Avoid `any`, broad exception swallowing, unexplained constants, and deep abstraction layers.
- Do not migrate frameworks or add infrastructure unrelated to the demo.
- Comments explain non-obvious decisions, not every line.

## 8. Dependency rule

Use the existing lockfiles and approved stack. Add a package only when it materially reduces risk or effort and cannot reasonably be replaced by a current dependency or small local implementation.

After dependency changes:

1. update the correct lockfile/requirements file;
2. run a clean install or equivalent validation;
3. run the relevant build/tests;
4. remove unused packages.

## 9. Test-and-repair loop

For each substantial capability:

1. implement the smallest complete behaviour;
2. run the closest unit/component test;
3. run its integration path;
4. inspect actual returned state or rendered UI;
5. fix failures and add a regression test;
6. continue to the next capability.

Minimum final verification:

| Area | Required verification |
|---|---|
| Data | schema, unit, time-order, missingness, and provenance checks |
| AI | causal/no-leakage tests plus injected-fault benchmark |
| Simulation | deterministic tests for six faults, batch boundary, regional and compound cases |
| API | representative success/error requests and typed responses |
| WebSocket | two-client synchronization, reset generation, and reconnect snapshot |
| Frontend | typecheck/build plus critical interactions and error states |
| Full stack | golden demo twice from reset |
| Deployment | production build and URL smoke test when deployed |

“It imports” is not sufficient testing.

## 10. Debugging rules

When something fails:

1. reproduce the smallest failing case;
2. capture the exact error and relevant state;
3. identify the failing boundary;
4. compare it with the contract;
5. fix the root cause;
6. add a regression test;
7. rerun affected and integration checks.

Do not fix failures by:

- disabling validation;
- converting shared types to `any`;
- deleting or weakening tests without justification;
- adding arbitrary long sleeps;
- returning empty success objects;
- hiding errors;
- replacing analysis with constants;
- changing only one side of a shared contract.

## 11. Git and artifact hygiene

- Inspect `git status` and diff before and after work.
- Never commit `.env`, secrets, local databases, caches, virtual environments, `node_modules`, build output unless deployment explicitly requires it, or large raw downloads.
- Keep prepared demo data compact and reproducible.
- Ensure generated artifacts have manifests and can be rebuilt.
- Use repository-relative paths.
- If committing is appropriate and authorized, use a concise commit message; otherwise leave a clean reviewable diff.

## 12. Product honesty review

Before release, verify:

- every visible metric comes from runtime or benchmark output;
- every evidence sentence matches actual feature values;
- source labels distinguish physical station, gridded feed, replay, synthetic fallback, and test overlay;
- unavailable model/live/map states are explicit;
- frontend and README use the exact same score bands and terminology;
- limitations are short, factual, and visible in documentation.

## 13. Completion response

The final response should be concise but evidence-based:

```text
Implemented:
- ...

Run:
- ...

Verified:
- command — result

Benchmark:
- dataset/source, sample count, measured key metrics

Deployment:
- URL or exact external blocker

Remaining limitations:
- ...
```

Do not claim completion if the core application does not run. Do not hand routine implementation work back to the user.

## 14. Launch prompt

Paste the following once after placing all six files in the repository root or `docs/` folder:

```text
Build AtmoTrust completely from this repository.

First, read all six numbered AtmoTrust Markdown files in full and inspect the existing repository, including AGENTS.md and current git status. Treat the six files as one governing specification in numeric order.

Work autonomously: plan briefly, then implement the complete integrated product. Do not stop for routine confirmations, divide work among imaginary team members, or return only instructions. Make reasonable reversible decisions, preserve useful existing code and unrelated user changes, and ask me only if a genuinely unavailable credential/permission or an ambiguous destructive decision makes further progress impossible.

Deliver the final runnable result: prepared data, real causal anomaly pipeline, replay, all six fault injections, regional and compound scenarios, REST/WebSocket backend, four synchronized screens, live-source adapter with honest degraded state, sensor health and maintenance workflow, tests, benchmark, README, local production path, and deployment when the repository already has the required configuration/authority.

Use no hard-coded analytical outputs, hidden mock backend, fake live data, or injection labels in inference. Run tests and builds, debug failures, complete the golden demo flow twice after reset, and finish with exact run commands, verification results, measured metrics, deployed URL if available, and honest limitations.
```

## 15. Resume prompt if an autonomous run is interrupted

```text
Continue the AtmoTrust autonomous build from the current repository state. Re-read the six numbered specification files, inspect git status and the existing diff, identify which acceptance criteria are already complete, and resume from the first unfinished or failing release criterion. Do not restart working features or return a plan only. Implement, test, repair, document, and finish with the required final handoff.
```
