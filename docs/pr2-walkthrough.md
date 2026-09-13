# PR 2 — Human walkthrough

Run `make up` and `make seed`, then open http://localhost:5180. This adds 12 rules and materializes assignments without replacing PR 1 employee records. Keep the demo date at September 12, 2026. No reset is needed. Changes in this increment stay local and are not pushed.

1. Open Jamie Park. Under Policy assignments, verify Biweekly pay. Expand “Why?” to see the US employee rule outrank the monthly default (lower order number wins).
2. Inspect Jamie's GitHub and Figma assignments: Engineering supplies GitHub; Launch team membership supplies Figma.
3. Open Morgan Ellis. At September 12, 2026, vacation is Standard. Select September 30, 2026, the two-year anniversary of Morgan's September 30, 2024 start. Vacation changes to Extended. The timeline shows the two exclusive date intervals.
4. Inspect Morgan's Figma explanation. Both the Design rule and Launch team rule contribute, but Figma appears only once.
5. Open Assignments in the sidebar. Clear selection, then select Jamie, Priya, and Morgan. Compare pay schedules on September 12: Jamie and Morgan receive Biweekly; Priya receives Monthly. Filter by a category or policy and expand explanations.
6. Select Alex and Sam and filter to Compliance training. Both have manager training because they have active direct reports. Inspect the source records if desired.
7. Select Riley before and after September 26, 2026. The earlier date identifies Riley as not employed; the start date has assignments. Former employees have no assignments after their exclusive end date.
8. Try January 1, 2099. Ongoing employment still has policies; these are stored results based on recorded rules, not a daily-job prediction. Date navigation does not write to the database.
9. Open Policies and expand the readable Assignment rules. Numeric order is local to each category. These rules are read-only in PR 2.
10. Run `make reconcile` twice. Both should report zero interval changes after a successful seed. Restarting retains assignments. Review keyboard navigation, narrow layouts, filters, and expanded explanations manually.

## Scope and verification

API report queries are read-only POST requests so employee selections are not limited by URL length. An empty selection means nobody; omitted selection means everyone. Unknown employee IDs are rejected. Missing required assignments are surfaced separately from the policy filter; dates outside employment have no coverage error. Run seed before reviewing a freshly migrated database.

The backend suite covers typed conditions, invalid operators, ties, multi-policy deduplication, leap-day tenure, finite timelines, manager dependencies, provenance changes, stored/point agreement, idempotent reruns, removal evidence, cardinality constraints, rollback, and two-connection lock visibility. No automated browser/computer-use tests were added.

Verified locally: 26 backend checks pass, generated API types and the frontend production build pass, and a repeat reconciliation reports zero interval changes. The report/rules/timeline HTTP endpoints return the expected seeded results. Manual UI review remains with the human.

Overrides, employee edits, and rule authoring remain for later increments. The UI does not offer those controls yet.
