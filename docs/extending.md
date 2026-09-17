# Extending the MVP

Prefer adding data or an ordinary command over introducing another framework.

## A policy in an existing category

Use Policies → Create policy, then add a rule or a manual assignment. No schema or resolver change is necessary. Business-specific payloads (such as a vacation allowance) can later live in feature-owned tables keyed by policy ID; the assignment engine only decides who gets the policy and when.

## An employee field

1. Add its storage with an Alembic migration if it is a new persisted fact. Attribute revisions remain immutable; append/supersede them through the employee planner.
2. Add the field to `FIELDS` in `backend/app/resolver.py`, declaring type, label, operators, and input dependencies. Ordinary stored attributes are read from the dated snapshot. Derived attributes also need a snapshot reader.
3. For a time-dependent field, enumerate a finite and complete set of truth-change dates for the actual condition operands. The resolver cannot support an arbitrary predicate that changes at unenumerable dates. Tenure demonstrates calendar-anniversary boundaries.
4. Extend the employee command/form if HR should edit that fact. Lookup fields need ID-backed choices in `rule_fields()` and reference validation. The rule builder consumes field/operator metadata from the API; simple string, numeric-tenure, and boolean controls are already represented.
5. Include every affected employee in reconciliation (including other employees when a derived relationship changes). Add a focused boundary or reconciliation test, then regenerate frontend types with `make types`.

Persistence, domain validation, and editing are deliberately explicit rather than hidden behind a plugin system. Adding a field is not literally a one-line change when it also needs storage or a new kind of input control.

## A category

Add a category with one of the fixed cardinalities: `exactly_one`, `at_most_one`, or `many`. Add initial policies and, for a required category, a covering default rule in the same transaction before reconciliation. Existing resolver/override/report behavior is category-driven. The MVP has no category-management screen; a migration or additive seed step is the intended developer workflow.

## An audit-history screen later

No generic audit-log framework is needed now. Immutable rule/employee/membership/override revisions already record actor/time/reason, and assignment-change snapshots retain the previous explanation and source IDs. A later screen can query those records. A full “what did we know at time T about effective date Z?” API requires explicit knowledge-time semantics; the current as-of query uses the latest recorded input history.

## Scaling beyond one company

Reads use indexed stored assignment intervals. Writes are rarer and currently serialized by a company-wide transaction lock. This keeps preview/save/reconciliation understandable for a seeded company, at the cost of write throughput and whole-company work for rule edits.

Before scaling, add company ownership and authorization throughout (including tenant-scoped keys and row-level security), dependency-based candidate selection that includes former matches, per-employee locking with coordination for shared rule revisions, and a transactional outbox for payroll/IT consumers. Do not simply replace the company lock with individual locks without solving shared-input consistency.

## Deliberate limits

One local company, fictional HR actor, no authentication. Flat AND conditions, no arbitrary expression language. New hire starts/edits are today or later; conflicting scheduled edits are rejected. No policy retirement/replacement workflow, historical correction/cancellation UI, termination/rehire editor, background job fleet, external delivery, or dedicated audit screen. These are extension points, not unfinished MVP infrastructure.
