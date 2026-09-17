# Policy Assignment System: MVP Implementation Plan

## Goal

Build a complete, small take-home demonstration for one company with seeded data. HR can define rules, resolve assignments for any selected employees on a date, make manual exceptions, and preview assignment changes when employee information, rules, or group membership changes. Deliver five sequential PRs, each with working UI and a manual walkthrough.

This plan defines implementation scope. The [schema proposal](policy-assignment-schema.md) describes the model and extension possibilities; its deferred workflows are not prerequisites for the MVP.

**Implementation status:** PRs 1–4 are implemented and pushed as branch increments. PR 5 is implemented locally with 47 passing backend tests, generated API types, and frontend checks; see the [end-to-end walkthrough](docs/pr5-walkthrough.md). Human UI review and the final push/submission remain. No automated browser tests are included.

## Required versus deferred

| Requirement | MVP behavior |
|---|---|
| Define rules | Small AND-condition builder, target policy, effective date, and rule ordering within a category. |
| Resolve any employee set on a date | Assignments report with employee selection, date, category/policy filters, and explanations. |
| Cardinality and conflicts | Single-category winner by lowest numeric priority then stable rule ID; multiple-category union; explicit overrides; visible required-coverage errors. |
| Reconciliation | Employee, group, override, and rule edits atomically update inputs and stored timelines. Known tenure and future-date transitions are calculated in advance. |
| HR usability | People, Policies, and Assignments screens; readable explanations; before/after previews; a basic Add employee form with start-date assignments. |
| Auditability | Input revisions with actor/time/reason and assignment-change records, without a dedicated audit screen. |
| Developer experience | Pure resolver, small field registry, typed API, understandable transactions, and documentation in every PR. |

Use seeded categories, departments, groups, and example policies. Allow adding a simple policy within an existing category. Keep category cardinalities fixed and reporting relationships as inputs. Do not implement payroll or other feature-specific policy logic.

Defer retirement/replacement change sets, archive controls, historical correction/cancellation screens, termination/rehire editors, a multi-step onboarding wizard, a separate stale-preview rejection protocol, audit events/history UI, authentication, tenancy, asynchronous jobs, and external integrations. Employment boundaries and historical revisions still work in the domain model. Avoid building infrastructure merely because a future feature might use it.

## Stack and extension points

Use FastAPI, SQLAlchemy, Alembic, and PostgreSQL for one backend; React, TypeScript, and Vite for the frontend; Docker Compose and a small Makefile for local setup. Pin dependencies during implementation. Generate TypeScript API types from backend OpenAPI so client/server contracts stay aligned.

Keep four ordinary modules:

- Snapshot loading: batch-load dated employee facts, groups, rules, and overrides.
- Field registry and resolver: typed field definitions and pure evaluation functions, independent of HTTP and database writes.
- Timeline/reconciliation service: boundary discovery, interval comparison, and transactional persistence.
- API/UI: translate forms into commands and display server-calculated previews/results.

Adding a field means declaring its type, operators, label, reader, input dependencies, and any date boundaries; persisted facts may also need a migration. Adding a policy in an existing category is data entry. Later editing workflows reuse revision and preview/save services. Do not create a plugin framework or generic workflow engine.

## Decisions and conventions

- **Clock:** A backend `APP_TODAY` override fixes the demo date; without it, use the configured company timezone. Expose the effective date to the UI. Seed dates and “Today” labels use this clock. Stored timelines have no clock-dependent horizon.
- **Dates:** Effective dates are Python/PostgreSQL dates and API/frontend `YYYY-MM-DD` strings, never JavaScript timestamps. Use exclusive interval ends and clear form labels. Recorded-at metadata uses UTC timestamps.
- **Seeds:** Approximately 15–20 employees with stable IDs. Named scenarios: Jamie moves to California, Morgan reaches 24 months of tenure, and a direct report moves from Alex to Sam. Include default, department, employment-type, location, tenure, group, and manager rules. An explicit seed command adds missing fixtures without overwriting edited rows; document any reset requirement per PR. Startup never resets data. Once reconciliation exists in PR 2, seed insertion finishes through its normal transaction path so fixture changes update stored assignments atomically.
- **Migrations:** Handwrite/review PostgreSQL exclusion constraints and `btree_gist` setup rather than relying on Alembic autogeneration.
- **Explanations:** Define a typed, versioned structure in PR 2: decision code, category/policy IDs, exact input revisions and evaluated facts, matched rules, winning/contributing sources, and applicable overrides. Order collections deterministically. Exclude query dates and calculation timestamps from interval equivalence. Explain tenure using stable threshold facts rather than embedding a count that changes within an otherwise identical interval. Prose is presentation, not the key for comparison.
- **Timelines and reads:** Store each employment's entire timeline, ending in an unbounded range when employment has no end date. Registry fields must enumerate a finite, complete set of truth-change boundaries for the actual rule operands. For example, tenure `gte 24` has one anniversary boundary; `equals 24` also ends at month 25. Stored input dates and direct-report dates supply other boundaries. Reject unsupported predicates whose boundaries cannot be enumerated. No coverage table, extension action, special read path, or daily job is needed. Date reads never write.
- **Ordering and scheduled edits:** Lower numeric priority comes first (1 before 2); stable rule ID breaks ties. Reject a reorder/edit whose affected rules have conflicting future versions, rather than silently overwriting a schedule. Keep earlier versions intact. MVP onboarding requires a start date today or later; past-start onboarding is deferred, though seeds can contain historical employment.
- **Writes:** One company-wide database transaction lock acquired before loading inputs, with fresh committed visibility after acquisition. Save revisions, recomputed intervals, and change records atomically. Revalidate on save and show the actual saved impact, including any difference from the preview; no extra stale-preview approval workflow.
- **Documentation:** Start README, schema/system diagram, setup steps, and tradeoffs in PR 1; update in every PR.

## PR 1 — Directory and policy catalog

**Visible UI:** Searchable People directory, employee profiles, and a Policies catalog grouped into “Choose one,” “Optional,” and “Multiple allowed.” All read from PostgreSQL.

**Implementation:** Scaffold local development, migrations, seeds, clock/date conventions, and generated API types. Add employee identity, employment/attribute revisions, departments, groups/memberships, categories, and policy data. Establish actor/reason/supersession metadata from the beginning. Include useful loading/error states and initial documentation.

**Human walkthrough:** Start the app, find Jamie, inspect location/manager/start date, browse pay schedules and apps, and confirm the demo date is visible. Restart and verify data remains.

**Tests:** Migration/seed loading, representative foreign-key and interval-overlap constraints. Frontend type checking and build. No static markup tests.

## PR 2 — Resolver, timelines, and multi-employee report

**Visible UI:** Employee assignments with “Why?” and a simple past/future timeline. An Assignments report supports any employee subset, evaluation date, category/policy filters, and explanations. Show readable seeded rules on policy details.

**Implementation:** Add rule versions, field registry, batch snapshot loader, point resolver, and timeline wrapper. Support employment-limited coverage, priorities/ties, multiple-policy deduplication, groups, tenure, and derived manager status. Define the canonical explanation format before interval merging.

Add assignment intervals, reconciliation runs, and change records. Enumerate finite boundaries from dated inputs and actual tenure predicates, resolve every segment including the final unbounded segment, and merge equivalent assignments/provenance. Establish the shared transaction path, idempotent diffing, and full materialization. Finish seed changes through this path. No horizon or daily job is needed. Keep this PR together initially; if it becomes difficult to review, split live resolver/report and stored timeline work into two runnable PRs, each with visible UI, before enabling editing.

**Human walkthrough:** Select Jamie and international employees in the report and compare pay schedules. Inspect Engineering app access. Move the date across Morgan's anniversary and inspect vacation changes. Query a far-future date and confirm the stored final interval applies without a write.

**Tests:** Compact table-driven cases for supported conditions, priority/ties, deduplication, employment coverage, and February 29 tenure behavior. Targeted finite-boundary/merge and provenance cases, database cardinality checks, stored timeline agreement with point resolution on sampled dates (including boundaries and far future), unchanged reruns, and rollback. One concurrency test uses two database connections with controlled transaction ordering, not timing-dependent racing threads.

## PR 3 — Manual exceptions

**Visible UI:** Set/add/exclude/clear controls with effective date, optional end date, reason, and before/after preview. Show manual badges, visible exclusions, and “Use automatic assignment.”

**Implementation:** Add override revisions and constraints; integrate override boundaries into resolution. Introduce reusable preview/save handling: proposed inputs resolve in memory, while save reloads and validates under the transaction lock. Invalid choices fail without partial changes. Expiration or ending an override resumes the rules applicable on that date. Preserve prior evidence. Limit overrides to the relevant employment period so exceptions do not carry into a later rehire.

**Human walkthrough:** Temporarily set Jamie to monthly pay, inspect automatic return after expiration, exclude GitHub while retaining other apps, and restore automatic assignment. Confirm the report agrees with the profile.

**Tests:** Table-driven action/expiration cases, persistence through recomputation, and an integration scenario for invalid/overlapping exceptions and rollback. Reuse existing reconciliation tests.

## PR 4 — Employee/group changes and basic onboarding

**Visible UI:** Effective-dated employee edits for location, department, employment type, and manager, with impact previews. Edit seeded group memberships. A single Add employee form previews assignments for the start date.

**Implementation:** Reuse revisions and preview/save transactions. Recompute edited employees and affected old/new managers, including relevant direct-report employment boundaries. Group changes include removed members. Prefer conservative recomputation when dependencies are uncertain.

Limit edits and onboarding start dates to today/future dates; preserve earlier intervals. Reject conflicting scheduled edits with an actionable message rather than building cancellation/correction editors. When onboarding or an employee edit leaves required coverage gaps, show a policy selector and override reason beside each gap. Include those set overrides in the same preview and atomic save as identity/employment/attribute changes. A new employee must not have to exist first to resolve a gap. Other exceptions remain available from the profile.

**Human walkthrough:** Move Jamie to California and verify training is added while manual pay persists. Remove group membership and inspect lost access. Move a report from Alex to Sam and inspect both managers. Add an employee and compare previewed and saved policies. Exercise an uncovered required category during onboarding and an employee edit; choose an inline set override and save successfully.

**Tests:** Location/group-removal reconciliation, old/new manager effects, onboarding and employee edits with inline coverage-fixing overrides saved atomically, rejection without a gap fix, revalidated save results, and preservation of earlier dated results after a future edit. Avoid repeating the same API assertions for every field.

## PR 5 — Rule authoring and MVP handoff

**Visible UI:** Create a policy in an existing category. Create/edit/end rules using readable registry-driven dropdowns; move rules up/down and preview assignment gains, losses, and switches. Identify unchanged manual exceptions in the preview.

**Implementation:** Store entity IDs in conditions and validate operators. Version rule edits and reordered priorities atomically. Recompute the whole company, including former matches. Preserve required-category coverage or reject saves with actionable gaps. Use the existing preview/save path; no retirement/replacement workflow.

Finish the reproducible demo walkthrough, update architecture/schema diagrams and tradeoffs, and document how to add a field and policy category. Incorporate human UI feedback. Catalog defaults, rule editing, and Add employee provide the setup/onboarding story without another wizard.

**Human walkthrough:** Create an app policy and department rule, preview/save, then change the department and verify gains and removals. Reorder matching pay rules and inspect the winning explanation. Repeat Jamie's move and manual override as the complete demonstration.

**Tests:** Invalid condition validation, lower-number-first ordering, conflicting future-version reorder rejection, historical ordering, former matches losing assignments, coverage-gap rejection, and preserved explanation evidence. Run the accumulated suite, migrations, frontend type checking/build; add regression cases only for actual defects found during review.

## Handoff and completion

Every PR includes updated docs, checks actually run, and a short human walkthrough with explicit dates and named employees. Implement one PR-sized increment at a time. The full MVP is complete after rule creation, batch/date resolution, manual overrides, employee/group/rule reconciliation, tenure transitions, and explanations all work together from a fresh setup.

Maintain one focused backend suite instead of duplicating domain assertions across endpoints. Browser interactions, visuals, keyboard/accessibility checks, and walkthroughs belong to the human. No computer-use/browser automation or screenshot tests.

Document future scale through dependency filtering, per-employee locks with shared-input revision coordination, tenant isolation, and transactional outbox delivery. These are extensions, not infrastructure to build for the demo. Do not start deferred workflows just because the schema can accommodate them.
