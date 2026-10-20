# SIH26249 Prototype Build Prompt and Documentation

*Integrated Predictive Maintenance & Fleet Availability Decision Platform (Air Power)*

Built from the 47-file research package (problem decomposition through Final Coding Handoff). Source precedence, as set by the Final Consistency Audit: Reviewed PRD v1.1 (product meaning) > Requirement Traceability Matrix (requirements and tests) > Corrected System Architecture and Consistency Audit (cross-layer contracts) > Technology Decision Package (stack). Older drafts lose any conflict.

How to use this document: Part A is a ready-to-paste master prompt for a coding assistant (Claude Code, Cursor, etc.). Part B is the supporting documentation it refers to. Items marked **\[ASSUMPTION\]** are my proposals where the research leaves a value open; everything else comes from the research files.

---

# PART A: MASTER PROMPT (paste this into your coding tool)

```
ROLE
You are a senior full-stack engineer building a local-first prototype of the
"Integrated Predictive Maintenance & Fleet Availability Decision Platform"
(SIH26249, Air Power). Build the MAXIMUM working functionality that fits the
Gate A scope below. Do not build anything listed under OUT OF SCOPE.

PRODUCT IN ONE SENTENCE
A single-instance ADVISORY platform that ingests synthetic evidence from four
domains (aircraft health, technical records, spares/logistics, maintenance
agency/work orders), validates it, links it to the right asset/component/
configuration/time, ranks cases deterministically, checks intervention
feasibility, passes every case through ONE fail-closed DecisionGate
(READY_FOR_HUMAN_REVIEW / HOLD / BLOCK), records a local human disposition,
and keeps a versioned, replayable trace.
It is NOT a maintenance controller. It never writes to aircraft, work-order,
release or flight systems.

CORE PRINCIPLES (non-negotiable)
1. Fail closed: unknown, stale, missing or ambiguous never counts as OK.
2. Exactly ONE DecisionGate emits gate_state. No controller, UI, model wrapper
   or report may compute READY/HOLD/BLOCK on its own.
3. READY means "ready for human review", never "approved".
4. Every decision field is sourced, or visibly UNKNOWN / PENDING / N/A.
5. Evidence classes are always labelled: SYNTHETIC, BENCHMARK, SIMULATED,
   OPERATIONAL, PENDING. Never imply real operational gains.
6. Contract first: enums, DTOs and OpenAPI before screens.
7. Real mechanism, not a mock-up. No UI-only fake data.

TECH STACK (fixed)
- Frontend: React + TypeScript + Vite + React Router (client-rendered SPA)
- Backend: Python 3.12 + FastAPI + Pydantic, ONE modular monolith
- DB: SQLite + SQLAlchemy + Alembic (foreign keys ON, transactions)
- API: REST/JSON under /api/v1, committed OpenAPI 3.1, TS types generated
- Artifacts: private local directory + registry table + SHA-256 manifests
- Tests: pytest; Vitest + React Testing Library; Playwright if available
- Run: bind 127.0.0.1, one process serves built SPA + API (same origin);
  optional single Docker container
Do NOT add: Redis, queues, Celery/Kafka, microservices, Kubernetes, GraphQL,
NoSQL, cloud inference, a second database.

ARCHITECTURE
Layers: Frontend SPA -> FastAPI controllers (DTO validation, principal, error
mapping) -> Application use cases (own transactions) -> Domain services
(contracts, linkage, ranking, feasibility, RUL facade, DecisionGate) ->
Repository/adapter interfaces -> SQLite + artifact root.
Controllers never touch tables or decide domain rules. Use cases never
re-implement ranking/feasibility/gate rules.

CANONICAL STATES
Intake:       RECEIVED | VALIDATED | QUARANTINED | REJECTED (every reject/
              quarantine has a reason code)
Linkage:      RESOLVED | UNRESOLVED | CONFLICT
RUL:          ACCEPTED | PENDING | OUT_OF_SCOPE | NOT_RUN | FAILED
Feasibility:  FEASIBLE | INFEASIBLE_HARD | UNKNOWN
Gate:         READY_FOR_HUMAN_REVIEW | HOLD | BLOCK
Disposition:  ACKNOWLEDGE_FOR_PLANNING | REJECT_RECOMMENDATION | DEFER |
              REQUEST_EVIDENCE   (local advisory record only)

DECISIONGATE PRECEDENCE (evaluate strictly in this order, first match wins)
1. Persistence/orchestration failure -> operation ERROR, NO gate result.
2. Missing/invalid RUL-applicability policy -> HOLD
3. Critical evidence or linkage unresolved/conflict -> HOLD
4. Trusted, current, resolved evidence of a hard-constraint violation -> BLOCK
5. Required prerequisite unknown or stale -> HOLD
6. Required RUL not ACCEPTED -> HOLD
7. Otherwise -> READY_FOR_HUMAN_REVIEW
Every result persists: reason codes, evidence references, case version,
rule/config fingerprint, decision_time, input snapshot. The full trace is
persisted BEFORE the gate state is returned.

BUILD THE FOLLOWING (Gate A, F01-F09, F12, F13)
F01 Four-domain fixture import with versioned contracts and provenance.
F02 Identity/configuration/time linkage: approved aliases only, half-open
    validity windows [valid_from, valid_to); ambiguous alias or overlapping
    epoch => UNRESOLVED, never auto-joined.
F03 RUL as explicit status: PENDING or OUT_OF_SCOPE (no accepted numeric
    claim) through a RULFacade that a later model can plug into.
F04 Deterministic transparent ranking with visible factor reasons and a
    frozen tie-break.
F05 Constraint feasibility: FEASIBLE / INFEASIBLE_HARD / UNKNOWN with rule +
    evidence. Unknown/stale NEVER counts as feasible.
F06 Single DecisionGate (above).
F07 Evidence-backed case card (all fields sourced or explicitly unknown).
F08 Human review: local disposition, role-checked, idempotent, expected case
    version, atomic with an audit event.
F09 Versioned append-oriented case/event history and replay. Do NOT claim
    tamper-proof.
F12 Frozen test suite: >=40 development cases + 240-case holdout, fault
    injection, deterministic replay, separate stateful/path tests.
F13 Startup-configured demo principal + server-side RBAC, audit events,
    no secrets, reproducible package with run manifest, backup/restore check.

OUT OF SCOPE (do not build)
Live connectors, work-order or aircraft write-back, global scheduler, auto-
retraining, intervention-risk model, physics-constrained estimator,
progressive inference, enterprise auth, cloud hosting, distributed anything.
F10 simulation and Gate B RUL model are CONDITIONAL: build only the stub
routes/UI that return NOT_RUN / PENDING, labelled honestly.

API (canonical; no aliases like /health, /imports, /evaluate)
GET  /api/v1/live              liveness + release id (loopback only)
GET  /api/v1/ready             DB + artifact root readiness
GET  /api/v1/session           display-only demo persona (no role switch)
GET  /api/v1/demo/metadata     fixture/policy/model version names only
GET  /api/v1/cases             filters: gate_state, asset_id, component_id,
                               freshness_state, limit 1-50, cursor;
                               server-fixed ordering + tie-break
GET  /api/v1/cases/{caseId}    versioned case card + latest evaluation
GET  /api/v1/cases/{caseId}/events   ordered history + completeness flags
POST /api/v1/import-runs       bounded synthetic fixture import
GET  /api/v1/import-runs/{runId}
POST /api/v1/cases/{caseId}/evaluations   the ONE authoritative evaluation
POST /api/v1/cases/{caseId}/dispositions  local advisory disposition
POST /api/v1/evaluation-runs   launch frozen suite (one active run)
GET  /api/v1/evaluation-runs/{runId}
POST/GET /api/v1/rul-runs, /api/v1/simulation-runs   stubs: NOT_RUN/BLOCKED
GET  /api/v1/artifacts/{artifactId}   logical ID only, never a path
Rules: mutations require Idempotency-Key; case mutations require expected
case version (If-Match). Reused key + different body => 409. Stable error
envelope. Invalid filters/DTOs => 422. Denied => safe denial + audit event.
Persisted READY/HOLD/BLOCK is a SUCCESS; DB/orchestration failure is an
ERROR with no fabricated gate state.

DATABASE TABLES
runs, source_records, validation_results, asset_component_mappings, cases,
case_versions, case_evidence_links, evaluations, case_events,
rule_config_versions, model_registry_versions, idempotency_records,
artifact_references, security_audit_events.
Time: keep source offset, store event_time AND ingest_time, compare in UTC,
one decision_time per evaluation. Naive timestamps are rejected.

FRONTEND ROUTES
/ -> /cases | /cases/:caseId | /cases/:caseId/timeline | /imports,
/imports/:runId | /evaluations/:runId | /rul-runs/:runId (stub) |
/simulations/:runId (stub) | /admin (read-only metadata + run launcher) |
/not-found
UI rules: show backend gate + case version, never recompute. Explicit
loading/error/empty/stale/pending/conflict states; a failed GET must not look
like empty data. Status shown as text as well as colour; keyboard operable;
no "saved" message until the server confirms. Filters live in the URL.
No client-side re-ranking.

SECURITY
Startup-configured principal (fail startup if missing). Capabilities checked
server-side: case read, import, evaluate, disposition, run launch, metadata,
artifact read. Never trust a role from the request body. Same-origin checks
on mutations. Import allow-list + size/record caps. Artifact path
traversal/symlink rejection. No secrets or raw sensitive bodies in logs.
No subprocess except a fixed allow-listed runner with a timeout.

IMPLEMENTATION ORDER (do not reorder)
00 repo conventions + pinned versions + check scripts
01 contracts: enums, Pydantic DTOs, committed OpenAPI 3.1, TS types
02 DecisionGate oracle + truth-table tests (before any screen)
03 SQLite/Alembic schema + repositories + transaction tests
04 intake + validation (four domain contracts, reason codes)
05 identity/time linkage + versioned case assembly
06 ranking + feasibility + single evaluation use case
07 REST API with errors, idempotency, version checks, RBAC
08 frontend vertical slice: queue -> case card -> timeline -> disposition
09 bounded run coordination + artifact registry + reconciliation
10 frozen verification package (dev cases, 240 holdout, stateful tests)
11 stubs for Gate B/C only (NOT_RUN/PENDING)
12 packaging, clean run, backup/restore check

FIRST TASK (do this now)
Scaffold both projects with pinned manifests; freeze enums/DTOs/OpenAPI;
implement DecisionGate with the precedence above; add the initial migration;
round-trip ONE synthetic case through POST /cases/{id}/evaluations and
GET /cases/{id}. Test: missing policy, unresolved evidence, hard violation,
unknown prerequisite, RUL not accepted, stale version, idempotency replay,
persistence failure (=> error, no gate). Add OpenAPI validation and a
requirement-to-test traceability lint.

DEFINITION OF DONE
Clean install + migration succeed; OpenAPI validates; every gate truth-table
row passes; persisted evaluation holds reasons, case version, config
fingerprint; failed transaction returns no gate; no secret and no write-back
path exists. Label tests PASSED / FAILED / NOT_RUN / BLOCKED honestly.

WORKING RULES
If a value is unspecified, do NOT invent it silently: put it in
docs/decision-register.md and use a visible, versioned fixture/config value.
After each step, report what ran, what passed, and what is still open.
```

---

# PART B: SUPPORTING DOCUMENTATION

## 1. Problem and purpose

**Official problem (SIH26249):** low aircraft availability due to fragmented and largely reactive maintenance. Data from aircraft health-monitoring systems, technical records, spares and maintenance agencies is not integrated, causing delayed fault prediction, avoidable downtime and sub-optimal use of critical assets.

The research concluded the gap is not just a missing prediction algorithm. It is the lack of demonstrated proof that cross-domain data can be joined correctly, turned into feasible decisions, passed through a control gate and evaluated. The proposed differentiator is **traceable integration plus one shared gate**, not a claim that RUL prediction is new.

Four problem threads drive the design: P1 fragmented evidence, P2 delayed prediction, P3 the actionability gap (a warning does not prove a compatible part, capacity, window or approval exists), P4 the impact-evidence gap (a dashboard does not prove availability improved).

## 2. Users and roles (demo roles, to be confirmed with a sponsor)

| Role | What they do in the prototype |
| --- | --- |
| Maintenance planner / fleet-readiness analyst (primary) | Filter queue, inspect case, request evaluation, record disposition |
| Analyst | Inspect evidence quality, linkage, RUL scope |
| Reviewer | Record a local disposition (this is not maintenance approval) |
| Logistics / agency | Supply spares and capacity evidence (via fixtures) |
| Evaluator | Run frozen checks, read manifests and reports |

## 3. Workflow

1. Import allowed fixture
2. Validate contract
3. Resolve asset / configuration / time
4. Assemble versioned case
5. RUL status and rank
6. Check feasibility
7. DecisionGate
8. Persist trace and show result

## 4. Feature map

| ID | Feature | Status |
| --- | --- | --- |
| F01 | Four-domain intake, contracts, lineage | Core MVP |
| F02 | Configuration-aware temporal linkage | Core MVP |
| F03 | RUL result or explicit status | Core (status only until Gate B) |
| F04 | Deterministic ranking | Core MVP |
| F05 | Constraint feasibility | Core MVP |
| F06 | Shared fail-closed gate | Core differentiator |
| F07 | Evidence-backed case card | Core MVP |
| F08 | Human review and local disposition | Core MVP |
| F09 | Versioned case/event history | Core MVP |
| F10 | Fleet simulation | Conditional (Gate C) |
| F11 | Outcome/delay analytics | P1 extension |
| F12 | Frozen tests, replay, fault injection | Core acceptance |
| F13 | Access, audit, reproducible packaging | Core MVP |
| F14 to F20 | Intervention-risk, global scheduler, federated analytics, operational offline mode, auto-retraining, physics residual, progressive inference | Deferred |

## 5. Requirements summary

There are 26 functional requirements (FR-001 to FR-026) and 16 non-functional requirements (NFR-01 to NFR-16) in the RTM. The ones that matter most for the prototype:

- **FR-002 / FR-021:** contract validation is reason-coded; unknown units are never silently coerced; no exception may default to READY.
- **FR-004:** only approved aliases and half-open validity windows resolve identity.
- **FR-009 / FR-010 / FR-024:** only DecisionGate emits gate\_state; reasons and config fingerprints are persisted; missing applicability policy gives HOLD.
- **FR-012 / FR-013:** dispositions use allowed values, expected version and idempotency; history is append-oriented.
- **FR-018 / FR-022:** server-enforced demo roles; no operational write-back.
- **NFR-01:** zero critical-invalid cases reach READY. **NFR-02:** at least 95% of 120 valid holdout cases retained. **NFR-03:** zero accepted hard-constraint violations. **NFR-04:** 100% required trace fields. **NFR-05:** deterministic replay.

## 6. Synthetic fixture design

The research does not supply target schemas, so fixtures come first. **\[ASSUMPTION\]** Suggested minimum contracts, each carrying `schema_version`, `source_record_key`, `record_version`, `event_time` (with offset), `ingest_time`, `evidence_class`:

- **Health:** asset\_id, component\_id, sensor/parameter, value, unit, quality flag.
- **Technical records:** component install/removal events, aliases, configuration id, valid\_from, valid\_to.
- **Spares:** part number, compatible components, quantity, serviceable flag, lead time, as-of time.
- **Agency / work orders:** agency id, capability, bay capacity, window start/end, approval status, as-of time.

**Holdout structure (from the research, FR-016):** 240 locked cases, 120 valid and 120 invalid. The invalid half has six fault families at 20 each: identity/epoch, stale or unknown time, schema/version, unit/type, duplicate/conflict, and infeasible constraint. Add at least 40 development cases for tuning, plus a separate stateful pack for duplicate imports, changed evidence invalidating old READY, concurrent dispositions, DB/file failure and missing artifacts.

## 7. Ranking policy

The research requires a deterministic, versioned, transparent policy with visible factor reasons and a frozen tie-break, but does **not** fix the factors' values. Factors named: validity, urgency, consequence, warning lead time, uncertainty/quality, feasibility.

**\[ASSUMPTION\]** Start with a lexicographic order: validity, then feasibility state, then urgency, then consequence, then warning lead time, then data quality; tie-break by case\_id ascending. Unknown factors sort last and show a reason code. Freeze it in a versioned `rule_config_versions` row and in golden test vectors. State in the UI that this is a demo policy, not operational doctrine.

## 8. Feasibility rules

For each prerequisite (compatible part, serviceable stock, agency capability, capacity, maintenance window, approval): FEASIBLE if trusted, current evidence supports it; INFEASIBLE\_HARD only if trusted, current, resolved evidence shows a violation (for example an incompatible part); otherwise UNKNOWN. UNKNOWN or stale maps to HOLD at the gate.

## 9. Gate truth table (use as test oracle)

| Scenario | Expected |
| --- | --- |
| Persistence failure during evaluation | Operation error, no gate result |
| RUL applicability policy missing or invalid | HOLD |
| Identity UNRESOLVED or CONFLICT | HOLD |
| Hard violation on trusted, current evidence | BLOCK |
| Hard violation on stale or unresolved evidence | HOLD (not BLOCK) |
| Spares or agency data unknown or stale | HOLD |
| RUL required but PENDING / OUT\_OF\_SCOPE | HOLD |
| Everything valid, feasible, RUL not required or accepted | READY\_FOR\_HUMAN\_REVIEW |

Note the interaction: precedence puts "evidence unresolved" ahead of "hard violation", so a violation only BLOCKs when its supporting evidence is itself trusted and current.

## 10. Three evidence gates beyond Gate A

- **Gate B, RUL model evidence (conditional):** needs task fit and licence review (candidates C-MAPSS or N-CMAPSS), unit-separated split, transparent baseline, MAE/RMSE, pre-registered acceptance rule, final holdout never used for tuning. Until it passes, RUL is PENDING or OUT\_OF\_SCOPE. Public benchmark scores must never be presented as target-fleet accuracy.
- **Gate C, simulation (conditional):** only after state model, assumptions, formulas and matched-run tests are frozen; every output labelled SIMULATED; otherwise NOT\_RUN.
- **Gate D, operational pilot (external):** needs authorised data, confirmed roles, approved KPIs, security review and identity decisions. Not part of this prototype.

## 11. Risks to design against

| Risk | Mitigation |
| --- | --- |
| Wrong identity/config/time join | Approved mappings, half-open intervals, UNRESOLVED state, seeded tests |
| Gate logic duplicated across layers | One DecisionGate, one evaluation use case, route-bypass tests |
| RUL overclaim | Separate Gate B, status vocabulary, no accepted number without acceptance |
| DB says done but artifact missing | Temp write, hash verify, register, reconcile on read, never fake COMPLETED |
| Unbounded upload or run | Caps, allow-list, timeout, one active run |
| Demo persona mistaken for real auth | Visible demo-only banner, no role switch endpoint |
| Scope creep | Gate A first; defer F14 to F20 |

## 12. Open decisions (record, do not silently decide)

Target data schemas and clocks; RUL target subsystem and acceptance threshold; simulation state model and KPI denominators; production identity and role mapping; hosting, TLS and recovery targets; repository host and CI provider; audit and retention objectives. None of these block Gate A.

## 13. Demo script suggestion

1. Import a clean fixture, show validation counts.
2. Open the queue, filter by gate\_state, show deterministic order.
3. Open a READY case: evidence links, RUL shown as PENDING, rank reasons, feasibility.
4. Open a HOLD case (stale spares) and a BLOCK case (incompatible part), showing reason codes.
5. Record a disposition; show the timeline entry and that no operational system changes.
6. Re-import changed evidence; show the old READY superseded and prior history preserved.
7. Run the frozen suite; show raw counts, manifest and honest NOT\_RUN labels for Gate B/C.

## 14. Honest limits to state out loud

Synthetic proof is not operational proof. Thresholds are project gates, not aviation standards. History is append-oriented, not tamper-proof. The local demo identity is not enterprise authentication. A listed test ID means a verification path exists, not that it has passed.
