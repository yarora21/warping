# Policy Assignment System: Schema Proposal

Status: design reference. The [MVP implementation plan](implementation-plan.md) defines delivery scope; lifecycle and editing extensions below are not all part of the MVP.

## Scope and approach

Build a small relational model in PostgreSQL: employees and their history, policies, and rules that connect them. Separate the rules that determine assignments from the assignments we calculate.

This implementation serves one company with fake seeded data. A single application and a clear resolver function should be enough; tenants, distributed processing, and a separate rules engine are unnecessary for this scope. Favor a design that is straightforward for a human developer to understand and extend.

The MVP includes rule authoring, batch/date resolution, manual overrides, basic onboarding, employee/group edits, timelines, and explanations. Defer retirement/replacement and archive controls, correction/cancellation screens, termination/rehire editors, and a dedicated audit UI. Retain temporal inputs and evidence for later extensions. MVP edits apply today or in the future. Use a backend `APP_TODAY` override for reproducible demo dates and date-only `YYYY-MM-DD` values across the API/frontend.

## 1. Model the thing being assigned

An **assignment category** is the set of assignments that share a cardinality constraint.

| Category | Cardinality | Example targets |
|---|---|---|
| Pay schedule | Exactly one | Monthly, biweekly |
| Vacation | Exactly one | Standard vacation, extended vacation |
| Sick leave | At most one | Standard sick leave |
| Application access | Many | Slack, GitHub, Figma |
| Compliance training | Many | Security training, manager training |

Vacation and sick leave must be separate categories because someone can have one of each.

```text
assignment_categories
  id
  name
  key                    unique, stable identifier
  cardinality            exactly_one | at_most_one | many

policies
  id
  category_id

policy_versions
  id
  policy_id
  name
  description
  effective_from
  effective_to
  archived               deferred control; false in MVP
```

The assignment system should know that “Biweekly” is a pay schedule, but payroll owns what biweekly pay actually does. We do not need to recreate each feature's business logic.

**Policy lifecycle controls (deferred):** Archiving hides a policy from new selections without ending existing assignments. Retirement ends its effective availability. A future retirement workflow must preview its impact and save necessary replacements atomically. Overrides cannot bypass policy effective dates. Keep historical policy versions available for explanations; the MVP has no retirement or archive editor.

For this implementation, reporting relationships are employee inputs only. Rule-based manager assignment is outside scope. Derive `is_manager` from whether an employee has active direct reports on the requested date.

## 2. Keep dated employee information

A mutable employee row cannot answer “what applied before this person moved to California?” Attributes used by rules need effective dates.

```text
employees
  id
  name
  email

employments
  id
  employee_id
  start_date
  end_date               nullable; exclusive

employee_versions
  id
  employment_id
  effective_from
  effective_to           nullable; exclusive
  employment_type
  country
  state
  department_id
  manager_id
```

Use typed columns for supported attributes. This keeps the schema understandable, validates data naturally, and makes the rule builder easier to implement. `department_id` references a small department lookup table; `manager_id` references an employee.

Each version describes an employment during `[effective_from, effective_to)`. Enforce nonoverlapping active versions within an employment and, for this implementation, nonoverlapping employment periods for an employee. Require complete attribute coverage during employment. A rehire creates a new employment record. Assignments and required-category coverage checks apply only inside employment periods.

Calculate tenure as completed calendar months in the current employment. Month anniversaries are calculated from the original start date and clamped to the last valid day of the target month; a February 29 hire reaches their annual anniversary on February 28 in a non-leap year. Previous employment does not carry over for this demo. Do not store a tenure value that silently becomes stale.

For groups:

```text
groups
  id
  name

group_memberships
  id
  group_id
  employment_id          scopes membership to one employment
  effective_from
  effective_to
```

For the first version, groups can be explicitly maintained collections of employees. Dynamic selection already exists through rules; nested groups would add complexity without helping the demonstration much.

Memberships and overrides reference a stable employment identity; validate their intervals are contained within the current employment period. Rehires do not inherit them. Employment revisions retain that identity while preserving changes to employment dates.

### Shared revision convention

All assignment-affecting inputs, including employment periods, memberships, policies, rules, and overrides, preserve historical revisions. The table sketches omit common revision metadata for readability: each revision records a stable logical identity, `created_at`, `created_by`, `change_reason`, and supersession metadata. Business values on a recorded revision are immutable; only supersession metadata may be set once to retire it from the current interpretation of history.

A scheduled change replaces the current interval representation with revisions covering the unchanged earlier interval and the new later interval. Perform replacement and nonoverlap validation atomically; overlap constraints apply to nonsuperseded revisions. **Correction/cancellation editors (deferred):** Corrections would replace the affected interval while retaining superseded rows; cancellation would retain the withdrawn revision plus actor/time/reason. The MVP rejects conflicting scheduled edits rather than providing these editors.

Historical explanations reference exact revisions and capture the relevant evaluated values and display labels. This preserves evidence even after corrections or renames. It does not promise a general bitemporal query API.

## 3. Define rules and explicit employee overrides

```text
assignment_rules
  id
  name

assignment_rule_versions
  id
  rule_id
  policy_id
  effective_from
  effective_to
  priority
  conditions             jsonb
  created_at
  created_by
  change_reason
```

A normal rule has conditions such as:

```json
{
  "all": [
    { "field": "country", "operator": "equals", "value": "US" },
    { "field": "department_id", "operator": "equals", "value": "dept_engineering" },
    { "field": "tenure_months", "operator": "gte", "value": 24 }
  ]
}
```

Support a small, validated vocabulary of fields and operators, with a flat “all conditions match” builder initially. Do not allow arbitrary SQL or executable expressions.

Use stable IDs for entity references; names are display labels. Support a `group_ids` condition with the `in` operator, defined as membership in any selected group on the evaluation date.

### Field registry

A plain code registry declares each field's type, allowed operators, UI label, snapshot reader, input dependencies, and date-boundary calculation where applicable. Validation, the rule builder, evaluation, and reconciliation scoping use this shared definition. For example, `tenure_months` depends on employment dates and produces relevant anniversary boundaries; `is_manager` depends on active direct reports and their reporting relationships. Persisted attributes still require migrations. Keep this a small code structure rather than a plugin framework.

Each supported predicate must enumerate a finite, complete set of truth-change dates for its actual operands. Tenure `gte 24` produces the month-24 anniversary; `equals 24` also produces month 25. Do not enumerate every future month. Unsupported predicates without finite boundaries are rejected until a different temporal strategy is designed.

Manual overrides are a first-class feature. Store them separately from population rules so an HR user can manage an exception directly on an employee's profile without creating a special rule. Both inputs go through the same resolver and explanation path.

```text
employee_assignment_overrides
  id
  employment_id          stable employment identity; employee derived through it
  category_id
  policy_id              nullable only for clear
  action                 set | add | exclude | clear
  effective_from
  effective_to           nullable; exclusive
  created_at
  created_by
  reason                 required
```

Override behavior depends on the category:

| Category | Available actions | Meaning |
|---|---|---|
| Exactly one | Set | Replace the automatic choice with a selected policy |
| At most one | Set, clear | Select a policy or explicitly leave the category unassigned |
| Many | Add, exclude | Include or exclude a specific policy while other policies continue to follow rules |

Validate that the policy belongs to the category and that the action is allowed. Prevent overlapping override periods for the same employee/category in single-assignment categories, or the same employee/policy in many-assignment categories. Replacing an override ends the previous period on the replacement's effective date. Preserve previous values and actor/reason in the audit history when correcting or cancelling a scheduled override.

An override persists through employee, group, and rule changes until it expires or HR chooses “Use automatic assignment.” Ending it resumes the rules applicable on that date, rather than restoring a potentially outdated previous assignment. Manual exclusions must survive reconciliation just like manual additions.

For single-assignment categories, the resolver chooses:

1. An applicable manual override.
2. Otherwise, the matching rule with the lowest numeric priority (1 before 2).
3. If priorities tie, the lowest stable rule ID.

The override constraints prevent competing manual choices. The UI should warn about rule priority ties even though resolution is deterministic. Avoid implicit “most specific rule wins”—specificity becomes surprisingly hard to explain.

Rule order is per category. “Move up/down” creates new effective-dated versions of the affected rules in a single transaction, preserving the earlier order. For the small initial rule set this is simpler than a separate ordering model. The UI assigns distinct priorities; the resolver retains stable-ID tie-breaking as a deterministic fallback.

The first visible rule has the lowest priority number. Reject a reorder/edit with conflicting future versions of affected rules; scheduled-version splitting beyond the ordinary current-period split is deferred.

For many-assignment categories, take the union of matching policies and manual additions, remove duplicates, and subtract manually excluded policies.

An “exactly one” category also needs a coverage check: if nothing matches, return a visible configuration error. A default rule with no conditions and a high numeric priority (last in order) provides normal coverage.

## 4. Resolve and store assignment timelines

Make this function the center of the application:

```text
resolve(employee_ids, as_of_date)
  → assignments, winning rules, competing rules, coverage errors

resolve_timeline(employee_id)
  → assignment intervals, explanations, coverage errors
```

The point resolver reads dated inputs and explains every result. The timeline resolver splits a requested period at every relevant change boundary: employment, attribute, membership, rule, policy, and override starts/ends, plus tenure thresholds and direct-report changes. Resolve each segment, then merge adjacent segments only when both assignments and their provenance are equivalent. This supports previews and stored historical, current, and scheduled assignments using the same logic.

```text
employee_assignments
  id
  employee_id
  category_id
  policy_id
  valid_during           daterange; [start, end), unbounded end allowed
  is_single              constrained to category cardinality
  explanation            jsonb; exact input revisions and contributing sources

```

For single-assignment categories, prevent overlapping assignment ranges for an employee/category. For many-assignment categories, prevent overlapping ranges for the same employee/policy. Carry `is_single` as a constrained category property so a partial exclusion constraint can enforce the first invariant; use composite foreign keys to enforce category/policy consistency. Category cardinality is fixed in this implementation. “Exactly one” additionally requires resolver coverage validation; an exclusion constraint alone only enforces at most one.

Explanations include all contributing rules for a many-assignment policy, not just one source ID. Explicit clears and exclusions remain explainable from retained override revisions even when no assignment row exists.

Materialize each employee's entire employment timeline from the finite set of relevant boundaries. For ongoing employment, resolve the last boundary once and store an unbounded final interval where applicable. There is no horizon, coverage table, or extension action. Date reads use stored results without writes. The demo clock affects the selected date and fixture generation, not timeline completeness. Future results reflect currently recorded inputs, not a guarantee those inputs never change.

### Reconciliation and consistency

Recompute affected employees' full timelines. Previews do not persist results. Diff intervals and explanations, writing only changes. A provenance change is recorded even if the policy stays the same. Identical reruns produce no assignment-change entries. Define a typed, versioned explanation structure with deterministic ordering and exclude volatile calculation metadata from interval-equivalence comparisons.

For this single-company implementation, serialize assignment-affecting writes with one database transaction lock acquired before reading resolver inputs. Save input revisions, recalculated assignments, and assignment-change records in the same transaction. Reject unresolved required-coverage gaps; onboarding and employee edits can include inline set overrides in the same preview/save to fix them. Revalidate previews at save time. The seed command also reconciles through this transaction path once the resolver exists.

Employee, membership, and override changes recompute affected employees. Reporting changes also include the previous and new manager; employment starts and ends can change a manager's status. Rule and policy changes may recompute the whole population. Known future changes and tenure crossings are already represented in stored intervals. No periodic job is required for correctness.

## 5. Audit inputs and assignment outcomes

Defer a dedicated audit log and history screen. Preserve input revisions with actor, time, and reason, plus assignment-change records and explanations. These provide the evidence needed to answer “Who changed the rule and why?” and “Which assignments changed because of it?” without a generic audit subsystem or event sourcing.

```text
reconciliation_runs
  id
  actor
  reason
  employee_ids           reconciled population
  created_at

assignment_changes
  id
  run_id
  action                 assigned | removed
  snapshot               jsonb; employee/category/policy, interval and explanation

```

Write revisions and assignment-change records in the same transaction as their changes. Require human reasons for overrides and historical corrections; routine edits can use a generated description with an optional note. Keep prior revisions even after an override ends or a rule is retired. Use a clearly identified seeded HR actor for the local demo; authentication is outside the initial scope.

PR 2 records changed intervals as removal/addition pairs linked by a reconciliation run, preserving both explanations without a separate change-event abstraction. A no-op reconciliation writes neither a run nor change records.

A later history view can assemble actor, recorded time, effective date, before/after values, reason, and linked assignment impact from these records. Add a dedicated event table only when a concrete workflow needs it. The initial UI exposes assignment explanations and override attribution, not a separate history screen.

Stored timelines answer “what applies on date Z according to our current recorded history?” Immutable revisions and assignment-change records also preserve earlier computed results and their evidence after a retroactive correction. Keep recorded time and effective dates visibly distinct.

## 6. Design the interface for HR

Use People, Policies, and an Assignments report, with group management accessible from People. The report selects any employee set and date, filters by category/policy, and exposes explanations. Favor readable tables, clear labels, sensible defaults, and short forms. Technical concepts such as JSON conditions, cardinality, and reconciliation should stay out of the HR workflow.

### Initial setup and policy rules

Start with seeded employees and example policies so the application is immediately understandable. Organize policies by recognizable categories such as Pay schedule, Time off, Apps, and Training. Show category constraints as “Choose one,” “Optional,” or “Multiple allowed.”

Creating a rule should read like a sentence: “Assign Extended vacation when Tenure is at least 24 months.” Use dropdowns and searchable selectors for employee attributes, departments, locations, and groups. Show a matching employee count with an expandable list. Let HR order rules using “Move up” and “Move down”; explain that the first matching rule wins for categories that allow one assignment. Store that order as priority internally.

Before saving a rule, show its effective date and a compact impact preview: employees gaining, losing, or switching policies, plus employees whose manual overrides keep their assignments unchanged. Highlight missing required assignments with a link to resolve them.

### Employee assignments and overrides

On an employee profile, group assignments by category. Show the policy, an “Automatic” or “Manual” badge, and a “Why?” link. The explanation should use plain language, for example: “Extended vacation applies because Jamie has at least 24 months of tenure.” For a manual choice, show who made it, their reason, and its dates.

Use a “Change assignment” action that opens a short form with the available policies, effective date, optional end date, and reason. For categories allowing multiple assignments, support both “Add policy” and “Exclude policy.” Keep exclusions visible so an absent assignment is explainable. For optional single-assignment categories, offer “Leave unassigned”; required categories must have a selected policy.

Show a before/after preview in the same form. An active override should offer “Use automatic assignment,” with a preview of what the rules would assign when the override ends. Creating an exception must not require visiting the rule builder.

### Onboarding and employee changes

During onboarding, show assignments calculated for the employee's start date after their employment details are entered. If a required category has no assignment, offer a policy selector and reason to include a set override in the same save. Employee edits use this same gap-fixing flow. Other exceptions can be managed on the profile. MVP start dates must be today or later; past-start onboarding is explicitly deferred.

When an employee's location, department, or other relevant attribute changes, show assignment changes alongside the edit before saving. For example: “Moving Jamie to California adds CA Meal Break training. Monthly pay stays unchanged because of a manual override.” Use the same resolver for previews and saved results, and re-evaluate against current inputs when saving.

Provide an “As of” date selector on employee assignments for historical and future views, clearly labeled with the selected date. Distinguish scheduled changes from assignments active today. Keep errors specific and actionable, such as “No pay schedule matches Jamie. Choose a default rule or set a manual assignment.”

## Testing approach

Test the resolver with a handful of representative cases:

- Priority conflicts and deterministic tie-breaking.
- Manual replacement, addition, and exclusion; expiration or removal returning to automatic rules.
- Multiple app assignments and deduplication.
- Effective-date boundaries and employment-limited resolution, using seeded data rather than deferred employment lifecycle editors.
- Tenure transitions, including a February 29 anniversary.
- Timeline reconciliation removing an obsolete assignment and producing no changes on an identical rerun.
- A reporting change updating old/new managers' training assignments.
- Stored timelines matching point resolution on sampled dates, boundaries, and far-future dates.
- Onboarding/employee edits with inline overrides fixing required gaps; failure without a fix rolls back assignments and revisions.
- Future edits preserving earlier input evidence. Historical correction/cancellation workflow tests are deferred with those editors.

These tests establish the core behavior without excessive test infrastructure. Browser and computer-use testing belongs to the human and is outside the automated test scope.

## Scale and tradeoffs

- Typed employee fields make the supported rule vocabulary explicit; adding a new attribute requires a schema and resolver change.
- JSON conditions keep rule storage small, but require application-level validation and a deliberately limited language.
- A dedicated override table adds one small concept to the schema, while making employee exceptions, exclusions, validation, and HR workflows explicit.
- Stored intervals make frequent date-based reads simple. Index employee/category lookups and date ranges; batch reads for consumer requests involving multiple employees.
- Immutable input revisions and assignment-change records preserve evidence. A dedicated audit log, history screen, and full knowledge-time query API are deferred.
- Whole-population reconciliation on rule edits and a single write lock are appropriate for this dataset. They trade write throughput for easy-to-understand transactional correctness.
- At larger scale, use registry dependencies to narrow recomputation, including both previous and new matches so employees who stop matching lose stale assignments. Move to ordered per-employee locks with a shared-input revision check/retry protocol; employee locks alone do not coordinate concurrent global rule edits.
- If reconciliation becomes asynchronous, track input and assignment generations and define when consumers may read them; do not silently return stale assignments as current.
- For payroll or IT integrations, add a transactional outbox with stable event IDs, retries, and idempotent consumers. Distinguish a newly scheduled interval from an action due now. No external delivery infrastructure is needed for the demo.
- Multi-company support is a future extension: add company ownership to tables, tenant-scoped keys and foreign keys, and row-level security. It is intentionally outside the single-company implementation.
- Complete materialization is practical because supported predicates have finite boundaries and the final interval can be unbounded. Recurring or arbitrary time-dependent predicates would require revisiting this contract. Benchmark before introducing more infrastructure.
